import os
import uuid
import asyncio
import logging
import hashlib
import glob
from aiogram import Router, F, types
from aiogram.types import FSInputFile
from aiogram.exceptions import TelegramBadRequest, TelegramEntityTooLarge
from bot.services.audio_extractor import audio_extractor
from bot.services.recognition_service import recognition_service
from bot.database.models import User
from bot.database.session import Database
from bot.config import config
import aiohttp

router = Router()
logger = logging.getLogger(__name__)


from bot.utils.i18n import translator


async def _safe_edit_text(message: types.Message, text: str):
    """Edit message text, ignoring Telegram 'message is not modified' noise."""
    try:
        await message.edit_text(text)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            return
        raise

def _build_result_text(result, lang: str = "uz") -> str:
    labels_map = {
        "uz": {"song": "🎵 Qo'shiq", "artist": "🎤 Ijrochi", "album": "💿 Albom", "year": "📅 Yil"},
        "ru": {"song": "🎵 Песня", "artist": "🎤 Исполнитель", "album": "💿 Альбом", "year": "📅 Год"},
        "en": {"song": "🎵 Song", "artist": "🎤 Artist", "album": "💿 Album", "year": "📅 Year"}
    }
    labels = labels_map.get(lang, labels_map["uz"])

    lines = [
        f"{labels['song']}: {result.title}",
        f"{labels['artist']}: {result.artist}",
    ]
    if result.album:
        lines.append(f"{labels['album']}: {result.album}")
    if result.year:
        lines.append(f"{labels['year']}: {result.year}")
    return "\n".join(lines)


def _build_links_keyboard(result, audio_hash: str = None, lang: str = "uz") -> types.InlineKeyboardMarkup:
    buttons = []

    spotify = result.spotify_url
    if spotify and spotify.startswith("spotify:"):
        parts = spotify.replace("spotify:", "").split(":", 1)
        if len(parts) == 2:
            spotify = f"https://open.spotify.com/{parts[0]}/{parts[1]}"
        else:
            spotify = f"https://open.spotify.com/search/{parts[0]}"

    if spotify and spotify.startswith("https://"):
        buttons.append([types.InlineKeyboardButton(text="🎧 Spotify", url=spotify)])
    if result.youtube_url and result.youtube_url.startswith("https://"):
        buttons.append([types.InlineKeyboardButton(text="📺 YouTube", url=result.youtube_url)])
    if result.apple_music_url and result.apple_music_url.startswith("https://"):
        buttons.append([types.InlineKeyboardButton(text="🍎 Apple Music", url=result.apple_music_url)])
    if result.shazam_url and result.shazam_url.startswith("https://"):
        buttons.append([types.InlineKeyboardButton(text="🔍 Shazam", url=result.shazam_url)])

    if result.lyrics and audio_hash:
        label = translator.get("btn_lyrics", lang)
        buttons.append([types.InlineKeyboardButton(text=label, callback_data=f"lyrics:{audio_hash[:16]}")])

    # ADD MANUAL DOWNLOAD BUTTON
    if audio_hash:
        download_label = translator.get("btn_music", lang)
        buttons.append([types.InlineKeyboardButton(text=f"⬇️ {download_label}", callback_data=f"mdl:{audio_hash[:16]}")])
        spatial_label = translator.get("btn_8d", lang)
        buttons.append([types.InlineKeyboardButton(text=f"🌀 {spatial_label}", callback_data=f"m8d:{audio_hash[:16]}")])
        hall_label = translator.get("btn_hall", lang)
        buttons.append([types.InlineKeyboardButton(text=f"🏛 {hall_label}", callback_data=f"mch:{audio_hash[:16]}")])

    if not buttons:
        return None
    return types.InlineKeyboardMarkup(inline_keyboard=buttons)


async def _download_telegram_file(
    bot,
    file_id: str,
    max_size_bytes: int | None = 20 * 1024 * 1024,
) -> str:
    file = await bot.get_file(file_id)
    
    if max_size_bytes and file.file_size and file.file_size > max_size_bytes:
        max_mb = max_size_bytes / (1024 * 1024)
        raise ValueError(f"File too large: {file.file_size / (1024*1024):.1f}MB (max {max_mb:.1f}MB)")
    
    ext = os.path.splitext(file.file_path)[1] if file.file_path else ".tmp"
    local_path = os.path.join(config.DOWNLOAD_DIR, f"{uuid.uuid4()}{ext}")
    await bot.download_file(file.file_path, local_path)
    return local_path


def _build_sample_plan(duration_seconds: float | None) -> list[dict]:
    """
    Build dynamic sample windows for better recognition quality.
    Returns list items: {"start": int, "duration": int}
    """
    if not duration_seconds or duration_seconds <= 0:
        return [
            {"start": 0, "duration": 20},
            {"start": 20, "duration": 20},
            {"start": 45, "duration": 20},
        ]

    total = max(1, int(duration_seconds))
    if total <= 12:
        return [{"start": 0, "duration": total}]

    clip = 24 if total >= 90 else 18
    anchors = [0.10, 0.32, 0.55, 0.78]
    samples = []
    used_starts = set()

    for anchor in anchors:
        center = int(total * anchor)
        start = max(0, center - (clip // 2))
        if start + clip > total:
            start = max(0, total - clip)

        if start in used_starts:
            continue
        if any(abs(start - item["start"]) < max(4, clip // 2) for item in samples):
            continue
        used_starts.add(start)

        dur = min(clip, total - start)
        if dur >= 8:
            samples.append({"start": start, "duration": dur})

    if not samples:
        return [{"start": 0, "duration": min(20, total)}]

    if samples[0]["start"] > 3:
        samples.insert(0, {"start": 0, "duration": min(samples[0]["duration"], total)})

    return samples[:5]


async def _tag_mp3_file(file_path: str, result):
    """Apply ID3 tags and cover art to the MP3 file."""
    try:
        from mutagen.id3 import ID3, TIT2, TPE1, TALB, TYER, APIC
        from mutagen.mp3 import MP3
        
        audio = MP3(file_path, ID3=ID3)
        try:
            audio.add_tags()
        except:
            pass
            
        audio.tags.add(TIT2(encoding=3, text=result.title))
        audio.tags.add(TPE1(encoding=3, text=result.artist))
        if result.album:
            audio.tags.add(TALB(encoding=3, text=result.album))
        if result.year:
            audio.tags.add(TYER(encoding=3, text=result.year))
            
        if result.cover_url:
            async with aiohttp.ClientSession() as session:
                async with session.get(result.cover_url) as resp:
                    if resp.status == 200:
                        image_data = await resp.read()
                        audio.tags.add(APIC(
                            encoding=3,
                            mime='image/jpeg',
                            type=3,
                            desc='Cover',
                            data=image_data
                        ))
        
        audio.save()
        return True
    except Exception as e:
        logger.error(f"Error tagging MP3: {e}")
        return False


async def _download_music_from_youtube(result) -> dict | None:
    """Search YouTube and download audio with fastest possible settings."""
    title = result.title
    artist = result.artist
    source = (getattr(result, "youtube_url", None) or "").strip()
    if source and source.startswith("https://"):
        download_source = source
    else:
        download_source = f"{artist} {title} audio"
    output_base = os.path.join(config.DOWNLOAD_DIR, str(uuid.uuid4()))

    # Fast path: avoid transcoding to mp3 (conversion costs significant time).
    fast_opts = {
        'format': 'bestaudio[ext=m4a][abr<=128]/bestaudio[ext=m4a]/bestaudio[abr<=128]/bestaudio/best',
        'outtmpl': output_base + '.%(ext)s',
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'socket_timeout': 12,
        'retries': 1,
        'fragment_retries': 1,
        'extractor_retries': 0,
        'concurrent_fragment_downloads': 8,
        'cachedir': False,
    }
    if not (download_source.startswith("http://") or download_source.startswith("https://")):
        fast_opts['default_search'] = 'ytsearch1'

    try:
        import yt_dlp
        loop = asyncio.get_event_loop()

        def _download_fast():
            with yt_dlp.YoutubeDL(fast_opts) as ydl:
                info = ydl.extract_info(download_source, download=True)
                if 'entries' in info:
                    info = info['entries'][0]
                return info

        info = await loop.run_in_executor(None, _download_fast)

        candidates = [
            path for path in sorted(glob.glob(output_base + ".*"))
            if os.path.isfile(path) and not path.endswith((".part", ".ytdl"))
        ]
        preferred_ext = [".m4a", ".mp3", ".aac", ".opus", ".webm"]
        actual_path = None
        for ext in preferred_ext:
            match = next((p for p in candidates if p.lower().endswith(ext)), None)
            if match:
                actual_path = match
                break
        if not actual_path and candidates:
            actual_path = candidates[0]

        if actual_path and os.path.exists(actual_path):
            return {
                'title': info.get('title', title),
                'duration': info.get('duration', 0),
                'uploader': info.get('uploader', artist),
                'file_path': actual_path
            }

        return None
    except Exception as e:
        logger.error(f"YouTube music download error: {e}")
        return None


async def _convert_audio_to_mp3(input_path: str, bitrate_kbps: int = 128, timeout_sec: int = 30) -> str | None:
    """Convert audio to MP3 for Telegram send_audio compatibility."""
    output_path = os.path.join(config.DOWNLOAD_DIR, f"{uuid.uuid4()}.mp3")
    safe_bitrate = max(48, min(int(bitrate_kbps), 192))
    safe_timeout = max(10, min(int(timeout_sec), 90))
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vn",
        "-acodec", "libmp3lame",
        "-b:a", f"{safe_bitrate}k",
        output_path,
    ]
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await asyncio.wait_for(process.communicate(), timeout=safe_timeout)
        except asyncio.TimeoutError:
            process.kill()
            try:
                await process.communicate()
            except Exception:
                pass
            logger.warning(
                f"MP3 conversion timeout after {safe_timeout}s "
                f"(bitrate={safe_bitrate}k, input={input_path})"
            )
            audio_extractor.cleanup(output_path)
            return None

        if process.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return output_path
        logger.warning(
            f"MP3 conversion failed (rc={process.returncode}, bitrate={safe_bitrate}k): "
            f"{(stderr or b'').decode(errors='ignore')[:300]}"
        )
        audio_extractor.cleanup(output_path)
        return None
    except FileNotFoundError:
        logger.error("MP3 conversion error: ffmpeg binary not found in PATH")
        audio_extractor.cleanup(output_path)
        return None
    except Exception as e:
        logger.warning(f"MP3 conversion error ({type(e).__name__}): {e!r}")
        audio_extractor.cleanup(output_path)
        return None


async def _convert_audio_to_8d(input_path: str, bitrate_kbps: int = 128, timeout_sec: int = 75) -> str | None:
    """Convert input audio to a simple 8D-style stereo panning MP3."""
    output_path = os.path.join(config.DOWNLOAD_DIR, f"{uuid.uuid4()}_8d.mp3")
    safe_bitrate = max(64, min(int(bitrate_kbps), 192))
    safe_timeout = max(20, min(int(timeout_sec), 180))

    # apulsator provides lightweight left-right rotation for "8D" effect.
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vn",
        "-ac", "2",
        "-ar", "44100",
        "-af", "apulsator=hz=0.085:amount=0.92:offset_r=0.55",
        "-acodec", "libmp3lame",
        "-b:a", f"{safe_bitrate}k",
        output_path,
    ]
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await asyncio.wait_for(process.communicate(), timeout=safe_timeout)
        except asyncio.TimeoutError:
            process.kill()
            try:
                await process.communicate()
            except Exception:
                pass
            logger.warning(
                f"8D conversion timeout after {safe_timeout}s "
                f"(bitrate={safe_bitrate}k, input={input_path})"
            )
            audio_extractor.cleanup(output_path)
            return None

        if process.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return output_path

        logger.warning(
            f"8D conversion failed (rc={process.returncode}, bitrate={safe_bitrate}k): "
            f"{(stderr or b'').decode(errors='ignore')[:300]}"
        )
        audio_extractor.cleanup(output_path)
        return None
    except FileNotFoundError:
        logger.error("8D conversion error: ffmpeg binary not found in PATH")
        audio_extractor.cleanup(output_path)
        return None
    except Exception as e:
        logger.warning(f"8D conversion error ({type(e).__name__}): {e!r}")
        audio_extractor.cleanup(output_path)
        return None


async def _convert_audio_to_concert_hall(
    input_path: str,
    bitrate_kbps: int = 128,
    timeout_sec: int = 75,
) -> str | None:
    """Convert input audio to a concert-hall style reverberation MP3."""
    output_path = os.path.join(config.DOWNLOAD_DIR, f"{uuid.uuid4()}_hall.mp3")
    safe_bitrate = max(64, min(int(bitrate_kbps), 192))
    safe_timeout = max(20, min(int(timeout_sec), 180))

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vn",
        "-ac", "2",
        "-ar", "44100",
        "-af", "aecho=0.8:0.85:70|140|210:0.25|0.18|0.12,volume=0.95",
        "-acodec", "libmp3lame",
        "-b:a", f"{safe_bitrate}k",
        output_path,
    ]
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await asyncio.wait_for(process.communicate(), timeout=safe_timeout)
        except asyncio.TimeoutError:
            process.kill()
            try:
                await process.communicate()
            except Exception:
                pass
            logger.warning(
                f"Concert Hall conversion timeout after {safe_timeout}s "
                f"(bitrate={safe_bitrate}k, input={input_path})"
            )
            audio_extractor.cleanup(output_path)
            return None

        if process.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return output_path

        logger.warning(
            f"Concert Hall conversion failed (rc={process.returncode}, bitrate={safe_bitrate}k): "
            f"{(stderr or b'').decode(errors='ignore')[:300]}"
        )
        audio_extractor.cleanup(output_path)
        return None
    except FileNotFoundError:
        logger.error("Concert Hall conversion error: ffmpeg binary not found in PATH")
        audio_extractor.cleanup(output_path)
        return None
    except Exception as e:
        logger.warning(f"Concert Hall conversion error ({type(e).__name__}): {e!r}")
        audio_extractor.cleanup(output_path)
        return None


async def _prepare_audio_for_telegram(path: str) -> str:
    """Ensure file can be sent via Telegram send_audio."""
    ext = os.path.splitext(path)[1].lower()
    if ext in {".mp3", ".m4a"}:
        return path
    converted = await _convert_audio_to_mp3(path)
    return converted or path


def _max_audio_upload_bytes() -> int:
    """
    Telegram bot upload practical limit.
    Keep a small safety margin below configured max.
    """
    try:
        configured_mb = int(config.MAX_VIDEO_SIZE_MB or 50)
    except Exception:
        configured_mb = 50
    safe_mb = max(5, min(configured_mb, 49))
    return safe_mb * 1024 * 1024


async def _fit_audio_for_telegram(path: str) -> str | None:
    """
    Ensure file is in a Telegram-friendly format and under upload limit.
    Returns sendable path or None if compression cannot fit the limit.
    """
    send_path = await _prepare_audio_for_telegram(path)
    if not send_path or not os.path.exists(send_path):
        return None

    max_bytes = _max_audio_upload_bytes()
    try:
        size = os.path.getsize(send_path)
    except Exception:
        return None

    if size <= max_bytes:
        return send_path

    duration = await audio_extractor.probe_duration(send_path)
    if not duration:
        duration = await audio_extractor.probe_duration(path)
    duration = max(1.0, float(duration or 180.0))

    # Estimated bitrate to fit target size with protocol/container overhead margin.
    target_kbps = int((max_bytes * 8) / (duration * 1000) * 0.90)
    target_kbps = max(48, min(target_kbps, 128))

    # Keep attempts limited to avoid multi-minute conversion loops.
    attempts = [target_kbps, 64, 48]
    seen = set()
    conv_timeout = int(min(40, max(12, duration * 0.18)))

    for bitrate in attempts:
        if bitrate in seen:
            continue
        seen.add(bitrate)

        compressed = await _convert_audio_to_mp3(
            send_path,
            bitrate_kbps=bitrate,
            timeout_sec=conv_timeout,
        )
        if not compressed or not os.path.exists(compressed):
            continue

        try:
            csize = os.path.getsize(compressed)
        except Exception:
            audio_extractor.cleanup(compressed)
            continue

        if csize <= max_bytes:
            return compressed

        audio_extractor.cleanup(compressed)

    return None


def _build_track_cache_key(result) -> str:
    raw = f"{(result.artist or '').strip().lower()}::{(result.title or '').strip().lower()}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()
    return f"track_audio:{digest}"


async def _get_cached_track_audio_file_id(result) -> str | None:
    redis_client = recognition_service.redis
    if not redis_client:
        return None
    try:
        return await redis_client.get(_build_track_cache_key(result))
    except Exception:
        return None


async def _set_cached_track_audio_file_id(result, file_id: str):
    redis_client = recognition_service.redis
    if not redis_client or not file_id:
        return
    try:
        # 14 days global track cache
        await redis_client.set(_build_track_cache_key(result), file_id, ex=14 * 24 * 3600)
    except Exception:
        pass


def _build_track_8d_cache_key(result) -> str:
    raw = f"{(result.artist or '').strip().lower()}::{(result.title or '').strip().lower()}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()
    return f"track_audio8d:{digest}"


async def _get_cached_track_8d_audio_file_id(result) -> str | None:
    redis_client = recognition_service.redis
    if not redis_client:
        return None
    try:
        return await redis_client.get(_build_track_8d_cache_key(result))
    except Exception:
        return None


async def _set_cached_track_8d_audio_file_id(result, file_id: str):
    redis_client = recognition_service.redis
    if not redis_client or not file_id:
        return
    try:
        # 14 days global cache for converted 8D tracks.
        await redis_client.set(_build_track_8d_cache_key(result), file_id, ex=14 * 24 * 3600)
    except Exception:
        pass


def _build_track_hall_cache_key(result) -> str:
    raw = f"{(result.artist or '').strip().lower()}::{(result.title or '').strip().lower()}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()
    return f"track_audiohall:{digest}"


async def _get_cached_track_hall_audio_file_id(result) -> str | None:
    redis_client = recognition_service.redis
    if not redis_client:
        return None
    try:
        return await redis_client.get(_build_track_hall_cache_key(result))
    except Exception:
        return None


async def _set_cached_track_hall_audio_file_id(result, file_id: str):
    redis_client = recognition_service.redis
    if not redis_client or not file_id:
        return
    try:
        # 14 days global cache for converted concert-hall tracks.
        await redis_client.set(_build_track_hall_cache_key(result), file_id, ex=14 * 24 * 3600)
    except Exception:
        pass


async def _process_recognition(message: types.Message, file_id: str, user: User, db: Database | None = None):
    """Recognition pipeline with dynamic sampling and confidence-based pick."""
    status_msg = await message.answer(translator.get("recog_status", user.language))
    local_path = None
    music_path = None
    extra_cleanup_paths: list[str] = []
    temp_audio_paths: list[str] = []

    try:
        await _safe_edit_text(status_msg, translator.get("recog_downloading", user.language))
        local_path = await _download_telegram_file(message.bot, file_id)

        media_duration = await audio_extractor.probe_duration(local_path)
        samples = _build_sample_plan(media_duration)

        best_result = None
        best_hash = None
        best_score = -1
        votes: dict[str, int] = {}
        seen_hashes = set()

        for i, sample in enumerate(samples, start=1):
            await _safe_edit_text(status_msg, f"{translator.get('recog_shazam', user.language)} ({i}/{len(samples)})...")

            temp_audio = await audio_extractor.extract_audio(
                local_path,
                duration=sample["duration"],
                start_time=sample["start"],
            )
            if not temp_audio:
                continue

            temp_audio_paths.append(temp_audio)
            current_hash = recognition_service._get_audio_hash(temp_audio)
            if current_hash in seen_hashes:
                continue
            seen_hashes.add(current_hash)

            current_result = await recognition_service.recognize(temp_audio)
            if not current_result:
                continue

            result_key = f"{(current_result.artist or '').strip().lower()}::{(current_result.title or '').strip().lower()}"
            votes[result_key] = votes.get(result_key, 0) + 1

            score = current_result.match_count or 0
            if current_result.lyrics:
                score += 5
            if current_result.cover_url:
                score += 3
            score += votes[result_key] * 20

            if score > best_score:
                best_score = score
                best_result = current_result
                best_hash = current_hash

            # Two matching samples means high confidence.
            if votes[result_key] >= 2:
                break

        if not best_result:
            # Last-resort pass: try a couple of longer extracted windows.
            fallback_windows = []
            if media_duration and media_duration > 0:
                total = int(media_duration)
                long_dur = max(10, min(36, total))
                mid_start = max(0, (total // 2) - (long_dur // 2))
                fallback_windows.append({"start": mid_start, "duration": long_dur})
                fallback_windows.append({"start": 0, "duration": min(30, total)})
            else:
                fallback_windows.append({"start": 0, "duration": 30})

            for sample in fallback_windows:
                await _safe_edit_text(status_msg, f"{translator.get('recog_shazam', user.language)} (fallback)...")
                temp_audio = await audio_extractor.extract_audio(
                    local_path,
                    duration=sample["duration"],
                    start_time=sample["start"],
                )
                if not temp_audio:
                    continue

                temp_audio_paths.append(temp_audio)
                current_hash = recognition_service._get_audio_hash(temp_audio)
                if current_hash in seen_hashes:
                    continue
                seen_hashes.add(current_hash)

                current_result = await recognition_service.recognize(temp_audio)
                if current_result:
                    best_result = current_result
                    best_hash = current_hash
                    break

        if not best_result:
            await _safe_edit_text(status_msg, translator.get("recog_not_found", user.language))
            return

        result = best_result
        audio_hash = best_hash

        if recognition_service.redis and audio_hash:
            prefix = audio_hash[:16]
            await recognition_service.redis.set(f"rec_prefix:{prefix}", audio_hash, ex=86400)
            await recognition_service.redis.set(f"ly_prefix:{prefix}", audio_hash, ex=86400)
            await recognition_service.cache_result(audio_hash, result)

        if db:
            await db.add_recognition_log(user.id, result.title, result.artist)

        text = _build_result_text(result, user.language)
        keyboard = _build_links_keyboard(result, audio_hash, user.language)

        if result.cover_url:
            try:
                await message.answer_photo(photo=result.cover_url, caption=text, reply_markup=keyboard)
            except Exception:
                await message.answer(text, reply_markup=keyboard)
        else:
            await message.answer(text, reply_markup=keyboard)

        if result.audio_file_id:
            try:
                await message.answer_audio(
                    audio=result.audio_file_id,
                    title=result.title,
                    performer=result.artist,
                    caption=f"🎵 {result.artist} — {result.title} (Cached)"
                )
                await status_msg.delete()
                return
            except Exception:
                # Telegram file_id may expire. Continue with fresh download.
                result.audio_file_id = None
        else:
            # Cross-user cache: if this track was already uploaded before, send instantly.
            result.audio_file_id = await _get_cached_track_audio_file_id(result)
            if result.audio_file_id:
                try:
                    await message.answer_audio(
                        audio=result.audio_file_id,
                        title=result.title,
                        performer=result.artist,
                        caption=f"🎵 {result.artist} — {result.title} (Cached)"
                    )
                    await status_msg.delete()
                    return
                except Exception:
                    result.audio_file_id = None

        await _safe_edit_text(status_msg, translator.get("recog_download_music", user.language))
        music = await _download_music_from_youtube(result)

        if music and music.get("file_path"):
            music_path = music["file_path"]
            send_path = await _fit_audio_for_telegram(music_path)
            if not send_path:
                await message.answer("⚠️ Audio fayl hajmi Telegram limitidan katta.")
                await status_msg.delete()
                return
            if send_path != music_path:
                extra_cleanup_paths.append(send_path)

            ext = os.path.splitext(send_path)[1] or ".mp3"
            filename = f"{result.artist} - {result.title}{ext}"
            audio_file = FSInputFile(send_path, filename=filename)

            try:
                sent_audio = await message.answer_audio(
                    audio=audio_file,
                    title=result.title,
                    performer=result.artist,
                    caption=f"🎵 {result.artist} — {result.title}"
                )
            except TelegramEntityTooLarge:
                # Emergency fallback: try ultra-low bitrate once.
                fallback_mp3 = await _convert_audio_to_mp3(
                    send_path,
                    bitrate_kbps=48,
                    timeout_sec=20,
                )
                if fallback_mp3 and os.path.exists(fallback_mp3):
                    extra_cleanup_paths.append(fallback_mp3)
                    fallback_file = FSInputFile(
                        fallback_mp3,
                        filename=f"{result.artist} - {result.title}.mp3"
                    )
                    sent_audio = await message.answer_audio(
                        audio=fallback_file,
                        title=result.title,
                        performer=result.artist,
                        caption=f"🎵 {result.artist} — {result.title}"
                    )
                else:
                    sent_audio = None
                    await message.answer("⚠️ Audio fayl hajmi juda katta, yuborib bo'lmadi.")
            except Exception as send_error:
                logger.warning(f"send_audio failed for {send_path}: {send_error}")
                sent_audio = None
                if not send_path.lower().endswith(".mp3"):
                    fallback_mp3 = await _convert_audio_to_mp3(
                        send_path,
                        bitrate_kbps=64,
                        timeout_sec=20,
                    )
                    if fallback_mp3:
                        extra_cleanup_paths.append(fallback_mp3)
                        fallback_file = FSInputFile(
                            fallback_mp3,
                            filename=f"{result.artist} - {result.title}.mp3"
                        )
                        sent_audio = await message.answer_audio(
                            audio=fallback_file,
                            title=result.title,
                            performer=result.artist,
                            caption=f"🎵 {result.artist} — {result.title}"
                        )
                    else:
                        doc_file = FSInputFile(send_path, filename=filename)
                        await message.answer_document(
                            document=doc_file,
                            caption=f"🎵 {result.artist} — {result.title}"
                        )
                else:
                    doc_file = FSInputFile(send_path, filename=filename)
                    await message.answer_document(
                        document=doc_file,
                        caption=f"🎵 {result.artist} — {result.title}"
                    )

            if sent_audio and sent_audio.audio and audio_hash:
                result.audio_file_id = sent_audio.audio.file_id
                await recognition_service.cache_result(audio_hash, result)
                await _set_cached_track_audio_file_id(result, sent_audio.audio.file_id)
        else:
            await message.answer(translator.get("recog_error", user.language))

        await status_msg.delete()

    except Exception as e:
        logger.error(f"Recognition pipeline error: {e}", exc_info=True)
        try:
            await _safe_edit_text(status_msg, "⚠️ Error.")
        except Exception:
            pass
    finally:
        audio_extractor.cleanup(local_path, *temp_audio_paths)
        if music_path:
            audio_extractor.cleanup(music_path)
        if extra_cleanup_paths:
            audio_extractor.cleanup(*extra_cleanup_paths)


# ─── Handlers ────────────────────────────────────────

@router.message(F.voice)
async def handle_voice(message: types.Message, user: User, db: Database, **data):
    await _process_recognition(message, message.voice.file_id, user, db)

@router.message(F.audio)
async def handle_audio(message: types.Message, user: User, db: Database, **data):
    await _process_recognition(message, message.audio.file_id, user, db)

@router.message(F.video)
async def handle_video_recognition(message: types.Message, user: User, db: Database, **data):
    await _process_recognition(message, message.video.file_id, user, db)

@router.message(F.video_note)
async def handle_video_note(message: types.Message, user: User, db: Database, **data):
    await _process_recognition(message, message.video_note.file_id, user, db)


# ─── Callback: Recognize from downloaded video ───────

@router.callback_query(F.data == "recognize_music")
async def callback_recognize_music(callback: types.CallbackQuery, user: User, db: Database, **data):
    await callback.answer(translator.get("recog_status", user.language))

    msg = callback.message
    file_id = None

    if msg.video:
        file_id = msg.video.file_id
    elif msg.document:
        file_id = msg.document.file_id

    if not file_id:
        await msg.answer("❌ Error.")
        return

    await _process_recognition(msg, file_id, user, db)


async def _resolve_full_hash_by_prefix(prefix: str) -> str | None:
    if not recognition_service.redis:
        return None
    full_hash = await recognition_service.redis.get(f"rec_prefix:{prefix}")
    if not full_hash:
        full_hash = await recognition_service.redis.get(f"ly_prefix:{prefix}")
    return full_hash


# ─── Callback: Convert Music To 8D ─────────────────────

@router.callback_query(F.data.startswith("m8d:"))
async def callback_convert_music_8d(callback: types.CallbackQuery, user: User, **data):
    prefix = callback.data.split(":", 1)[1]

    if not recognition_service.redis:
        await callback.answer("⚠️ Redis Error.", show_alert=True)
        return

    full_hash = await _resolve_full_hash_by_prefix(prefix)
    if not full_hash:
        await callback.answer("😔 Session expired. Please recognize again.", show_alert=True)
        return

    cached = await recognition_service.get_cached_result(full_hash)
    if not cached:
        await callback.answer("❌ Result not found.", show_alert=True)
        return

    cached_8d_file_id = await _get_cached_track_8d_audio_file_id(cached)
    if cached_8d_file_id:
        try:
            await callback.message.answer_audio(
                audio=cached_8d_file_id,
                title=f"{cached.title} (8D)",
                performer=cached.artist,
                caption=f"🌀 {cached.artist} — {cached.title} (8D)"
            )
            await callback.answer("✅")
            return
        except Exception:
            pass

    await callback.answer(translator.get("downloading", user.language))
    status_msg = await callback.message.answer(translator.get("recog_make_8d", user.language))

    cleanup_paths: list[str] = []
    try:
        source_path = None
        source_file_id = cached.audio_file_id or await _get_cached_track_audio_file_id(cached)
        if source_file_id:
            try:
                source_path = await _download_telegram_file(
                    callback.bot,
                    source_file_id,
                    max_size_bytes=_max_audio_upload_bytes(),
                )
                cleanup_paths.append(source_path)
            except Exception as e:
                logger.warning(f"Unable to download source audio by file_id for 8D: {e}")

        if not source_path:
            music = await _download_music_from_youtube(cached)
            if music and music.get("file_path"):
                source_path = music["file_path"]
                cleanup_paths.append(source_path)

        if not source_path:
            await _safe_edit_text(status_msg, translator.get("recog_error", user.language))
            return

        converted_8d = await _convert_audio_to_8d(
            source_path,
            bitrate_kbps=128,
            timeout_sec=75,
        )
        if not converted_8d:
            await _safe_edit_text(status_msg, translator.get("recog_8d_error", user.language))
            return
        cleanup_paths.append(converted_8d)

        send_path = await _fit_audio_for_telegram(converted_8d)
        if not send_path:
            await _safe_edit_text(status_msg, "⚠️ Audio fayl hajmi Telegram limitidan katta.")
            return
        if send_path != converted_8d:
            cleanup_paths.append(send_path)

        ext = os.path.splitext(send_path)[1] or ".mp3"
        filename = f"{cached.artist} - {cached.title} (8D){ext}"
        audio_file = FSInputFile(send_path, filename=filename)

        sent_audio = None
        try:
            sent_audio = await callback.message.answer_audio(
                audio=audio_file,
                title=f"{cached.title} (8D)",
                performer=cached.artist,
                caption=f"🌀 {cached.artist} — {cached.title} (8D)"
            )
        except TelegramEntityTooLarge:
            await callback.message.answer("⚠️ Audio fayl hajmi juda katta, yuborib bo'lmadi.")
        except Exception as send_error:
            logger.warning(f"send_audio failed for 8D file {send_path}: {send_error}")
            doc_file = FSInputFile(send_path, filename=filename)
            await callback.message.answer_document(
                document=doc_file,
                caption=f"🌀 {cached.artist} — {cached.title} (8D)"
            )

        if sent_audio and sent_audio.audio:
            await _set_cached_track_8d_audio_file_id(cached, sent_audio.audio.file_id)

        await status_msg.delete()
    except Exception as e:
        logger.error(f"8D conversion error: {e}", exc_info=True)
        await _safe_edit_text(status_msg, translator.get("recog_8d_error", user.language))
    finally:
        if cleanup_paths:
            audio_extractor.cleanup(*cleanup_paths)


# ─── Callback: Convert Music To Concert Hall ───────────

@router.callback_query(F.data.startswith("mch:"))
async def callback_convert_music_hall(callback: types.CallbackQuery, user: User, **data):
    prefix = callback.data.split(":", 1)[1]

    if not recognition_service.redis:
        await callback.answer("⚠️ Redis Error.", show_alert=True)
        return

    full_hash = await _resolve_full_hash_by_prefix(prefix)
    if not full_hash:
        await callback.answer("😔 Session expired. Please recognize again.", show_alert=True)
        return

    cached = await recognition_service.get_cached_result(full_hash)
    if not cached:
        await callback.answer("❌ Result not found.", show_alert=True)
        return

    cached_hall_file_id = await _get_cached_track_hall_audio_file_id(cached)
    if cached_hall_file_id:
        try:
            await callback.message.answer_audio(
                audio=cached_hall_file_id,
                title=f"{cached.title} (Concert Hall)",
                performer=cached.artist,
                caption=f"🏛 {cached.artist} — {cached.title} (Concert Hall)"
            )
            await callback.answer("✅")
            return
        except Exception:
            pass

    await callback.answer(translator.get("downloading", user.language))
    status_msg = await callback.message.answer(translator.get("recog_make_hall", user.language))

    cleanup_paths: list[str] = []
    try:
        source_path = None
        source_file_id = cached.audio_file_id or await _get_cached_track_audio_file_id(cached)
        if source_file_id:
            try:
                source_path = await _download_telegram_file(
                    callback.bot,
                    source_file_id,
                    max_size_bytes=_max_audio_upload_bytes(),
                )
                cleanup_paths.append(source_path)
            except Exception as e:
                logger.warning(f"Unable to download source audio by file_id for Hall: {e}")

        if not source_path:
            music = await _download_music_from_youtube(cached)
            if music and music.get("file_path"):
                source_path = music["file_path"]
                cleanup_paths.append(source_path)

        if not source_path:
            await _safe_edit_text(status_msg, translator.get("recog_error", user.language))
            return

        converted_hall = await _convert_audio_to_concert_hall(
            source_path,
            bitrate_kbps=128,
            timeout_sec=75,
        )
        if not converted_hall:
            await _safe_edit_text(status_msg, translator.get("recog_hall_error", user.language))
            return
        cleanup_paths.append(converted_hall)

        send_path = await _fit_audio_for_telegram(converted_hall)
        if not send_path:
            await _safe_edit_text(status_msg, "⚠️ Audio fayl hajmi Telegram limitidan katta.")
            return
        if send_path != converted_hall:
            cleanup_paths.append(send_path)

        ext = os.path.splitext(send_path)[1] or ".mp3"
        filename = f"{cached.artist} - {cached.title} (Concert Hall){ext}"
        audio_file = FSInputFile(send_path, filename=filename)

        sent_audio = None
        try:
            sent_audio = await callback.message.answer_audio(
                audio=audio_file,
                title=f"{cached.title} (Concert Hall)",
                performer=cached.artist,
                caption=f"🏛 {cached.artist} — {cached.title} (Concert Hall)"
            )
        except TelegramEntityTooLarge:
            await callback.message.answer("⚠️ Audio fayl hajmi juda katta, yuborib bo'lmadi.")
        except Exception as send_error:
            logger.warning(f"send_audio failed for Hall file {send_path}: {send_error}")
            doc_file = FSInputFile(send_path, filename=filename)
            await callback.message.answer_document(
                document=doc_file,
                caption=f"🏛 {cached.artist} — {cached.title} (Concert Hall)"
            )

        if sent_audio and sent_audio.audio:
            await _set_cached_track_hall_audio_file_id(cached, sent_audio.audio.file_id)

        await status_msg.delete()
    except Exception as e:
        logger.error(f"Concert Hall conversion error: {e}", exc_info=True)
        await _safe_edit_text(status_msg, translator.get("recog_hall_error", user.language))
    finally:
        if cleanup_paths:
            audio_extractor.cleanup(*cleanup_paths)


# ─── Callback: Show Lyrics ───────────────────────────

@router.callback_query(F.data.startswith("lyrics:"))
async def callback_show_lyrics(callback: types.CallbackQuery, user: User, **data):
    prefix = callback.data.split(":", 1)[1]

    if not recognition_service.redis:
        await callback.answer("⚠️ Redis Error.", show_alert=True)
        return

    full_hash = await recognition_service.redis.get(f"rec_prefix:{prefix}")
    if not full_hash:
        full_hash = await recognition_service.redis.get(f"ly_prefix:{prefix}")
    if not full_hash:
        await callback.answer("😔 Session expired. Please recognize again.", show_alert=True)
        return

    cached = await recognition_service.get_cached_result(full_hash)
    if not cached or not cached.lyrics:
        await callback.answer(translator.get("lyrics_not_found", user.language), show_alert=True)
        return

    title = f"{cached.artist} — {cached.title}"
    lyrics_text = translator.get("lyrics_title", user.language, title=title) + cached.lyrics
    if len(lyrics_text) > 3900:
        lyrics_text = lyrics_text[:3900] + "\n..."

    await callback.message.answer(lyrics_text)
    await callback.answer(translator.get("recog_lyrics_ready", user.language))


# ─── Callback: Manual Music Download ──────────────────────

@router.callback_query(F.data.startswith("mdl:"))
async def callback_manual_music_download(callback: types.CallbackQuery, user: User, **data):
    """Trigger music download manually if auto-download failed or skipped."""
    prefix = callback.data.split(":", 1)[1]
    
    if not recognition_service.redis:
        await callback.answer("⚠️ Redis Error.", show_alert=True)
        return

    full_hash = await recognition_service.redis.get(f"rec_prefix:{prefix}")
    if not full_hash:
        full_hash = await recognition_service.redis.get(f"ly_prefix:{prefix}")
    if not full_hash:
        await callback.answer("😔 Session expired. Please recognize again.", show_alert=True)
        return

    cached = await recognition_service.get_cached_result(full_hash)
    if not cached:
        await callback.answer("❌ Result not found.", show_alert=True)
        return

    # Fast path 1: per-recognition cached audio file_id
    if cached.audio_file_id:
        try:
            await callback.message.answer_audio(
                audio=cached.audio_file_id,
                title=cached.title,
                performer=cached.artist,
                caption=f"🎵 {cached.artist} — {cached.title} (Cached)"
            )
            await callback.answer("✅")
            return
        except Exception:
            cached.audio_file_id = None

    # Fast path 2: cross-user global track cache
    global_audio_file_id = await _get_cached_track_audio_file_id(cached)
    if global_audio_file_id:
        try:
            sent = await callback.message.answer_audio(
                audio=global_audio_file_id,
                title=cached.title,
                performer=cached.artist,
                caption=f"🎵 {cached.artist} — {cached.title} (Cached)"
            )
            if sent.audio:
                cached.audio_file_id = sent.audio.file_id
                await recognition_service.cache_result(full_hash, cached)
            await callback.answer("✅")
            return
        except Exception:
            pass

    await callback.answer(translator.get("downloading", user.language))
    status_msg = await callback.message.answer(translator.get("recog_download_music", user.language))
    
    music_path = None
    extra_cleanup_paths: list[str] = []
    try:
        music = await _download_music_from_youtube(cached)
        if music and music.get('file_path'):
            music_path = music['file_path']
            send_path = await _fit_audio_for_telegram(music_path)
            if not send_path:
                await _safe_edit_text(status_msg, "⚠️ Audio fayl hajmi Telegram limitidan katta.")
                return
            if send_path != music_path:
                extra_cleanup_paths.append(send_path)

            ext = os.path.splitext(send_path)[1] or ".mp3"
            filename = f"{cached.artist} - {cached.title}{ext}"
            audio_file = FSInputFile(send_path, filename=filename)

            try:
                sent_audio = await callback.message.answer_audio(
                    audio=audio_file,
                    title=cached.title,
                    performer=cached.artist,
                    caption=f"🎵 {cached.artist} — {cached.title}"
                )
            except TelegramEntityTooLarge:
                fallback_mp3 = await _convert_audio_to_mp3(
                    send_path,
                    bitrate_kbps=48,
                    timeout_sec=20,
                )
                if fallback_mp3 and os.path.exists(fallback_mp3):
                    extra_cleanup_paths.append(fallback_mp3)
                    fallback_file = FSInputFile(
                        fallback_mp3,
                        filename=f"{cached.artist} - {cached.title}.mp3"
                    )
                    sent_audio = await callback.message.answer_audio(
                        audio=fallback_file,
                        title=cached.title,
                        performer=cached.artist,
                        caption=f"🎵 {cached.artist} — {cached.title}"
                    )
                else:
                    sent_audio = None
                    await callback.message.answer("⚠️ Audio fayl hajmi juda katta, yuborib bo'lmadi.")
            except Exception:
                sent_audio = None
                doc_file = FSInputFile(send_path, filename=filename)
                await callback.message.answer_document(
                    document=doc_file,
                    caption=f"🎵 {cached.artist} — {cached.title}"
                )
            
            # Update cache with file_id
            if sent_audio and sent_audio.audio:
                cached.audio_file_id = sent_audio.audio.file_id
                await recognition_service.cache_result(full_hash, cached)
                await _set_cached_track_audio_file_id(cached, sent_audio.audio.file_id)
            await status_msg.delete()
        else:
            await _safe_edit_text(status_msg, translator.get("recog_error", user.language))
    except Exception as e:
        logger.error(f"Manual download error: {e}")
        await _safe_edit_text(status_msg, "⚠️ Download failed.")
    finally:
        if music_path:
            audio_extractor.cleanup(music_path)
        if extra_cleanup_paths:
            audio_extractor.cleanup(*extra_cleanup_paths)

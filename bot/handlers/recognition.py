import os
import uuid
import asyncio
import logging
from aiogram import Router, F, types
from aiogram.types import FSInputFile
from bot.services.audio_extractor import audio_extractor
from bot.services.recognition_service import recognition_service
from bot.database.models import User
from bot.database.session import Database
from bot.config import config
import aiohttp

router = Router()
logger = logging.getLogger(__name__)


from bot.utils.i18n import translator

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

    if not buttons:
        return None
    return types.InlineKeyboardMarkup(inline_keyboard=buttons)


async def _download_telegram_file(bot, file_id: str) -> str:
    file = await bot.get_file(file_id)
    
    # Check file size before downloading (Telegram bot limit is 20MB)
    if file.file_size and file.file_size > 20 * 1024 * 1024:  # 20MB
        raise ValueError(f"File too large: {file.file_size / (1024*1024):.1f}MB (max 20MB)")
    
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
    """Search YouTube for the recognized song and download as MP3 with tags."""
    title = result.title
    artist = result.artist
    # Professional search query for better high-quality matches
    query = f"{artist} {title} official high quality audio"
    output_path = os.path.join(config.DOWNLOAD_DIR, f"{uuid.uuid4()}.mp3")

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_path.replace('.mp3', '.%(ext)s'),
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'default_search': 'ytsearch1',
        'socket_timeout': 30,
    }

    try:
        import yt_dlp
        loop = asyncio.get_event_loop()

        def _download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(query, download=True)
                if 'entries' in info:
                    info = info['entries'][0]
                return {
                    'title': info.get('title', title),
                    'duration': info.get('duration', 0),
                    'uploader': info.get('uploader', artist),
                }

        dl_result = await loop.run_in_executor(None, _download)

        actual_path = output_path
        if not os.path.exists(actual_path):
            base = output_path.replace('.mp3', '')
            for ext in ['.mp3', '.m4a', '.opus', '.webm']:
                if os.path.exists(base + ext):
                    actual_path = base + ext
                    break

        if os.path.exists(actual_path):
            # Apply Professional Tagging
            await _tag_mp3_file(actual_path, result)
            
            dl_result['file_path'] = actual_path
            return dl_result

        return None
    except Exception as e:
        logger.error(f"YouTube music download error: {e}")
        return None


async def _process_recognition(message: types.Message, file_id: str, user: User, db: Database | None = None):
    """Recognition pipeline with dynamic sampling and confidence-based pick."""
    status_msg = await message.answer(translator.get("recog_status", user.language))
    local_path = None
    music_path = None
    temp_audio_paths: list[str] = []

    try:
        await status_msg.edit_text(translator.get("recog_downloading", user.language))
        local_path = await _download_telegram_file(message.bot, file_id)

        media_duration = await audio_extractor.probe_duration(local_path)
        samples = _build_sample_plan(media_duration)

        best_result = None
        best_hash = None
        best_score = -1
        votes: dict[str, int] = {}
        seen_hashes = set()

        for i, sample in enumerate(samples, start=1):
            await status_msg.edit_text(f"{translator.get('recog_shazam', user.language)} ({i}/{len(samples)})...")

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
            await status_msg.edit_text(translator.get("recog_not_found", user.language))
            return

        result = best_result
        audio_hash = best_hash

        if recognition_service.redis and audio_hash:
            prefix = audio_hash[:16]
            await recognition_service.redis.set(f"rec_prefix:{prefix}", audio_hash, ex=86400)
            await recognition_service.redis.set(f"ly_prefix:{prefix}", audio_hash, ex=86400)

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

        await status_msg.edit_text(translator.get("recog_download_music", user.language))
        music = await _download_music_from_youtube(result)

        if music and music.get("file_path"):
            music_path = music["file_path"]
            filename = f"{result.artist} - {result.title}.mp3"
            audio_file = FSInputFile(music_path, filename=filename)

            sent_audio = await message.answer_audio(
                audio=audio_file,
                title=result.title,
                performer=result.artist,
                caption=f"🎵 {result.artist} — {result.title}"
            )

            if sent_audio.audio and audio_hash:
                result.audio_file_id = sent_audio.audio.file_id
                await recognition_service.cache_result(audio_hash, result)
        else:
            await message.answer(translator.get("recog_error", user.language))

        await status_msg.delete()

    except Exception as e:
        logger.error(f"Recognition pipeline error: {e}", exc_info=True)
        try:
            await status_msg.edit_text("⚠️ Error.")
        except Exception:
            pass
    finally:
        audio_extractor.cleanup(local_path, *temp_audio_paths)
        if music_path:
            audio_extractor.cleanup(music_path)


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

    await callback.answer(translator.get("downloading", user.language))
    status_msg = await callback.message.answer(translator.get("recog_download_music", user.language))
    
    music_path = None
    try:
        music = await _download_music_from_youtube(cached)
        if music and music.get('file_path'):
            music_path = music['file_path']
            filename = f"{cached.artist} - {cached.title}.mp3"
            audio_file = FSInputFile(music_path, filename=filename)

            sent_audio = await callback.message.answer_audio(
                audio=audio_file,
                title=cached.title,
                performer=cached.artist,
                caption=f"🎵 {cached.artist} — {cached.title}"
            )
            
            # Update cache with file_id
            cached.audio_file_id = sent_audio.audio.file_id
            await recognition_service.cache_result(full_hash, cached)
            await status_msg.delete()
        else:
            await status_msg.edit_text(translator.get("recog_error", user.language))
    except Exception as e:
        logger.error(f"Manual download error: {e}")
        await status_msg.edit_text("⚠️ Download failed.")
    finally:
        if music_path:
            audio_extractor.cleanup(music_path)

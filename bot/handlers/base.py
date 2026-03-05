import os
import hashlib
import logging
from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from bot.services.downloader import downloader
from bot.services.caching import cache_service
from bot.services.lock_service import lock_service
from bot.services.video_service import video_service
from bot.database.models import User
from bot.database.session import Database
from bot.utils.keyboards import get_main_keyboard, get_download_keyboard, get_lang_keyboard
from bot.utils.i18n import translator
from bot.config import config

router = Router()
logger = logging.getLogger(__name__)
UPLOAD_CHUNK_SIZE_BYTES = max(64 * 1024, config.UPLOAD_CHUNK_SIZE_KB * 1024)

def _build_input_file(path: str):

    from aiogram.types import FSInputFile
    return FSInputFile(path, chunk_size=UPLOAD_CHUNK_SIZE_BYTES)

def _escape_markdown(text: str) -> str:
    """Escape user-generated text for legacy Markdown parse mode."""
    if not text:
        return ""
    escaped = text
    for ch in ("\\", "_", "*", "`", "["):
        escaped = escaped.replace(ch, f"\\{ch}")
    return escaped

@router.message(Command("start"))
async def cmd_start(message: types.Message, user: User):
    safe_name = _escape_markdown(user.full_name or "Friend")
    welcome_text = translator.get("welcome", user.language, name=safe_name)
    await message.answer(welcome_text, reply_markup=get_main_keyboard(user))

@router.message(Command("lang"))
async def cmd_lang(message: types.Message, user: User):
    await message.answer("🌐 Tilni tanlang / Выберите язык / Select language:", reply_markup=get_lang_keyboard())

@router.callback_query(F.data.startswith("setlang:"))
async def handle_set_language(callback: types.CallbackQuery, user: User, db: Database, redis_client=None):
    lang = callback.data.split(":")[1]
    await db.set_user_language(user.id, lang)
    
    # Invalidate Cache
    if redis_client:
        await redis_client.delete(f"user:{user.id}")
    
    await callback.message.edit_text(f"✅ Til o'zgartirildi / Язык изменен / Language changed to: {lang.upper()}")
    await callback.answer()

@router.callback_query(F.data == "check_sub")
async def handle_check_sub(callback: types.CallbackQuery, user: User):
    """If they reach here, it means middleware passed, so they joined."""
    await callback.answer("✅ Rahmat! Endi botdan foydalanishingiz mumkin.", show_alert=True)
    await callback.message.delete()

@router.message(F.text.in_([
    "👥 Referal", "👥 Рефералы", "👥 Referral", "🎁 Taklif qilish"
]))
async def handle_referral_menu(message: types.Message, user: User):
    bot_info = await message.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user.id}"
    text = translator.get(
        "referral_title", user.language, 
        link=ref_link, 
        count=user.referral_count
    )
    await message.answer(text)

@router.message(F.text.in_([
    "👤 Profil", "👤 Профиль", "👤 Profile"
]))
async def handle_profile_menu(message: types.Message, user: User, db: Database):
    # Get user specific stats
    user_dl_count = await db.get_user_download_count(user.id)

    text = translator.get(
        "profile_title", user.language,
        id=user.id,
        name=_escape_markdown(user.full_name or ""),
        lang=user.language.upper(),
        ref_count=user.referral_count,
        dl_count=user_dl_count
    )
    
    # Web Profile button
    kb = None
    if config.WEBHOOK_HOST:
        web_url = f"{config.WEBHOOK_HOST}/profile"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=translator.get("btn_web_profile", user.language), web_app=WebAppInfo(url=web_url))]
        ])
        
    await message.answer(text, reply_markup=kb)

@router.message(F.text.in_([
    "📊 Statistika", "📊 Статистика", "📊 Statistics"
]))
async def user_stats_redirect(message: types.Message, user: User, db: Database):
    await handle_profile_menu(message, user, db)

@router.message(F.text.in_([
    "🎵 Musiqa aniqlash rejimi", "🎵 Musiqa aniqlash", 
    "🎵 Режим распознавания музыки", "🎵 Распознавание музыки",
    "🎵 Music Recognition Mode", "🎵 Music Recognition"
]))
async def music_recognition_prompt(message: types.Message, user: User, **data):
    await message.answer(translator.get("music_mode_info", user.language))

@router.message(F.text.in_([
    "❓ Yordam", "❓ Помощь", "❓ Help"
]))
async def cmd_help(message: types.Message, user: User):
    await message.answer(translator.get("help", user.language))

@router.message(F.text.regexp(r'(https?://[^\s]+)'))
async def handle_url(message: types.Message, user: User, db: Database, **data):
    url = message.text.strip()
    redis = data.get('redis_client')
    q_key = hashlib.md5(url.encode()).hexdigest()[:12]
    if redis:
        await redis.set(f"v_url:{q_key}", url, ex=3600)

    status_msg = await message.answer(translator.get("downloading", user.language))
    
    try:
        # 1. Cache Check — instant response if cached
        cached = await cache_service.get_cached_file(url)
        if cached:
            safe_title = _escape_markdown(cached.title or "Video")
            await message.reply_video(
                video=cached.file_id,
                caption=f"✅ **{safe_title}**\n\n📱 Platforma: {cached.platform}\n⚡️ Kesh",
                reply_markup=get_download_keyboard(q_key)
            )
            await db.increment_download(user.id, cached.platform, url, cached.file_id)
            await status_msg.delete()
            return

        # 2. FAST single-pass download (no separate get_info call)
        max_bytes = config.MAX_VIDEO_SIZE_MB * 1024 * 1024
        result = await downloader.fast_download(url, max_size_mb=config.MAX_VIDEO_SIZE_MB)

        # Fallback to standard download if fast_download fails
        if not result or result.get("error"):
            result = await downloader.download(url, format_id=None, max_size_mb=config.MAX_VIDEO_SIZE_MB)

        if not result or "file_path" not in result:
            error_text = (result or {}).get("error", "")
            if "too large" in error_text.lower():
                await status_msg.edit_text(f"❌ Fayl juda katta. Maksimal ruxsat etilgan hajm: {config.MAX_VIDEO_SIZE_MB}MB.")
            else:
                await status_msg.edit_text("❌ Video yuklab bo'lmadi. Havola yaroqsiz yoki video cheklangan bo'lishi mumkin.")
            return

        from aiogram.exceptions import TelegramBadRequest

        if not os.path.exists(result["file_path"]):
            await status_msg.edit_text("❌ Fayl topilmadi. Iltimos, qayta urinib ko'ring.")
            return

        if result.get("filesize", 0) > max_bytes:
            await status_msg.edit_text(f"❌ Fayl juda katta. Maksimal ruxsat etilgan hajm: {config.MAX_VIDEO_SIZE_MB}MB.")
            if os.path.exists(result["file_path"]):
                os.remove(result["file_path"])
            return

        await status_msg.edit_text(translator.get("uploading", user.language))
        media_file = _build_input_file(result["file_path"])
        safe_title = _escape_markdown(result.get('title') or 'Video')
        caption = f"✅ **{safe_title}**\n📱 Platforma: {result.get('platform') or 'Unknown'}"

        try:
            sent_msg = await message.answer_video(
                media_file,
                caption=caption,
                supports_streaming=True,
                reply_markup=get_download_keyboard(q_key)
            )
        except TelegramBadRequest as e:
            err = str(e).lower()
            if "too big" in err or "entity too large" in err:
                await status_msg.edit_text(f"❌ Fayl juda katta. Maksimal ruxsat etilgan hajm: {config.MAX_VIDEO_SIZE_MB}MB.")
            else:
                await status_msg.edit_text("❌ Video yuborishda xatolik yuz berdi.")
            if os.path.exists(result["file_path"]):
                os.remove(result["file_path"])
            return

        if sent_msg.video:
            file_id = sent_msg.video.file_id
            await cache_service.set_cache(url, file_id, result.get("platform") or "Generic", result.get("title"))
            await db.increment_download(user.id, result.get("platform") or "Generic", url, file_id)

        if os.path.exists(result["file_path"]):
            os.remove(result["file_path"])

        await status_msg.delete()

    except Exception as e:
        logger.error(f"Handle URL error: {e}", exc_info=True)
        error_msg = str(e)
        if "instagram" in error_msg.lower() and "empty media response" in error_msg.lower():
            await status_msg.edit_text("❌ Instagram videoni yuklab bo'lmadi. Video yoki profil maxfiy (private) bo'lishi mumkin.")
        elif "too large" in error_msg.lower():
            await status_msg.edit_text("❌ Video hajmi juda katta.")
        else:
            await status_msg.edit_text(translator.get("error_analysis", user.language))

@router.callback_query(F.data.startswith("dq:"))
async def handle_quality_selection(callback: types.CallbackQuery, user: User, db: Database, **data):
    """Start download with specific quality."""
    parts = callback.data.split(":")
    if len(parts) < 3: return
    
    q_key = parts[1]
    format_id = parts[2]
    
    redis = data.get('redis_client')
    if not redis:
        await callback.answer("⚠️ Redis Error.", show_alert=True)
        return

    url = await redis.get(f"v_url:{q_key}")
    if not url:
        await callback.answer("😔 Session expired.", show_alert=True)
        return

    await redis.set(f"v_url:{q_key}", url, ex=3600)

    await callback.message.edit_reply_markup(reply_markup=None)
    status_msg = await callback.message.answer(translator.get("downloading", user.language))
    
    url_hash = cache_service.get_url_hash(url)
    max_size = config.MAX_VIDEO_SIZE_MB
    
    try:
        # Parallel cache check and lock acquisition
        cached_task = asyncio.create_task(cache_service.get_cached_file(url))
        lock_task = asyncio.create_task(lock_service.acquire_distributed_lock(url_hash))
        
        cached, lock = await asyncio.gather(cached_task, lock_task)
        
        if cached:
            from aiogram.exceptions import TelegramBadRequest
            try:
                safe_title = _escape_markdown(cached.title or "Video")
                await callback.message.answer_video(
                    video=cached.file_id,
                    caption=f"✅ **{safe_title}**\n📱 {cached.platform}",
                    reply_markup=get_download_keyboard(q_key)
                )
                await db.increment_download(user.id, cached.platform, url, cached.file_id)
                delete_status = True
                return
            except TelegramBadRequest as e:
                logger.warning(f"Cached file send failed for {url_hash[:12]}: {e}")

        # Download
        await status_msg.edit_text(translator.get("downloading", user.language))
        result = await downloader.download(
            url, 
            format_id=format_id,
            max_size_mb=max_size
        )

        # Selected format may disappear between info and download
        if result and result.get("error"):
            err = result["error"].lower()
            if "requested format is not available" in err or "format is not available" in err:
                logger.warning(f"Format {format_id} unavailable, retrying best format for {url_hash[:12]}")
                result = await downloader.download(url, format_id=None, max_size_mb=max_size)
         
        if result and "file_path" in result:
            await status_msg.edit_text(translator.get("uploading", user.language))
            
            from aiogram.exceptions import TelegramBadRequest
            if not os.path.exists(result['file_path']):
                await status_msg.edit_text("❌ Fayl topilmadi. Iltimos, boshqa sifatni tanlang.")
                return
            media_file = _build_input_file(result['file_path'])
            is_audio = format_id == "audio" or result.get("is_audio", False)
            max_bytes = config.MAX_VIDEO_SIZE_MB * 1024 * 1024

            if result.get("filesize", 0) > max_bytes:
                await status_msg.edit_text(f"❌ Fayl juda katta. Maksimal ruxsat etilgan hajm: {config.MAX_VIDEO_SIZE_MB}MB.")
                if os.path.exists(result['file_path']):
                    os.remove(result['file_path'])
                return

            if is_audio:
                try:
                    sent_msg = await callback.message.answer_audio(
                        audio=media_file,
                        title=result.get('title') or 'Audio',
                        performer=result.get('uploader') or None,
                        caption=f"🎵 {result.get('title') or 'Audio'}"
                    )
                except TelegramBadRequest as e:
                    err = str(e).lower()
                    if "too big" in err or "entity too large" in err:
                        await status_msg.edit_text(f"❌ Fayl juda katta. Maksimal ruxsat etilgan hajm: {config.MAX_VIDEO_SIZE_MB}MB.")
                    else:
                        await status_msg.edit_text("❌ Audio yuborishda xatolik yuz berdi.")
                    if os.path.exists(result['file_path']):
                        os.remove(result['file_path'])
                    return

                if sent_msg.audio:
                    await db.increment_download(user.id, result['platform'], url, sent_msg.audio.file_id)
                delete_status = True
            else:
                try:
                    safe_title = _escape_markdown(result.get('title') or 'Video')
                    sent_msg = await callback.message.answer_video(
                        media_file,
                        caption=f"✅ **{safe_title}**\n📱 Platforma: {result['platform']}",
                        supports_streaming=True,
                        reply_markup=get_download_keyboard(q_key)
                    )
                except TelegramBadRequest as e:
                    err = str(e).lower()
                    if "too big" in err or "entity too large" in err:
                        await status_msg.edit_text(f"❌ Fayl juda katta. Maksimal ruxsat etilgan hajm: {config.MAX_VIDEO_SIZE_MB}MB.")
                    else:
                        await status_msg.edit_text("❌ Video yuborishda xatolik yuz berdi. Boshqa sifatni tanlab ko'ring.")
                    if os.path.exists(result['file_path']):
                        os.remove(result['file_path'])
                    return

                if sent_msg.video:
                    file_id = sent_msg.video.file_id
                    await cache_service.set_cache(url, file_id, result['platform'], result['title'])
                    await db.increment_download(user.id, result['platform'], url, file_id)
                    delete_status = True
                
            if os.path.exists(result['file_path']):
                os.remove(result['file_path'])
        else:
            error_text = (result or {}).get('error', 'Error.')
            if "too large" in error_text.lower():
                await status_msg.edit_text(f"❌ Fayl juda katta. Maksimal ruxsat etilgan hajm: {config.MAX_VIDEO_SIZE_MB}MB.")
            else:
                await status_msg.edit_text(f"❌ {error_text}")

    except Exception as e:
        logger.error(f"Quality download error: {e}", exc_info=True)
        await status_msg.edit_text("❌ Yuklashda xatolik yuz berdi. Boshqa sifatni tanlab ko'ring.")
    finally:
        if delete_status:
            try:
                await status_msg.delete()
            except Exception:
                pass

@router.callback_query(F.data == "download_audio")
async def legacy_download_audio(callback: types.CallbackQuery):
    await callback.answer("Bu eski tugma. Iltimos, havolani qayta yuboring.", show_alert=True)


# ─── Video Note Conversion ──────────────────────────────

@router.callback_query(F.data.startswith("cvn:"))
async def handle_video_note_conversion(callback: types.CallbackQuery, user: User, **data):
    """Convert a previously sent video into a Telegram Video Note (Round Video)."""
    parts = callback.data.split(":")
    if len(parts) < 2: return
    
    q_key = parts[1]
    
    # We need the original video from the message that has the button
    msg = callback.message
    if not msg.video:
        await callback.answer("❌ Video topilmadi.", show_alert=True)
        return

    await callback.answer(translator.get("converting_video_note", user.language))
    status_msg = await msg.answer(translator.get("converting_video_note", user.language))
    
    local_path = None
    note_path = None
    
    try:
        # 1. Download the video from Telegram servers
        from bot.handlers.recognition import _download_telegram_file
        local_path = await _download_telegram_file(msg.bot, msg.video.file_id)
        
        # 2. Convert to Video Note
        note_path = await video_service.to_video_note(local_path)
        
        if not note_path or not os.path.exists(note_path):
            await status_msg.edit_text("❌ Konvertatsiya xatosi.")
            return

        # 3. Send as Video Note
        from aiogram.types import FSInputFile
        note_file = FSInputFile(note_path)
        
        await msg.answer_video_note(
            video_note=note_file
        )
        
        await status_msg.delete()

    except ValueError as e:
        if "too large" in str(e):
            await status_msg.edit_text("❌ Video hajmi juda katta (20MB dan oshiq). Dumaloq video uchun kichikroq video yuboring.")
        else:
            await status_msg.edit_text(f"❌ Xatolik: {str(e)}")
    except Exception as e:
        logger.error(f"Video Note conversion error: {e}", exc_info=True)
        await status_msg.edit_text("⚠️ Xatolik yuz berdi.")
    finally:
        # Cleanup
        if local_path and os.path.exists(local_path):
            os.remove(local_path)
        if note_path and os.path.exists(note_path):
            os.remove(note_path)

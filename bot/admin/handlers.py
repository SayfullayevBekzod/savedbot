from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from bot.database.session import async_session, Database
from bot.config import config
from sqlalchemy import select
from bot.database.models import User
import csv
import os
import io

router = Router()

class AdminStates(StatesGroup):
    waiting_for_search = State()
    waiting_for_channel_data = State()

def get_admin_keyboard(lang: str):
    from bot.utils.i18n import translator as lm
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text=lm.get("btn_admin_stats", lang), callback_data="admin_stats"))
    builder.row(types.InlineKeyboardButton(text=lm.get("btn_admin_broadcast", lang), callback_data="admin_broadcast"))
    builder.row(types.InlineKeyboardButton(text=lm.get("btn_admin_search", lang), callback_data="admin_search"))
    builder.row(types.InlineKeyboardButton(text=lm.get("btn_admin_export", lang), callback_data="admin_export"))
    builder.row(types.InlineKeyboardButton(text=lm.get("btn_admin_channels", lang), callback_data="admin_channels"))
    return builder.as_markup()

@router.message(Command("admin"), F.from_user.id.in_(config.ADMIN_IDS))
async def cmd_admin(message: types.Message, db: Database):
    stats = await db.get_stats()
    lang = "uz" # Admin usually understands main bot lang
    from bot.utils.i18n import translator as lm
    
    await message.answer(
        lm.get("admin_welcome", lang, users=stats['users'], downloads=stats['downloads']),
        reply_markup=get_admin_keyboard(lang)
    )

@router.callback_query(F.data == "admin_stats", F.from_user.id.in_(config.ADMIN_IDS))
async def handle_stats(callback: types.CallbackQuery, db: Database):
    details = await db.get_detailed_stats()
    text = "📊 **Platform Breakdown:**\n"
    for p, c in details['platforms'].items():
        text += f" - {p}: {c}\n"
    
    text += "\n📈 **Growth (Last 7 days):**\n"
    for d, c in details['growth'].items():
        text += f" - {d}: +{c}\n"
        
    await callback.message.edit_text(text, reply_markup=get_admin_keyboard("uz"))

@router.callback_query(F.data == "admin_search", F.from_user.id.in_(config.ADMIN_IDS))
async def start_search(callback: types.CallbackQuery, state: FSMContext):
    from bot.utils.i18n import translator as lm
    await callback.message.answer(lm.get("admin_search_prompt", "uz"))
    await state.set_state(AdminStates.waiting_for_search)
    await callback.answer()

@router.message(AdminStates.waiting_for_search, F.from_user.id.in_(config.ADMIN_IDS))
async def process_search(message: types.Message, state: FSMContext, db: Database):
    from bot.utils.i18n import translator as lm
    users = await db.search_users(message.text)
    
    if not users:
        await message.answer(lm.get("admin_user_not_found", "uz"))
        await state.clear()
        return
        
    for user in users:
        dl_count = await db.get_user_download_count(user.id)
        status = "🚫 Blocked" if user.is_blocked else "✅ Active"
        await message.answer(
            lm.get("admin_user_info", "uz", 
                   id=user.id, name=user.full_name, lang=user.language, 
                   joined=user.joined_at.strftime("%Y-%m-%d"), dl_count=dl_count, status=status)
        )
    await state.clear()

@router.callback_query(F.data == "admin_export", F.from_user.id.in_(config.ADMIN_IDS))
async def handle_export(callback: types.CallbackQuery, db: Database):
    users = await db.get_all_users()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Username", "Full Name", "Language", "Joined At", "Blocked"])
    
    for u in users:
        writer.writerow([u.id, u.username, u.full_name, u.language, u.joined_at, u.is_blocked])
    
    output.seek(0)
    file_content = output.getvalue().encode('utf-8')
    
    document = types.BufferedInputFile(file_content, filename="users_export.csv")
    await callback.message.answer_document(document, caption=f"📁 Jami {len(users)} ta foydalanuvchi ro'yxati.")
    await callback.answer()

@router.callback_query(F.data == "admin_channels", F.from_user.id.in_(config.ADMIN_IDS))
async def handle_channels_list(callback: types.CallbackQuery, db: Database):
    from bot.utils.i18n import translator as lm
    channels = await db.get_sponsor_channels()
    
    builder = InlineKeyboardBuilder()
    text = lm.get("admin_channels_welcome", "uz") + "\n\n"
    
    for ch in channels:
        text += f"🔹 {ch.title} ({ch.username or ch.channel_id})\n"
        builder.row(types.InlineKeyboardButton(
            text=f"🗑 {ch.title}", 
            callback_data=f"del_chan:{ch.channel_id}"
        ))
    
    builder.row(types.InlineKeyboardButton(text=lm.get("btn_add_channel", "uz"), callback_data="add_channel"))
    builder.row(types.InlineKeyboardButton(text="⬅️ Back", callback_data="admin_back"))
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())

@router.callback_query(F.data == "add_channel", F.from_user.id.in_(config.ADMIN_IDS))
async def start_add_channel(callback: types.CallbackQuery, state: FSMContext):
    from bot.utils.i18n import translator as lm
    await callback.message.answer(lm.get("admin_channel_add_prompt", "uz"))
    await state.set_state(AdminStates.waiting_for_channel_data)
    await callback.answer()

@router.message(AdminStates.waiting_for_channel_data, F.from_user.id.in_(config.ADMIN_IDS))
async def process_add_channel(message: types.Message, state: FSMContext, db: Database):
    from bot.utils.i18n import translator as lm
    
    try:
        parts = [p.strip() for p in message.text.split("|")]
        if len(parts) < 2:
            raise ValueError()
            
        c_id = parts[0]
        title = parts[1]
        username = parts[2] if len(parts) > 2 and parts[2].lower() != "none" else None
        invite_link = parts[3] if len(parts) > 3 and parts[3].lower() != "none" else None
        
        await db.add_sponsor_channel(c_id, title, username, invite_link)
        await message.answer(lm.get("admin_channel_added", "uz"))
        await state.clear()
        
    except Exception:
        await message.answer(lm.get("admin_channel_invalid_format", "uz"))

@router.callback_query(F.data.startswith("del_chan:"), F.from_user.id.in_(config.ADMIN_IDS))
async def handle_delete_channel(callback: types.CallbackQuery, db: Database):
    from bot.utils.i18n import translator as lm
    channel_id = callback.data.split(":")[1]
    await db.delete_sponsor_channel(channel_id)
    await callback.answer(lm.get("admin_channel_deleted", "uz"), show_alert=True)
    await handle_channels_list(callback, db)

@router.callback_query(F.data == "admin_back", F.from_user.id.in_(config.ADMIN_IDS))
async def handle_admin_back(callback: types.CallbackQuery, db: Database):
    stats = await db.get_stats()
    from bot.utils.i18n import translator as lm
    await callback.message.edit_text(
        lm.get("admin_welcome", "uz", users=stats['users'], downloads=stats['downloads']),
        reply_markup=get_admin_keyboard("uz")
    )

@router.callback_query(F.data == "admin_broadcast", F.from_user.id.in_(config.ADMIN_IDS))
async def handle_broadcast_info(callback: types.CallbackQuery):
    await callback.answer("📢 `/broadcast [text]` or reply to any message with `/broadcast`", show_alert=True)

@router.message(Command("broadcast"), F.from_user.id.in_(config.ADMIN_IDS))
async def cmd_broadcast(message: types.Message, db: Database, arq_redis=None):
    if not arq_redis:
        await message.answer("⚠️ Worker (arq) is not connected.")
        return

    target_msg = message.reply_to_message if message.reply_to_message else message
    
    if target_msg == message and not message.text.split(maxsplit=1)[1:]:
        await message.answer("⚠️ Please provide text or reply to a message.")
        return

    users = await db.get_all_users()
    user_ids = [u.id for u in users]

    if not user_ids:
        await message.answer("⚠️ No users found.")
        return

    await arq_redis.enqueue_job(
        'broadcast_task',
        from_chat_id=target_msg.chat.id,
        message_id=target_msg.message_id,
        user_ids=user_ids
    )
    
    await message.answer(f"🚀 **Broadcast started!**\n\nTotal: {len(user_ids)} users.")

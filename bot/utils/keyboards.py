from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from bot.database.models import User

from bot.utils.i18n import translator

def get_main_keyboard(user: User) -> ReplyKeyboardMarkup:
    kb = [
        [
            KeyboardButton(text=translator.get("btn_music_mode", user.language)),
        ],
        [
            KeyboardButton(text=translator.get("btn_profile", user.language)),
            KeyboardButton(text=translator.get("btn_referral", user.language))
        ],
        [
            KeyboardButton(text=translator.get("help", user.language).split("\n")[0]) # "❓ Yordam"
        ]
    ]
    return ReplyKeyboardMarkup(
        keyboard=kb,
        resize_keyboard=True,
        input_field_placeholder="Havola yoki audio yuboring..."
    )

def get_download_keyboard(q_key: str) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="🎵 Musiqani yuklash (MP3)", callback_data=f"dq:{q_key}:audio")
        ],
        [
            InlineKeyboardButton(text="🎶 Musiqani aniqlash", callback_data="recognize_music"),
            InlineKeyboardButton(text="📹 Dumaloq video", callback_data=f"cvn:{q_key}")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def format_bytes(size: int) -> str:
    """Format bytes to human readable string."""
    if not size: return ""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"

def get_quality_keyboard(q_key: str, formats: list) -> InlineKeyboardMarkup:
    """Generate keyboard for video quality selection."""
    buttons = []
    
    # Sort formats by height (descending)
    sorted_fmts = sorted(formats, key=lambda x: x.get('height', 0), reverse=True)
    
    for f in sorted_fmts:
        label = f"📂 {f['height']}p"
        size = format_bytes(f.get('filesize'))
        if size:
            label += f" ({size})"
            
        # callback_data: dq:[q_key]:[format_id]
        buttons.append([
            InlineKeyboardButton(
                text=label, 
                callback_data=f"dq:{q_key}:{f['format_id']}"
            )
        ])
    
    # Add Audio extra button
    buttons.append([
        InlineKeyboardButton(text="🎵 Faqat audio (MP3)", callback_data=f"dq:{q_key}:audio")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_lang_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for language selection."""
    buttons = [
        [
            InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="setlang:uz"),
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="setlang:ru"),
        ],
        [
            InlineKeyboardButton(text="🇺🇸 English", callback_data="setlang:en")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

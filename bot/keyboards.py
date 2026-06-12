"""
Клавіатури для Telegram-бота "Жива Аптека".
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton("💡 Приклади запитів", callback_data="examples"),
            InlineKeyboardButton("📊 Статистика", callback_data="stats"),
        ],
        [
            InlineKeyboardButton("ℹ️ Довідка", callback_data="help"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


def back_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("🏠 Головне меню", callback_data="back")],
    ]
    return InlineKeyboardMarkup(buttons)

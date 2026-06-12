"""
Інлайн-клавіатури для Telegram-бота "Жива Аптека".
Всі callback_data константи визначені тут для уникнення помилок при введенні.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# ─── Константи callback_data ──────────────────────────────────────────────────
CALLBACK_HELP = "help"
CALLBACK_EXAMPLES = "examples"
CALLBACK_STATS = "stats"
CALLBACK_BACK = "back"
CALLBACK_ABOUT = "about"
CALLBACK_DISCLAIMER = "disclaimer"


# ─── Клавіатури ───────────────────────────────────────────────────────────────

def main_menu_keyboard() -> InlineKeyboardMarkup:
    """
    Головне меню бота.
    Відображається після відповіді на запит або після /start.
    """
    buttons = [
        [
            InlineKeyboardButton("💡 Приклади запитів", callback_data=CALLBACK_EXAMPLES),
            InlineKeyboardButton("📊 Статистика", callback_data=CALLBACK_STATS),
        ],
        [
            InlineKeyboardButton("ℹ️ Довідка", callback_data=CALLBACK_HELP),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


def back_keyboard() -> InlineKeyboardMarkup:
    """
    Клавіатура з кнопкою повернення до головного меню.
    Використовується на сторінках довідки, прикладів тощо.
    """
    buttons = [
        [InlineKeyboardButton("🏠 Головне меню", callback_data=CALLBACK_BACK)],
    ]
    return InlineKeyboardMarkup(buttons)


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Псевдонім для main_menu_keyboard() для зручності імпорту."""
    return main_menu_keyboard()


def get_back_keyboard() -> InlineKeyboardMarkup:
    """Псевдонім для back_keyboard() для зручності імпорту."""
    return back_keyboard()

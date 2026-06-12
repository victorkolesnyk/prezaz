"""
Точка входу для Telegram-бота "Жива Аптека".
Ініціалізує додаток, реєструє обробники та запускає бот.
"""

import logging
import sys
import os

# Додаємо корінь проєкту до шляху пошуку модулів
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from config.settings import settings
from bot.handlers import (
    start_handler,
    help_handler,
    text_message_handler,
    callback_query_handler,
    error_handler,
    stats_handler,
)

# Налаштування логування
logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)

# Вимикаємо зайві логи сторонніх бібліотек
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("chromadb").setLevel(logging.WARNING)
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


def build_application() -> Application:
    """
    Створює та налаштовує об'єкт Application з усіма обробниками.

    Returns:
        Налаштований екземпляр Application
    """
    logger.info(f"Запуск бота «{settings.bot_name}»...")

    # Створюємо додаток
    application = (
        Application.builder()
        .token(settings.telegram_token)
        .build()
    )

    # --- Реєстрація обробників команд ---
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("help", help_handler))
    application.add_handler(CommandHandler("stats", stats_handler))

    # --- Обробник натискань інлайн-кнопок ---
    application.add_handler(CallbackQueryHandler(callback_query_handler))

    # --- Обробник текстових повідомлень ---
    # Обробляє будь-який текст, що не є командою
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler)
    )

    # --- Обробник помилок ---
    application.add_error_handler(error_handler)

    logger.info("Усі обробники зареєстровано успішно")
    return application


def main() -> None:
    """Головна функція запуску бота."""
    application = build_application()

    logger.info("Бот запущено. Очікування повідомлень...")
    logger.info("Для зупинки натисніть Ctrl+C")

    # Запускаємо бота в режимі polling
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,  # Ігноруємо повідомлення, що прийшли під час паузи
    )


if __name__ == "__main__":
    main()

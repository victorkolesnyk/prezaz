"""
Обробники повідомлень та команд Telegram-бота "Жива Аптека".
Кожен handler отримує Update від Telegram та викликає відповідну логіку.
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode, ChatAction

from bot.keyboards import main_menu_keyboard, back_keyboard
from rag.retriever import get_retriever

logger = logging.getLogger(__name__)

# ─── Тексти повідомлень ────────────────────────────────────────────────────────

WELCOME_TEXT = (
    "🌿 *Вітаю у «Живій Аптеці»!*\n\n"
    "Я — ваш персональний фіто-помічник на основі українських лікарських книг.\n\n"
    "Запитайте мене про:\n"
    "• Лікарські рослини та їхні властивості\n"
    "• Народні рецепти від різних захворювань\n"
    "• Способи приготування трав'яних настоїв та відварів\n"
    "• Протипоказання та застереження\n\n"
    "Просто напишіть своє питання! 👇"
)

HELP_TEXT = (
    "ℹ️ *Довідка по «Живій Аптеці»*\n\n"
    "*Команди:*\n"
    "/start — Головне меню\n"
    "/help — Ця довідка\n"
    "/stats — Статистика бази знань\n\n"
    "*Як користуватися:*\n"
    "Просто напишіть питання українською мовою — бот знайде "
    "відповідну інформацію у своїй базі знань.\n\n"
    "*Приклади запитів:*\n"
    "• _Ромашка при застуді_\n"
    "• _Як заварити звіробій_\n"
    "• _Трави від безсоння_\n"
    "• _Валеріана протипоказання_\n"
    "• _Лікування болю в шлунку травами_\n\n"
    "⚠️ _Інформація носить довідковий характер. "
    "Перед застосуванням проконсультуйтеся з лікарем._"
)

EXAMPLES_TEXT = (
    "💡 *Приклади запитів:*\n\n"
    "*Про конкретні рослини:*\n"
    "• Ромашка при застуді\n"
    "• Як заварити звіробій\n"
    "• Властивості календули\n"
    "• Меліса заспокійливе\n\n"
    "*Про симптоми та хвороби:*\n"
    "• Трави від безсоння\n"
    "• Валеріана протипоказання\n"
    "• Лікування шлунку травами\n"
    "• Калина від тиску\n\n"
    "*Про приготування:*\n"
    "• Як зробити відвар з ромашки\n"
    "• Рецепт грудного збору\n"
    "• Скільки настоювати траву"
)


# ─── Обробники команд ─────────────────────────────────────────────────────────

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обробник команди /start. Показує привітальне повідомлення та головне меню."""
    user = update.effective_user
    logger.info(f"Команда /start від користувача {user.id} (@{user.username})")

    await update.message.reply_text(
        WELCOME_TEXT,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard(),
    )


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обробник команди /help. Показує довідкову інформацію."""
    user = update.effective_user
    logger.info(f"Команда /help від користувача {user.id}")

    await update.message.reply_text(
        HELP_TEXT,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=back_keyboard(),
    )


async def stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обробник команди /stats — показує статистику бази знань."""
    user = update.effective_user
    logger.info(f"Команда /stats від користувача {user.id}")

    try:
        retriever = get_retriever()
        stats = retriever.get_stats()
        text = (
            "📊 *Статистика бази знань:*\n\n"
            f"• Колекція: `{stats['collection_name']}`\n"
            f"• Документів: `{stats['total_documents']}`\n"
            f"• Модель: `{stats['embedding_model']}`\n"
            f"• Top-K: `{stats['top_k']}`\n"
            f"• Поріг схожості: `{stats['similarity_threshold']}`"
        )
    except Exception as e:
        logger.error(f"Помилка при отриманні статистики: {e}")
        text = "⚠️ Не вдалося отримати статистику бази знань."

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=back_keyboard(),
    )


# ─── Основний обробник текстових повідомлень ──────────────────────────────────

async def text_message_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Головний обробник текстових повідомлень.
    Передає запит до RAG-системи та повертає відповідь користувачу.
    """
    user = update.effective_user
    query = update.message.text.strip()

    if not query:
        await update.message.reply_text("Будь ласка, введіть запитання текстом.")
        return

    if len(query) < 3:
        await update.message.reply_text(
            "Запит задто короткий. Спробуйте написати повніше питання.",
            reply_markup=main_menu_keyboard(),
        )
        return

    logger.info(
        f"Запит від {user.id}: '{query[:80]}...'"
        if len(query) > 80
        else f"Запит від {user.id}: '{query}'"
    )

    # Показуємо індикатор набору тексту
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING,
    )

    # Відправляємо повідомлення "шукаю..."
    thinking_msg = await update.message.reply_text("🔍 Шукаю інформацію в базі знань...")

    try:
        retriever = get_retriever()
        response = retriever.retrieve(query)
        answer = response.format_for_telegram()
    except Exception as e:
        logger.error(f"Помилка ретривера: {e}", exc_info=True)
        answer = "⚠️ Виникла технічна помилка. Спробуйте ще раз пізніше."

    # Редагуємо повідомлення "шукаю..." на реальну відповідь
    await thinking_msg.edit_text(
        answer,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard(),
    )


# ─── Обробник інлайн-кнопок ───────────────────────────────────────────────────

async def callback_query_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Обробник натискань на інлайн-кнопки."""
    query = update.callback_query
    await query.answer()  # Знімаємо індикатор завантаження на кнопці

    data = query.data
    logger.info(f"Callback від {query.from_user.id}: '{data}'")

    if data == "help":
        await query.edit_message_text(
            HELP_TEXT,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=back_keyboard(),
        )

    elif data == "examples":
        await query.edit_message_text(
            EXAMPLES_TEXT,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=back_keyboard(),
        )

    elif data == "stats":
        try:
            retriever = get_retriever()
            stats = retriever.get_stats()
            text = (
                "📊 *Статистика бази знань:*\n\n"
                f"• Колекція: `{stats['collection_name']}`\n"
                f"• Документів: `{stats['total_documents']}`\n"
                f"• Модель: `{stats['embedding_model']}`\n"
                f"• Top-K: `{stats['top_k']}`\n"
                f"• Поріг схожості: `{stats['similarity_threshold']}`"
            )
        except Exception as e:
            logger.error(f"Помилка статистики: {e}")
            text = "⚠️ Не вдалося отримати статистику."
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=back_keyboard(),
        )

    elif data == "back":
        await query.edit_message_text(
            WELCOME_TEXT,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu_keyboard(),
        )

    else:
        logger.warning(f"Невідомий callback: '{data}'")
        await query.edit_message_text(
            "Невідома дія. Спробуйте /start",
            reply_markup=main_menu_keyboard(),
        )


# ─── Обробник помилок ─────────────────────────────────────────────────────────

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Глобальний обробник помилок. Логує виключення та повідомляє користувача."""
    logger.error(
        f"Виняток при обробці оновлення: {context.error}",
        exc_info=context.error,
    )

    # Намагаємося повідомити користувача про помилку
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "⚠️ Виникла непередбачена помилка. Спробуйте ще раз пізніше.",
            )
        except Exception:
            pass  # Якщо не вдалося — мовчки ігноруємо

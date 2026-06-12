import os
import base64
import logging
from collections import defaultdict

import anthropic
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

SYSTEM_PROMPT = """Ти — Жива Аптека, персональний фіто-консультант на основі українських лікарських книг: Кархут "Ліки навколо нас", Носаль "Лікарські рослини і способи їх застосування в народі", "Довідник з фітотерапії" та "Дари лісу".

Твоя роль:
- Надавати точну інформацію про лікарські рослини та їх властивості
- Пояснювати способи приготування і застосування рослинних препаратів
- Описувати показання, протипоказання та можливі побічні ефекти
- Давати поради щодо збору, зберігання та заготівлі рослин

Правила:
- Відповідай виключно українською мовою
- Посилайся на конкретні рослини та їх народні назви
- Завжди наголошуй, що фітотерапія є доповненням, а не заміною лікарської допомоги
- За серйозних симптомів рекомендуй звертатися до лікаря
- Якщо на фото рослина — визнач її та надай фітотерапевтичну інформацію
- Будь точним і конкретним, уникай загальних фраз

Тон: дружній, турботливий, як досвідчений травник."""

MAX_HISTORY = 20

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
conversation_history: dict[int, list] = defaultdict(list)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🌿 Вітаю! Я — Жива Аптека, твій персональний фіто-консультант.\n\n"
        "Можеш запитати мене про лікарські рослини, їх властивості та застосування. "
        "Також можеш надіслати фото рослини — я спробую її визначити.\n\n"
        "Чим можу допомогти?"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🌿 *Жива Аптека* — фіто-консультант\n\n"
        "📝 *Що я вмію:*\n"
        "• Відповідати на запитання про лікарські рослини\n"
        "• Розповідати про способи приготування відварів, настоянок\n"
        "• Описувати показання та протипоказання\n"
        "• Визначати рослини за фото\n\n"
        "📚 *Джерела:* Кархут, Носаль, Довідник фітотерапії, Дари лісу\n\n"
        "/start — почати розмову\n"
        "/clear — очистити історію розмови\n\n"
        "⚠️ Фітотерапія доповнює, але не замінює лікарську допомогу.",
        parse_mode="Markdown",
    )


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    conversation_history[user_id].clear()
    await update.message.reply_text("🌿 Історію розмови очищено. Починаємо спочатку!")


def _trim_history(user_id: int) -> None:
    history = conversation_history[user_id]
    if len(history) > MAX_HISTORY:
        conversation_history[user_id] = history[-MAX_HISTORY:]


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    text = update.message.text

    conversation_history[user_id].append({"role": "user", "content": text})
    _trim_history(user_id)

    await update.message.chat.send_action("typing")

    try:
        response = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=conversation_history[user_id],
        )
        answer = response.content[0].text
    except Exception as e:
        logger.error("Claude API error: %s", e)
        answer = "Вибач, сталася помилка. Спробуй ще раз."

    conversation_history[user_id].append({"role": "assistant", "content": answer})

    await update.message.reply_text(answer)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    caption = update.message.caption or "Що це за рослина? Розкажи про її лікарські властивості."

    photo = update.message.photo[-1]
    photo_file = await photo.get_file()
    photo_bytes = await photo_file.download_as_bytearray()
    image_data = base64.standard_b64encode(bytes(photo_bytes)).decode("utf-8")

    user_message = {
        "role": "user",
        "content": [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": image_data,
                },
            },
            {"type": "text", "text": caption},
        ],
    }

    conversation_history[user_id].append(user_message)
    _trim_history(user_id)

    await update.message.chat.send_action("typing")

    try:
        response = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=conversation_history[user_id],
        )
        answer = response.content[0].text
    except Exception as e:
        logger.error("Claude API error: %s", e)
        answer = "Вибач, не вдалося обробити фото. Спробуй ще раз."

    conversation_history[user_id].append({"role": "assistant", "content": answer})

    await update.message.reply_text(answer)


def main() -> None:
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    logger.info("Жива Аптека bot started")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()

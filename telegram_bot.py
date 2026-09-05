import asyncio
import logging
import os

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from mentor import DANISH_TUTOR_PROMPT, LanguageMentor


logger = logging.getLogger(__name__)
telegram_mentor = LanguageMentor("telegram", DANISH_TUTOR_PROMPT)

START_TEXT = (
    "Hej! Jeg er din danske sprogmentor. Jeg kan hjælpe med samtale, "
    "grammatik, oversættelse, ordforråd og korte øvelser. Skriv på dansk, "
    "eller vælg /help for at se kommandoerne."
)

HELP_TEXT = """Tilgængelige kommandoer:
/start — start mentorbotten
/help — vis denne hjælp
/exercise [emne] — få en kort dansk øvelse
/grammar <sætning> — få rettet en dansk sætning
/translate <tekst> — oversæt mellem russisk og dansk
/words [emne] — træn et lille sæt danske ord"""


def _command_text(context: ContextTypes.DEFAULT_TYPE) -> str:
    return " ".join(context.args).strip()


def _conversation_id(update: Update) -> str | None:
    if update.effective_user is not None:
        return str(update.effective_user.id)

    message = update.effective_message
    if message is not None and message.sender_chat is not None:
        return f"channel:{message.sender_chat.id}"

    if update.effective_chat is not None:
        return f"chat:{update.effective_chat.id}"

    return None


async def _reply_text(update: Update, text: str) -> None:
    message = update.effective_message
    if message is None:
        return

    text = text[:4000]
    if update.channel_post is not None:
        await message.get_bot().send_message(chat_id=message.chat_id, text=text)
    else:
        await message.reply_text(text)


async def _send_mentor_reply(update: Update, prompt: str) -> None:
    conversation_id = _conversation_id(update)
    if update.effective_message is None or conversation_id is None:
        logger.warning("Ignored Telegram text update without a chat identity")
        return

    try:
        reply = await telegram_mentor.reply(conversation_id, prompt)
    except Exception:
        logger.exception("Telegram mentor request failed")
        reply = "Beklager, jeg kunne ikke svare lige nu. Prøv igen om lidt."

    await _reply_text(update, reply)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    await _reply_text(update, START_TEXT)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    await _reply_text(update, HELP_TEXT)


async def exercise_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    topic = _command_text(context) or "dagligdags samtale"
    await _send_mentor_reply(
        update,
        "Lav én kort dansk øvelse om emnet "
        f"'{topic}'. Tilpas niveauet til eleven, og vis ikke svaret med det samme.",
    )


async def grammar_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    phrase = _command_text(context)
    if not phrase:
        await _reply_text(
            update,
            "Skriv en dansk sætning efter kommandoen, fx: "
            "/grammar Jeg har boet her siden to år",
        )
        return

    await _send_mentor_reply(
        update,
        "Ret denne danske sætning kort. Vis først den korrekte version, "
        "derefter en mere naturlig version, hvis den er anderledes. Forklar "
        f"kun svære fejl på russisk:\n{phrase}",
    )


async def translate_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    text = _command_text(context)
    if not text:
        await _reply_text(
            update,
            "Tilføj teksten efter kommandoen: /translate <tekst>",
        )
        return

    await _send_mentor_reply(
        update,
        "Oversæt teksten mellem russisk og dansk. Hvis teksten er russisk, "
        "skal svaret være dansk; hvis teksten er dansk, skal svaret være "
        f"russisk. Giv gerne én naturlig variant:\n{text}",
    )


async def words_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    topic = _command_text(context) or "hverdagen"
    await _send_mentor_reply(
        update,
        f"Lav en kompakt ordforrådstræning om '{topic}': fem danske ord "
        "med russisk oversættelse og ét kort spørgsmål til eleven.",
    )


async def text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    message = update.effective_message
    if message and message.text:
        await _send_mentor_reply(update, message.text)


async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    del update
    logger.error("Telegram update failed: %s", context.error)


def build_telegram_application(token: str) -> Application:
    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("exercise", exercise_command))
    application.add_handler(CommandHandler("grammar", grammar_command))
    application.add_handler(CommandHandler("translate", translate_command))
    application.add_handler(CommandHandler("words", words_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message))
    application.add_error_handler(error_handler)
    return application


async def run_telegram_bot() -> None:
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_TOKEN is not set")

    application = build_telegram_application(token)
    if application.updater is None:
        raise RuntimeError("Telegram polling updater is unavailable")

    async with application:
        try:
            await application.updater.start_polling()
            await application.start()
            print("Telegram Danish bot started", flush=True)
            await asyncio.Event().wait()
        finally:
            if application.updater.running:
                await application.updater.stop()
            if application.running:
                await application.stop()

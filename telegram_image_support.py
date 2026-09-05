import logging
import mimetypes
import os
import tempfile
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

from vision import analyze_image_file

logger = logging.getLogger(__name__)

SUPPORTED_IMAGE_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}


def _image_suffix(message) -> str:
    if message.document:
        if message.document.file_name:
            suffix = Path(message.document.file_name).suffix.lower()
            if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
                return suffix
        if message.document.mime_type:
            guessed = mimetypes.guess_extension(message.document.mime_type)
            if guessed:
                return guessed
    return ".jpg"


def _image_file_id(message) -> str | None:
    if message.photo:
        return message.photo[-1].file_id

    document = message.document
    if document and document.mime_type in SUPPORTED_IMAGE_MIME_TYPES:
        return document.file_id

    return None


def _vision_instruction(caption: str | None, learner_context: str) -> str:
    user_request = (caption or "").strip()
    if not user_request:
        user_request = (
            "Forklar hvad dette danske undervisningsmateriale handler om. "
            "Læs den relevante tekst, forklar emnet kort og giv klare danske eksempler."
        )

    return f"""You are helping a learner study Danish.

Learner context:
{learner_context or 'No saved learner context yet.'}

Analyze the attached image carefully. Read the relevant visible Danish text and understand the grammar or learning topic. Do not merely transcribe the image unless the learner asks for transcription.

User instruction:
{user_request}

Answer primarily in Danish. If the learner wrote the instruction in Russian, you may explain difficult grammar in Russian while keeping Danish examples in Danish. Be practical and concise. If the image contains a grammar rule, explain it and give 3-5 useful examples. Do not claim the learner completed or mastered this topic just because an image was sent."""


async def image_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    import telegram_bot

    message = update.effective_message
    conversation_id = telegram_bot._study_user_id(update)
    if message is None or conversation_id is None:
        logger.warning("Ignored Telegram image update without a chat identity")
        return

    file_id = _image_file_id(message)
    if not file_id:
        return

    temp_path: str | None = None
    try:
        telegram_file = await context.bot.get_file(file_id)
        with tempfile.NamedTemporaryFile(
            suffix=_image_suffix(message),
            delete=False,
        ) as temp_image:
            temp_path = temp_image.name

        await telegram_file.download_to_drive(custom_path=temp_path)
        learner_context = await telegram_bot._learner_context(conversation_id)
        instruction = _vision_instruction(message.caption, learner_context)
        result = await analyze_image_file(temp_path, instruction=instruction)
        await telegram_bot._reply_text(update, result[:4000])
    except Exception:
        logger.exception("Telegram image analysis failed")
        await telegram_bot._reply_text(
            update,
            "Jeg kunne ikke læse billedet tydeligt. Prøv at sende et skarpere billede eller et billede i JPG, PNG eller WEBP-format.",
        )
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                logger.warning("Could not remove temporary Telegram image file")


def install_telegram_image_support() -> None:
    """Attach image handlers without changing the existing Telegram bot API."""
    import telegram_bot

    if getattr(telegram_bot, "_image_support_installed", False):
        return

    original_builder = getattr(telegram_bot, "build_telegram_application", None)
    if original_builder is None:
        return

    def build_with_images(token: str):
        application = original_builder(token)
        image_filter = filters.PHOTO | filters.Document.IMAGE
        application.add_handler(MessageHandler(image_filter, image_message))
        return application

    telegram_bot.build_telegram_application = build_with_images
    telegram_bot._image_support_installed = True

import logging
import os
import tempfile
from dataclasses import dataclass
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationHandlerStop,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from mentor import LanguageMentor
from speech import generate_speech, transcribe_audio_file

logger = logging.getLogger(__name__)

SESSION_KEY = "du3_opgave2_session"


@dataclass(frozen=True)
class Du3Topic:
    title: str
    situations: tuple[str, str, str, str]
    situation_questions: tuple[str, str, str, str]
    individual_questions: tuple[str, ...]


TOPICS: dict[str, Du3Topic] = {
    "dansk": Du3Topic(
        title="At lære dansk",
        situations=(
            "gå på sprogskole",
            "få onlineundervisning",
            "lære dansk på arbejde",
            "lære dansk i fritiden",
        ),
        situation_questions=(
            "Kan du lide at gå på sprogskole? Hvorfor?",
            "Hvad synes du om onlineundervisning?",
            "Lærer du dansk på arbejde? Hvordan?",
            "Hvordan lærer du dansk i din fritid?",
        ),
        individual_questions=(
            "Hvordan kan du bedst lide at lære dansk? Hvorfor?",
            "Hvornår taler du dansk, og hvem taler du dansk med?",
            "Hvordan har du lært dansk indtil nu?",
            "Hvad synes du er sværest ved dansk?",
        ),
    ),
    "venner": Du3Topic(
        title="At møde nye venner",
        situations=(
            "møde nye mennesker på arbejde",
            "møde nye mennesker til en fest",
            "møde nye mennesker gennem sport",
            "møde nye mennesker online",
        ),
        situation_questions=(
            "Synes du, det er nemt at møde nye mennesker på arbejde? Hvorfor?",
            "Kan du lide at møde nye mennesker til en fest? Hvorfor eller hvorfor ikke?",
            "Synes du, sport er en god måde at få nye venner på? Hvorfor?",
            "Hvad synes du om at møde nye mennesker online?",
        ),
        individual_questions=(
            "Hvordan kan du bedst lide at møde nye venner? Hvorfor?",
            "Er det svært at møde nye venner som voksen? Hvorfor?",
            "Hvor møder du normalt nye mennesker?",
            "Kan du fortælle om sidste gang, du lærte et nyt menneske at kende?",
        ),
    ),
    "bolig": Du3Topic(
        title="Bolig",
        situations=(
            "bo i et hus på landet",
            "bo i et rækkehus",
            "bo i en moderne lejlighed",
            "bo i en ældre lejlighed i byen",
        ),
        situation_questions=(
            "Vil du gerne bo i et hus på landet? Hvorfor eller hvorfor ikke?",
            "Hvad synes du om at bo i et rækkehus?",
            "Vil du helst bo i en moderne lejlighed? Hvorfor?",
            "Hvad er en fordel ved at bo i en ældre lejlighed i byen?",
        ),
        individual_questions=(
            "Hvordan bor du nu?",
            "Hvor vil du helst bo i fremtiden? Hvorfor?",
            "Hvad er vigtigt for dig, når du vælger bolig?",
            "Hvad er en fordel og en ulempe ved at bo i lejlighed?",
        ),
    ),
    "gron": Du3Topic(
        title="Grønne vaner",
        situations=(
            "cykle eller bruge offentlig transport",
            "sortere affald og genbruge ting",
            "spare på strøm og vand",
            "købe økologisk mad og undgå madspild",
        ),
        situation_questions=(
            "Bruger du mest cykel eller offentlig transport? Hvorfor?",
            "Sorterer du affald derhjemme? Hvad sorterer du?",
            "Hvordan sparer du på strøm og vand?",
            "Køber du økologisk mad, eller prøver du at undgå madspild?",
        ),
        individual_questions=(
            "Hvad gør du for miljøet i din hverdag?",
            "Hvilken grøn vane synes du er vigtigst? Hvorfor?",
            "Hvordan sparer du på strøm eller vand?",
            "Er det svært eller dyrt at leve grønt?",
        ),
    ),
    "sund": Du3Topic(
        title="Sunde og usunde vaner",
        situations=(
            "spise sund mad",
            "dyrke motion",
            "få nok søvn",
            "slik, fastfood, rygning eller alkohol",
        ),
        situation_questions=(
            "Hvad gør du for at spise sundt?",
            "Hvor ofte dyrker du motion?",
            "Hvor mange timer sover du normalt?",
            "Har du nogle usunde vaner? Hvilke?",
        ),
        individual_questions=(
            "Hvad gør du for at leve sundt?",
            "Hvilken sund vane synes du er vigtigst? Hvorfor?",
            "Har du nogle usunde vaner?",
            "Hvad vil du gerne ændre ved din livsstil?",
        ),
    ),
}


DU3_SYSTEM_PROMPT = """
You are a strict Danish speaking-practice evaluator for Danskuddannelse 3,
Modul 3, mundtlig kommunikation, Opgave 2.

The exercise flow is controlled by the program. The program itself presents
the situation and asks the learner a fixed question. Your only job is to give
very short feedback on the learner's answer.

Use simple natural Danish suitable for DU3 Modul 3.
Never invent a new scenario. Never answer the question yourself. Never give
topic advice. Never ask a follow-up question. Never move to another situation.
Never use Russian, markdown, headings, scores, or percentages.

Feedback rules:
- If the learner answers the question understandably and there is no important
  mistake, reply exactly: "Godt svar."
- If there is one important Danish mistake, reply only:
  "Lille rettelse: <short corrected version>."
- If the learner does not answer the question, reply only:
  "Svar på spørgsmålet: <repeat the fixed question>"

Return only the feedback sentence.
""".strip()

du3_mentor = LanguageMentor("telegram-du3-opgave2", DU3_SYSTEM_PROMPT)


def _topic_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🇩🇰 At lære dansk", callback_data="du3op2:start:dansk"),
                InlineKeyboardButton("👥 Nye venner", callback_data="du3op2:start:venner"),
            ],
            [
                InlineKeyboardButton("🏠 Bolig", callback_data="du3op2:start:bolig"),
                InlineKeyboardButton("🌱 Grønne vaner", callback_data="du3op2:start:gron"),
            ],
            [
                InlineKeyboardButton(
                    "❤️ Sunde/usunde vaner",
                    callback_data="du3op2:start:sund",
                )
            ],
            [InlineKeyboardButton("⬅️ Studiemenu", callback_data="du3op2:cancel")],
        ]
    )


def _session_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("⏹️ Stop træning", callback_data="du3op2:cancel")]]
    )


def _new_session(topic_key: str) -> dict[str, Any]:
    if topic_key not in TOPICS:
        raise KeyError(topic_key)
    return {
        "topic_key": topic_key,
        "phase": "pair",
        "situation_index": 0,
        "question_index": 0,
    }


def _get_session(context: ContextTypes.DEFAULT_TYPE) -> dict[str, Any] | None:
    session = context.user_data.get(SESSION_KEY)
    if isinstance(session, dict) and session.get("topic_key") in TOPICS:
        return session
    return None


def _pair_turn_text(topic: Du3Topic, index: int) -> str:
    return (
        f"Situation {index + 1}/4: {topic.situations[index]}\n"
        f"🤖 Spørgsmål: {topic.situation_questions[index]}\n"
        "🎙️ Din tur: svar på spørgsmålet."
    )


def _individual_turn_text(topic: Du3Topic, index: int) -> str:
    total = len(topic.individual_questions)
    return (
        f"Del 2 — spørgsmål {index + 1}/{total}\n"
        f"🤖 Spørgsmål: {topic.individual_questions[index]}\n"
        "🎙️ Din tur: svar på spørgsmålet."
    )


def _intro_text(topic: Du3Topic) -> str:
    return (
        f"🗣️ DU3 Modul 3 — Opgave 2\n"
        f"Emne: {topic.title}\n\n"
        "Sådan foregår træningen:\n"
        "1. Jeg viser én situation.\n"
        "2. Jeg stiller ét spørgsmål.\n"
        "3. Du svarer med lyd eller tekst.\n"
        "4. Jeg retter højst én vigtig fejl og går videre.\n\n"
        + _pair_turn_text(topic, 0)
    )


def _intro_speech(topic: Du3Topic) -> str:
    return (
        f"Emnet er {topic.title}. Del 1. "
        f"Situation 1: {topic.situations[0]}. "
        f"Spørgsmål: {topic.situation_questions[0]}"
    )


def _feedback_prompt(question: str, transcript: str) -> str:
    return f"""
Fixed question:
{question}

Learner's spoken answer:
{transcript}

Evaluate only this answer according to the system rules.
Do not answer the question yourself and do not ask any new question.
""".strip()


async def _du3_reply(
    conversation_id: str,
    session: dict[str, Any],
    transcript: str,
) -> tuple[str, bool]:
    topic = TOPICS[session["topic_key"]]

    if session["phase"] == "pair":
        index = int(session["situation_index"])
        question = topic.situation_questions[index]
        feedback = await du3_mentor.reply(
            conversation_id,
            _feedback_prompt(question, transcript),
        )

        if index < len(topic.situations) - 1:
            next_index = index + 1
            session["situation_index"] = next_index
            return (
                f"{feedback}\n\n{_pair_turn_text(topic, next_index)}",
                False,
            )

        session["phase"] = "individual"
        session["question_index"] = 0
        return (
            f"{feedback}\n\nDel 1 er færdig. Nu starter Del 2.\n\n"
            f"{_individual_turn_text(topic, 0)}",
            False,
        )

    index = int(session["question_index"])
    question = topic.individual_questions[index]
    feedback = await du3_mentor.reply(
        conversation_id,
        _feedback_prompt(question, transcript),
    )

    if index < len(topic.individual_questions) - 1:
        next_index = index + 1
        session["question_index"] = next_index
        return (
            f"{feedback}\n\n{_individual_turn_text(topic, next_index)}",
            False,
        )

    return f"{feedback}\n\n✅ Opgave 2 er færdig.", True


async def _send_spoken_reply(update: Update, text: str) -> None:
    message = update.effective_message
    if message is None or update.channel_post is not None:
        return

    voice_path: str | None = None
    try:
        voice_path = await generate_speech(text)
        with open(voice_path, "rb") as voice_file:  # noqa: ASYNC230
            await message.reply_audio(audio=voice_file, title="DU3 Opgave 2")
    except Exception:
        logger.exception("Could not generate DU3 Opgave 2 speech")
    finally:
        if voice_path and os.path.exists(voice_path):
            try:
                os.remove(voice_path)
            except OSError:
                logger.warning("Could not remove DU3 speech file")


async def _handle_transcript(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    transcript: str,
) -> None:
    import telegram_bot

    session = _get_session(context)
    conversation_id = telegram_bot._study_user_id(update)
    if session is None or conversation_id is None:
        return

    try:
        reply, complete = await _du3_reply(conversation_id, session, transcript)
    except Exception:
        logger.exception("DU3 Opgave 2 mentor request failed")
        await telegram_bot._reply_text(
            update,
            "Jeg kunne ikke lave et svar lige nu. Prøv igen om lidt.",
            _session_markup(),
        )
        return

    await telegram_bot._reply_text(update, f"🗣️ {reply}", _session_markup())
    await _send_spoken_reply(update, reply)

    if complete:
        context.user_data.pop(SESSION_KEY, None)


async def du3_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if _get_session(context) is None:
        return

    message = update.effective_message
    if message is None or not message.text:
        return

    await _handle_transcript(update, context, message.text.strip())
    raise ApplicationHandlerStop


async def du3_audio_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if _get_session(context) is None:
        return

    import telegram_bot

    message = update.effective_message
    if message is None:
        return

    telegram_file = None
    if message.voice:
        telegram_file = await context.bot.get_file(message.voice.file_id)
    elif message.audio:
        telegram_file = await context.bot.get_file(message.audio.file_id)
    elif (
        message.document
        and message.document.mime_type
        and message.document.mime_type.startswith("audio/")
    ):
        telegram_file = await context.bot.get_file(message.document.file_id)

    if telegram_file is None:
        return

    temp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            suffix=telegram_bot._audio_suffix(update),
            delete=False,
        ) as temp_audio:
            temp_path = temp_audio.name

        await telegram_file.download_to_drive(custom_path=temp_path)
        transcript = await transcribe_audio_file(temp_path, language="da")
        await telegram_bot._reply_text(update, f"🎧 Jeg hørte:\n{transcript[:3500]}")
        await _handle_transcript(update, context, transcript)
    except Exception:
        logger.exception("DU3 Opgave 2 audio processing failed")
        await telegram_bot._reply_text(
            update,
            "Jeg kunne ikke forstå lydoptagelsen. Prøv igen med en kort og tydelig "
            "talebesked.",
            _session_markup(),
        )
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                logger.warning("Could not remove temporary DU3 audio file")

    raise ApplicationHandlerStop


async def du3_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    import telegram_bot

    query = update.callback_query
    if query is None or not query.data:
        return

    try:
        await query.answer()
    except Exception:
        pass

    data = query.data

    if data == "du3op2:menu":
        await telegram_bot._present(
            update,
            "🗣️ DU3 Modul 3 — Opgave 2\n\nVælg et emne til samtaletræning:",
            _topic_menu(),
        )
        raise ApplicationHandlerStop

    if data == "du3op2:cancel":
        context.user_data.pop(SESSION_KEY, None)
        await telegram_bot._show_learn_menu(update)
        raise ApplicationHandlerStop

    if data.startswith("du3op2:start:"):
        topic_key = data.rsplit(":", 1)[-1]
        topic = TOPICS.get(topic_key)
        if topic is None:
            await telegram_bot._present(update, "Emnet findes ikke.", _topic_menu())
            raise ApplicationHandlerStop

        conversation_id = telegram_bot._study_user_id(update)
        if conversation_id is None:
            await telegram_bot._present(
                update,
                "Jeg kunne ikke finde din studieprofil.",
                _topic_menu(),
            )
            raise ApplicationHandlerStop

        context.user_data[SESSION_KEY] = _new_session(topic_key)
        du3_mentor._histories.pop(du3_mentor.history_key(conversation_id), None)

        await telegram_bot._present(update, _intro_text(topic), _session_markup())
        await _send_spoken_reply(update, _intro_speech(topic))
        raise ApplicationHandlerStop


def install_du3_opgave2_support() -> None:
    """Attach a strict audio-first DU3 Modul 3 Opgave 2 practice mode."""
    import telegram_bot

    if getattr(telegram_bot, "_du3_opgave2_support_installed", False):
        return

    original_main_menu = getattr(telegram_bot, "_main_menu", None)
    original_builder = getattr(telegram_bot, "build_telegram_application", None)
    if original_main_menu is None or original_builder is None:
        return

    def main_menu_with_du3() -> InlineKeyboardMarkup:
        original = original_main_menu()
        rows = [list(row) for row in original.inline_keyboard]
        rows.insert(
            1,
            [
                InlineKeyboardButton(
                    "🗣️ DU3 Opgave 2",
                    callback_data="du3op2:menu",
                )
            ],
        )
        return InlineKeyboardMarkup(rows)

    telegram_bot._main_menu = main_menu_with_du3

    def build_with_du3(token: str):
        application = original_builder(token)
        application.add_handler(
            CallbackQueryHandler(du3_callback, pattern=r"^du3op2:"),
            group=-3,
        )
        application.add_handler(
            MessageHandler(
                filters.VOICE | filters.AUDIO | filters.Document.AUDIO,
                du3_audio_message,
            ),
            group=-3,
        )
        application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, du3_text_message),
            group=-3,
        )
        return application

    telegram_bot.build_telegram_application = build_with_du3
    telegram_bot._du3_opgave2_support_installed = True

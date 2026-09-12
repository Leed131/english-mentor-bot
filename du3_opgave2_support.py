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
        individual_questions=(
            "Hvad gør du for at leve sundt?",
            "Hvilken sund vane synes du er vigtigst? Hvorfor?",
            "Har du nogle usunde vaner?",
            "Hvad vil du gerne ændre ved din livsstil?",
        ),
    ),
}


DU3_SYSTEM_PROMPT = """
You are a Danish conversation partner and examiner for Danskuddannelse 3,
Modul 3, mundtlig kommunikation, Opgave 2.

The learner is practicing spoken Danish. Use simple, natural Danish suitable
for DU3 Modul 3. Keep every spoken response short: normally 1-3 short
sentences. Stay in Danish during the exercise.

Correct only an important mistake, and only one at a time. If a correction is
useful, say: "Lille rettelse: ..." and then give a short natural version.
Do not give grammar lectures. Do not use markdown, bullet points, headings,
scores, percentages, or Russian in the exercise.

In Del 1 you are a conversation partner. Answer the learner's question briefly,
give a simple reason, and ask one short question back when instructed.
In Del 2 you are the examiner. Ask one question at a time and wait for the
learner's answer.

Return only the words that should be spoken to the learner.
""".strip()

du3_mentor = LanguageMentor("telegram-du3-opgave2", DU3_SYSTEM_PROMPT)

QUESTION_STARTERS = (
    "hvad",
    "hvor",
    "hvordan",
    "hvorfor",
    "hvem",
    "hvilken",
    "hvilket",
    "hvilke",
    "kan",
    "skal",
    "vil",
    "er",
    "har",
    "synes",
    "foretrækker",
    "kunne",
)


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
        "turn": "learner_question",
        "question_index": 0,
    }


def _get_session(context: ContextTypes.DEFAULT_TYPE) -> dict[str, Any] | None:
    session = context.user_data.get(SESSION_KEY)
    if isinstance(session, dict) and session.get("topic_key") in TOPICS:
        return session
    return None


def _is_likely_question(text: str) -> bool:
    cleaned = text.strip().lower()
    if not cleaned:
        return False
    if cleaned.endswith("?"):
        return True
    first = cleaned.split(maxsplit=1)[0].strip(".,!?:;")
    return first in QUESTION_STARTERS


def _intro_text(topic: Du3Topic) -> str:
    situation = topic.situations[0]
    return (
        f"🗣️ DU3 Modul 3 — Opgave 2\n"
        f"Emne: {topic.title}\n\n"
        "Del 1: Vi taler om fire situationer. Du starter med at stille mig "
        "et spørgsmål, jeg svarer og spørger dig tilbage.\n\n"
        f"Situation 1/4: {situation}\n"
        "🎙️ Stil mig et kort spørgsmål på dansk om denne situation."
    )


def _intro_speech(topic: Du3Topic) -> str:
    return (
        f"Emnet er {topic.title}. Del 1. "
        f"Situation 1: {topic.situations[0]}. "
        "Stil mig et kort spørgsmål på dansk om denne situation."
    )


def _pair_question_prompt(topic: Du3Topic, session: dict[str, Any], transcript: str) -> str:
    index = int(session["situation_index"])
    situation = topic.situations[index]
    return f"""
Theme: {topic.title}
Del 1, situation {index + 1}/4: {situation}

The learner was asked to ask you a question about this situation.
Learner said: {transcript}

Respond as the conversation partner:
1. Answer the learner's question briefly and naturally.
2. Give one simple reason for your answer.
3. If there is an important language mistake, include at most one short
   "Lille rettelse: ..." sentence.
4. End with one short question back to the learner about the SAME situation.
Do not move to the next situation yet.
""".strip()


def _pair_answer_prompt(
    topic: Du3Topic,
    session: dict[str, Any],
    transcript: str,
) -> tuple[str, bool]:
    index = int(session["situation_index"])
    is_last = index == len(topic.situations) - 1

    if not is_last:
        next_situation = topic.situations[index + 1]
        ending = (
            f'End exactly with: "Næste situation: {next_situation}. '
            'Stil mig et spørgsmål om den."'
        )
    else:
        first_question = topic.individual_questions[0]
        ending = (
            'Tell the learner that Del 2 starts now. '
            f'End by asking exactly: "{first_question}"'
        )

    prompt = f"""
Theme: {topic.title}
Del 1, situation {index + 1}/4: {topic.situations[index]}

You asked the learner a short question about this situation.
Learner answered: {transcript}

Acknowledge the answer briefly. If there is an important language mistake,
include at most one short "Lille rettelse: ..." sentence.
Do not ask another question about the current situation.
{ending}
""".strip()
    return prompt, is_last


def _individual_prompt(
    topic: Du3Topic,
    session: dict[str, Any],
    transcript: str,
) -> tuple[str, bool]:
    index = int(session["question_index"])
    current_question = topic.individual_questions[index]
    is_last = index == len(topic.individual_questions) - 1

    if is_last:
        ending = (
            'Finish the exercise with a short encouraging sentence such as '
            '"Godt arbejde. Opgave 2 er færdig." Do not ask a new question.'
        )
    else:
        next_question = topic.individual_questions[index + 1]
        ending = f'End by asking exactly: "{next_question}"'

    prompt = f"""
Theme: {topic.title}
Del 2, individual question {index + 1}/{len(topic.individual_questions)}.
Current question: {current_question}
Learner answered: {transcript}

React briefly to the answer. If there is an important language mistake,
include at most one short "Lille rettelse: ..." sentence.
{ending}
""".strip()
    return prompt, is_last


async def _du3_reply(
    conversation_id: str,
    session: dict[str, Any],
    transcript: str,
) -> tuple[str, bool]:
    topic = TOPICS[session["topic_key"]]

    if session["phase"] == "pair":
        if session["turn"] == "learner_question":
            if not _is_likely_question(transcript):
                situation = topic.situations[int(session["situation_index"])]
                return (
                    "Prøv at stille mig et spørgsmål først. "
                    f'For eksempel: "Hvad synes du om {situation}?"',
                    False,
                )

            prompt = _pair_question_prompt(topic, session, transcript)
            reply = await du3_mentor.reply(conversation_id, prompt)
            session["turn"] = "learner_answer"
            return reply, False

        prompt, starts_individual = _pair_answer_prompt(topic, session, transcript)
        reply = await du3_mentor.reply(conversation_id, prompt)
        if starts_individual:
            session["phase"] = "individual"
            session["question_index"] = 0
            session["turn"] = "learner_answer"
        else:
            session["situation_index"] = int(session["situation_index"]) + 1
            session["turn"] = "learner_question"
        return reply, False

    prompt, is_last = _individual_prompt(topic, session, transcript)
    reply = await du3_mentor.reply(conversation_id, prompt)
    if not is_last:
        session["question_index"] = int(session["question_index"]) + 1
    return reply, is_last


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
    """Attach an audio-first DU3 Modul 3 Opgave 2 practice mode."""
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

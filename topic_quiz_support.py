import asyncio
import json
import logging
from typing import Any

from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationHandlerStop,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from database import QuizSession, utc_now
from quiz_generator import generate_topic_quiz
from study_memory import QuizAnswer, QuizSnapshot, get_study_memory

logger = logging.getLogger(__name__)


def _quiz_markup(quiz: QuizSnapshot) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(
                option,
                callback_data=f"study:quiz:{quiz.id}:{quiz.question_index}:{index}",
            )
        ]
        for index, option in enumerate(quiz.options)
    ]
    buttons.append([InlineKeyboardButton("⬅️ Studiemenu", callback_data="study:menu")])
    return InlineKeyboardMarkup(buttons)


def _quiz_text(quiz: QuizSnapshot, prefix: str | None = None) -> str:
    parts: list[str] = []
    if prefix:
        parts.extend([prefix, ""])
    parts.extend(
        [
            f"Spørgsmål {quiz.question_index + 1}/{quiz.question_count}",
            quiz.question,
        ]
    )
    return "\n".join(parts)


def _start_custom_quiz_sync(
    user_id: str,
    topic: str,
    questions: list[dict[str, Any]],
) -> QuizSnapshot:
    memory = get_study_memory()
    with memory.database.session() as session:
        profile = memory._profile(session, "telegram", user_id)

        unfinished = session.scalars(
            select(QuizSession).where(
                QuizSession.profile_id == profile.id,
                QuizSession.completed.is_(False),
            )
        ).all()
        for old_quiz in unfinished:
            old_quiz.completed = True

        quiz = QuizSession(
            profile_id=profile.id,
            kind="grammar",
            topic=topic[:160],
            questions_json=json.dumps(questions, ensure_ascii=False),
        )
        session.add(quiz)
        session.flush()

        profile.current_section = "grammar"
        profile.current_topic = topic[:160]
        profile.next_step = f"Svar på spørgsmål 1 af {len(questions)}"
        profile.last_activity = utc_now()
        profile.updated_at = utc_now()

        snapshot = memory._quiz_snapshot(quiz)
        if snapshot is None:
            raise RuntimeError("Generated quiz has no questions")
        return snapshot


async def _start_topic_quiz(update: Update, topic: str) -> None:
    import telegram_bot

    user_id = telegram_bot._study_user_id(update)
    if user_id is None:
        await telegram_bot._reply_text(update, "Jeg kunne ikke finde din studieprofil.")
        return

    topic = topic.strip()
    if not topic:
        profile = await telegram_bot._study_call(
            "get_or_create_profile",
            "telegram",
            user_id,
        )
        topic = profile.current_topic or "dansk grammatik"

    try:
        learner_context = await telegram_bot._learner_context(user_id)
        questions = await generate_topic_quiz(topic, learner_context, count=5)
        quiz = await asyncio.to_thread(
            _start_custom_quiz_sync,
            user_id,
            topic,
            questions,
        )
    except Exception:
        logger.exception("Could not generate topic quiz")
        await telegram_bot._reply_text(
            update,
            "Jeg kunne ikke lave øvelser til emnet lige nu. Prøv igen om lidt.",
        )
        return

    await telegram_bot._present(
        update,
        _quiz_text(quiz, f"🧩 Øvelser: {topic}"),
        _quiz_markup(quiz),
    )


async def quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    topic = " ".join(context.args).strip()
    await _start_topic_quiz(update, topic)


async def topic_quiz_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    del context
    import telegram_bot

    query = update.callback_query
    if query is None or not query.data:
        return
    try:
        await query.answer()
    except Exception:
        pass

    data = query.data
    if data == "topicquiz:current":
        await _start_topic_quiz(update, "")
        return

    if data.startswith("topicquiz:next:"):
        user_id = telegram_bot._study_user_id(update)
        if user_id is None:
            return
        quiz = await telegram_bot._study_call(
            "get_active_quiz",
            "telegram",
            user_id,
        )
        if quiz is None:
            await telegram_bot._present(update, "Denne øvelse er afsluttet.")
            return
        await telegram_bot._present(update, _quiz_text(quiz), _quiz_markup(quiz))


async def topic_quiz_answer_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    del context
    import telegram_bot

    query = update.callback_query
    if query is None or not query.data:
        return

    parts = query.data.split(":")
    if len(parts) != 5:
        return

    try:
        quiz_id, question_index, selected_index = map(int, parts[2:])
    except ValueError:
        return

    try:
        await query.answer()
    except Exception:
        pass

    user_id = telegram_bot._study_user_id(update)
    if user_id is None:
        raise ApplicationHandlerStop

    result: QuizAnswer = await telegram_bot._study_call(
        "answer_quiz",
        "telegram",
        user_id,
        quiz_id,
        question_index,
        selected_index,
    )

    if result.state in {"missing", "invalid"}:
        await telegram_bot._present(update, "Denne øvelse er ikke længere aktiv.")
        raise ApplicationHandlerStop

    if result.state == "duplicate":
        if result.next_question is not None:
            keyboard = InlineKeyboardMarkup(
                [[InlineKeyboardButton("➡️ Næste spørgsmål", callback_data=f"topicquiz:next:{quiz_id}")]]
            )
            await telegram_bot._present(
                update,
                "Dette svar er allerede registreret.",
                keyboard,
            )
        else:
            await telegram_bot._present(update, "Øvelsen er allerede afsluttet.")
        raise ApplicationHandlerStop

    if result.was_correct:
        feedback = "✅ Korrekt"
    else:
        feedback = "❌ Forkert"

    if result.explanation:
        feedback += f"\n\n{result.explanation}"

    if result.state == "complete":
        feedback += (
            "\n\nFærdig!"
            f"\n✅ Rigtige svar: {result.correct_answers}"
            f"\n❌ Forkerte svar: {result.wrong_answers}"
        )
        await telegram_bot._present(update, feedback, telegram_bot._main_menu())
    else:
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("➡️ Næste spørgsmål", callback_data=f"topicquiz:next:{quiz_id}")]]
        )
        await telegram_bot._present(update, feedback, keyboard)

    raise ApplicationHandlerStop


def install_topic_quiz_support() -> None:
    """Attach dynamic topic quizzes to the existing Telegram application."""
    import telegram_bot

    if getattr(telegram_bot, "_topic_quiz_support_installed", False):
        return

    original_builder = telegram_bot.build_telegram_application

    def build_with_topic_quizzes(token: str):
        application = original_builder(token)
        application.add_handler(CommandHandler("quiz", quiz_command), group=-2)
        application.add_handler(
            CallbackQueryHandler(
                topic_quiz_answer_callback,
                pattern=r"^study:quiz:",
            ),
            group=-2,
        )
        application.add_handler(
            CallbackQueryHandler(
                topic_quiz_callback,
                pattern=r"^topicquiz:",
            ),
            group=-2,
        )
        return application

    telegram_bot.build_telegram_application = build_with_topic_quizzes
    telegram_bot._topic_quiz_support_installed = True

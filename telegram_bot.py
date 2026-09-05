import asyncio
import logging
import mimetypes
import os
import tempfile
from collections.abc import Callable
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest, TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from mentor import DANISH_TUTOR_PROMPT, LanguageMentor
from progress import format_progress_report, progress_bar
from speech import generate_speech, transcribe_audio_file
from study_evaluator import evaluate_danish_writing
from study_memory import (
    ProfileSnapshot,
    QuizAnswer,
    QuizSnapshot,
    VerbReviewSnapshot,
    get_study_memory,
)

logger = logging.getLogger(__name__)
telegram_mentor = LanguageMentor("telegram", DANISH_TUTOR_PROMPT)

START_TEXT = (
    "Hej! Jeg er din danske sprogmentor. Jeg kan hjælpe med samtale, "
    "grammatik, oversættelse, ordforråd og korte øvelser. Du kan også sende "
    "en talebesked på dansk. Brug /learn for at åbne din studieplan."
)

HELP_TEXT = """Tilgængelige kommandoer:
/start — start mentorbotten
/help — vis denne hjælp
/learn — åbn studiemenuen
/continue — fortsæt hvor du stoppede
/progress — se fremskridt i din aktuelle plan
/history — se emner og fejl fra tidligere
/review — se hvad der skal repeteres
/reset_progress — nulstil studiedata med bekræftelse
/exercise [emne] — få en kort dansk øvelse
/grammar <sætning> — få rettet en dansk sætning
/translate <tekst> — oversæt mellem russisk og dansk
/words [emne] — træn et lille sæt danske ord
/verbs — åbn menuen for danske verber

Du kan også sende en talebesked eller en lydfil på dansk."""

WRITING_TOPIC = "min dag"
WRITING_NEXT_STEP = "submit_writing"
AUDIO_TOPIC = "speaking and listening"
AUDIO_NEXT_STEP = "send_voice_message"


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


def _study_user_id(update: Update) -> str | None:
    chat = update.effective_chat
    if chat is not None and getattr(chat, "type", None) == "channel":
        return f"channel:{chat.id}"
    return _conversation_id(update)


async def _study_call(method_name: str, *args: Any, **kwargs: Any) -> Any:
    def call() -> Any:
        method: Callable[..., Any] = getattr(get_study_memory(), method_name)
        return method(*args, **kwargs)

    return await asyncio.to_thread(call)


async def _reply_text(
    update: Update,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    message = update.effective_message
    if message is None:
        return

    text = text[:4000]
    if update.channel_post is not None:
        kwargs: dict[str, Any] = {"chat_id": message.chat_id, "text": text}
        if reply_markup is not None:
            kwargs["reply_markup"] = reply_markup
        await message.get_bot().send_message(**kwargs)
    else:
        kwargs = {"text": text}
        if reply_markup is not None:
            kwargs["reply_markup"] = reply_markup
        await message.reply_text(**kwargs)


async def _present(
    update: Update,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    query = getattr(update, "callback_query", None)
    if query is None:
        await _reply_text(update, text, reply_markup)
        return

    try:
        await query.edit_message_text(text=text[:4000], reply_markup=reply_markup)
    except BadRequest as error:
        if "Message is not modified" not in str(error):
            logger.warning("Could not edit Telegram study menu: %s", error)
            await _reply_text(update, text, reply_markup)
    except TelegramError as error:
        logger.warning("Could not edit Telegram study menu: %s", error)
        await _reply_text(update, text, reply_markup)


def _main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🎧 Аудио", callback_data="study:section:audio"),
                InlineKeyboardButton("🧪 Тесты", callback_data="study:section:tests"),
            ],
            [
                InlineKeyboardButton(
                    "📚 Грамматика",
                    callback_data="study:section:grammar",
                ),
                InlineKeyboardButton(
                    "✍️ Письмо",
                    callback_data="study:section:writing",
                ),
            ],
            [
                InlineKeyboardButton("🔤 Глаголы", callback_data="study:verbs"),
                InlineKeyboardButton("📊 Прогресс", callback_data="study:progress"),
            ],
            [
                InlineKeyboardButton("🔁 Повторить", callback_data="study:review"),
                InlineKeyboardButton("▶️ Продолжить", callback_data="study:continue"),
            ],
            [
                InlineKeyboardButton(
                    "🎯 Тренировка на сегодня",
                    callback_data="study:daily",
                ),
                InlineKeyboardButton("📖 Что мы прошли", callback_data="study:history"),
            ],
        ]
    )


def _verb_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📚 Учить новые",
                    callback_data="study:verb:learn",
                ),
                InlineKeyboardButton(
                    "🔁 Повторить",
                    callback_data="study:verb:review",
                ),
            ],
            [
                InlineKeyboardButton(
                    "✅ Закреплённые",
                    callback_data="study:verb:mastered",
                ),
                InlineKeyboardButton(
                    "📊 Статистика",
                    callback_data="study:verb:stats",
                ),
            ],
            [InlineKeyboardButton("⬅️ Учебное меню", callback_data="study:menu")],
        ]
    )


def _quiz_markup(quiz: QuizSnapshot) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(
                option,
                callback_data=(
                    f"study:quiz:{quiz.id}:{quiz.question_index}:{option_index}"
                ),
            )
        ]
        for option_index, option in enumerate(quiz.options)
    ]
    buttons.append([InlineKeyboardButton("⬅️ Studiemenu", callback_data="study:menu")])
    return InlineKeyboardMarkup(buttons)


def _verb_review_markup(review: VerbReviewSnapshot) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(
                option,
                callback_data=f"study:verb_answer:{review.id}:{option_index}",
            )
        ]
        for option_index, option in enumerate(review.options)
    ]
    buttons.append([InlineKeyboardButton("⬅️ Verber", callback_data="study:verbs")])
    return InlineKeyboardMarkup(buttons)


def _quiz_text(quiz: QuizSnapshot, prefix: str | None = None) -> str:
    lines = []
    if prefix:
        lines.extend([prefix, ""])
    lines.extend(
        [
            f"Spørgsmål {quiz.question_index + 1}/{quiz.question_count}",
            quiz.question,
        ]
    )
    return "\n".join(lines)


async def _identity_or_warn(update: Update) -> str | None:
    user_id = _study_user_id(update)
    if user_id is None:
        await _reply_text(update, "Jeg kunne ikke finde din studieprofil.")
    return user_id


async def _learner_context(conversation_id: str) -> str:
    return await _study_call(
        "build_learner_context",
        "telegram",
        conversation_id,
    )


async def _mentor_reply(conversation_id: str, prompt: str) -> str:
    learner_context = await _learner_context(conversation_id)
    return await telegram_mentor.reply(
        conversation_id,
        prompt,
        learner_context=learner_context,
    )


async def _send_mentor_reply(update: Update, prompt: str) -> str | None:
    conversation_id = _study_user_id(update)
    if update.effective_message is None or conversation_id is None:
        logger.warning("Ignored Telegram update without a chat identity")
        return None

    try:
        reply = await _mentor_reply(conversation_id, prompt)
    except Exception:
        logger.exception("Telegram mentor request failed")
        reply = "Beklager, jeg kunne ikke svare lige nu. Prøv igen om lidt."

    await _reply_text(update, reply)
    return reply


async def _show_learn_menu(update: Update) -> None:
    user_id = await _identity_or_warn(update)
    if user_id is None:
        return
    profile: ProfileSnapshot = await _study_call(
        "get_or_create_profile",
        "telegram",
        user_id,
    )
    await _present(
        update,
        f"🇩🇰 Din danske studieplan — {profile.current_level}\n\nVælg en aktivitet:",
        _main_menu(),
    )


async def _show_progress(update: Update) -> None:
    user_id = await _identity_or_warn(update)
    if user_id is None:
        return
    profile, sections, today, test_stats = await asyncio.gather(
        _study_call("get_or_create_profile", "telegram", user_id),
        _study_call("get_sections", "telegram", user_id),
        _study_call("get_today_summary", "telegram", user_id),
        _study_call("get_test_stats", "telegram", user_id),
    )
    percentages = {name: section.percentage for name, section in sections.items()}
    report = format_progress_report(profile.current_level, percentages)
    if today["total"]:
        report += (
            "\n\n✅ Сегодня выполнено"
            f"\n🎧 Аудио: {today['audio']}"
            f"\n🧪 Тесты: {today['tests']}"
            f"\n📚 Грамматика: {today['grammar']}"
            f"\n✍️ Письмо: {today['writing']}"
            f"\n🔤 Глаголы: {today['verbs']}"
            f"\nСредний результат: {today['score']}%"
        )
    if test_stats["count"]:
        report += (
            "\n\n🧪 Результаты тестов"
            f"\nПоследний: {test_stats['latest']}%"
            f"\nЛучший: {test_stats['best']}%"
            f"\nСредний: {test_stats['average']}%"
        )
    await _present(
        update,
        report,
        InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ Studiemenu", callback_data="study:menu")]]
        ),
    )


async def _show_history(update: Update) -> None:
    user_id = await _identity_or_warn(update)
    if user_id is None:
        return
    history = await _study_call("get_history", "telegram", user_id)

    def values(name: str, empty: str) -> str:
        items = history[name]
        return ", ".join(items) if isinstance(items, list) and items else empty

    text = "\n".join(
        [
            "📖 Det har vi arbejdet med",
            "",
            f"📘 Gennemført: {values('completed', 'intet endnu')}",
            f"✅ Behersket: {values('mastered', 'ingen endnu')}",
            f"🟡 Lærer nu: {values('learning', 'ingen endnu')}",
            f"🔁 Skal repeteres: {values('review', 'intet endnu')}",
            f"📝 Typiske fejl: {values('errors', 'ingen registrerede')}",
            "",
            f"Aktuelt emne: {history['current_topic'] or 'ikke valgt'}",
            f"Næste skridt: {history['next_step'] or 'åbn /learn'}",
        ]
    )
    await _present(
        update,
        text,
        InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ Studiemenu", callback_data="study:menu")]]
        ),
    )


async def _show_review(update: Update) -> None:
    user_id = await _identity_or_warn(update)
    if user_id is None:
        return
    counts = await _study_call("get_review_counts", "telegram", user_id)
    total = sum(counts.values())
    text = "\n".join(
        [
            "🔁 Repetition i dag",
            "",
            f"🔤 Verber: {counts['verbs']}",
            f"📚 Grammatikemner: {counts['grammar']}",
            f"📝 Typiske fejl: {counts['errors']}",
            f"🔡 Ord: {counts['words']}",
            "",
            "Du er ajourført." if total == 0 else "Vælg hvad du vil repetere:",
        ]
    )
    buttons: list[list[InlineKeyboardButton]] = []
    if counts["verbs"]:
        buttons.append(
            [
                InlineKeyboardButton(
                    "🔤 Repetér verber", callback_data="study:verb:review"
                )
            ]
        )
    if counts["grammar"] or counts["errors"]:
        buttons.append(
            [
                InlineKeyboardButton(
                    "📚 Grammatikøvelse",
                    callback_data="study:section:grammar",
                )
            ]
        )
    buttons.append([InlineKeyboardButton("⬅️ Studiemenu", callback_data="study:menu")])
    await _present(update, text, InlineKeyboardMarkup(buttons))


async def _show_continue(update: Update) -> None:
    user_id = await _identity_or_warn(update)
    if user_id is None:
        return
    active_quiz: QuizSnapshot | None = await _study_call(
        "get_active_quiz",
        "telegram",
        user_id,
    )
    if active_quiz is not None:
        await _present(
            update,
            _quiz_text(active_quiz, "▶️ Lad os fortsætte din quiz."),
            _quiz_markup(active_quiz),
        )
        return

    profile: ProfileSnapshot = await _study_call(
        "get_or_create_profile",
        "telegram",
        user_id,
    )
    if profile.current_section == "writing" and profile.next_step == WRITING_NEXT_STEP:
        await _present(
            update,
            "▶️ Sidst valgte du skrivning. Skriv tre danske sætninger om din dag.",
            _main_menu(),
        )
        return
    if profile.current_section == "audio" and profile.next_step == AUDIO_NEXT_STEP:
        await _present(
            update,
            "▶️ Sidst valgte du audio. Send en kort talebesked på dansk om din dag.",
            _main_menu(),
        )
        return

    text = "\n".join(
        [
            "▶️ Fortsæt undervisningen",
            "",
            f"Sidste emne: {profile.current_topic or 'intet endnu'}",
            f"Næste skridt: {profile.next_step or 'vælg en aktivitet'}",
        ]
    )
    await _present(update, text, _main_menu())


async def _show_verbs(update: Update) -> None:
    user_id = await _identity_or_warn(update)
    if user_id is None:
        return
    stats = await _study_call("get_verb_stats", "telegram", user_id)
    await _present(
        update,
        "\n".join(
            [
                "🔤 Danske verber",
                "",
                f"Studeret: {stats['total']}",
                f"Til repetition nu: {stats['due']}",
                f"Behersket: {stats['mastered']}",
            ]
        ),
        _verb_menu(),
    )


async def _show_daily_training(update: Update) -> None:
    user_id = await _identity_or_warn(update)
    if user_id is None:
        return
    counts, today = await asyncio.gather(
        _study_call("get_review_counts", "telegram", user_id),
        _study_call("get_today_summary", "telegram", user_id),
    )
    text = "\n".join(
        [
            "🎯 Træning i dag — cirka 10–15 minutter",
            "",
            f"🔤 2 verber ({counts['verbs']} forfalder nu)",
            "📚 1 grammatikøvelse",
            "🎧 1 kort talebesked",
            "✍️ 1 kort tekst",
            "",
            f"Allerede gennemført i dag: {today['total']} opgaver",
        ]
    )
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔤 Verber", callback_data="study:verbs"),
                InlineKeyboardButton(
                    "📚 Grammatik",
                    callback_data="study:section:grammar",
                ),
            ],
            [
                InlineKeyboardButton("🎧 Audio", callback_data="study:section:audio"),
                InlineKeyboardButton(
                    "✍️ Skrivning",
                    callback_data="study:section:writing",
                ),
            ],
            [InlineKeyboardButton("⬅️ Studiemenu", callback_data="study:menu")],
        ]
    )
    await _present(update, text, keyboard)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    await _reply_text(update, START_TEXT, _main_menu())


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    await _reply_text(update, HELP_TEXT, _main_menu())


async def learn_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    await _show_learn_menu(update)


async def continue_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    await _show_continue(update)


async def progress_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    await _show_progress(update)


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    await _show_history(update)


async def review_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    await _show_review(update)


async def verbs_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    await _show_verbs(update)


async def reset_progress_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    del context
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Ja, slet",
                    callback_data="study:reset:confirm",
                ),
                InlineKeyboardButton("Annuller", callback_data="study:reset:cancel"),
            ]
        ]
    )
    await _reply_text(
        update,
        "⚠️ Dette sletter hele din studiehistorik og kan ikke fortrydes.\n\n"
        "Vil du fortsætte?",
        keyboard,
    )


async def exercise_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    topic = _command_text(context) or "dagligdags samtale"
    user_id = _study_user_id(update)
    if user_id is not None:
        await _study_call(
            "set_current_step",
            "telegram",
            user_id,
            "grammar",
            topic,
            "Besvar den genererede øvelse",
        )
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


async def _handle_writing_submission(
    update: Update,
    user_id: str,
    text: str,
) -> bool:
    profile: ProfileSnapshot = await _study_call(
        "get_or_create_profile",
        "telegram",
        user_id,
    )
    if profile.current_section != "writing" or profile.next_step != WRITING_NEXT_STEP:
        return False

    try:
        context = await _learner_context(user_id)
        evaluation = await evaluate_danish_writing(text, context)
        await _study_call(
            "save_writing_evaluation",
            "telegram",
            user_id,
            profile.current_topic or WRITING_TOPIC,
            evaluation.score,
            evaluation.grammar_errors,
            evaluation.vocabulary_errors,
        )
    except Exception:
        logger.exception("Could not evaluate and save Telegram writing exercise")
        await _send_mentor_reply(
            update,
            "Ret denne korte danske tekst venligt, men opfind ikke en score:\n" + text,
        )
        return True

    await _reply_text(
        update,
        "\n".join(
            [
                "✍️ Skriveøvelsen er gemt.",
                f"Resultat: {evaluation.score}%",
                "",
                evaluation.feedback_da,
                "",
                f"Grammatikfejl: {len(evaluation.grammar_errors)}",
                f"Ordforrådsfejl: {len(evaluation.vocabulary_errors)}",
            ]
        ),
        _main_menu(),
    )
    return True


async def text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    message = update.effective_message
    user_id = _study_user_id(update)
    if message and message.text and user_id:
        if await _handle_writing_submission(update, user_id, message.text):
            return
        await _send_mentor_reply(update, message.text)


def _audio_suffix(update: Update) -> str:
    message = update.effective_message
    if message is None:
        return ".ogg"

    if message.voice:
        return ".ogg"

    if message.audio:
        if message.audio.file_name:
            _, ext = os.path.splitext(message.audio.file_name)
            if ext:
                return ext.lower()
        if message.audio.mime_type:
            guessed = mimetypes.guess_extension(message.audio.mime_type)
            if guessed:
                return guessed

    if message.document:
        if message.document.file_name:
            _, ext = os.path.splitext(message.document.file_name)
            if ext:
                return ext.lower()
        if message.document.mime_type:
            guessed = mimetypes.guess_extension(message.document.mime_type)
            if guessed:
                return guessed

    return ".ogg"


async def audio_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    conversation_id = _study_user_id(update)
    if message is None or conversation_id is None:
        logger.warning("Ignored Telegram audio update without a chat identity")
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
    voice_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            suffix=_audio_suffix(update),
            delete=False,
        ) as temp_audio:
            temp_path = temp_audio.name

        await telegram_file.download_to_drive(custom_path=temp_path)
        transcript = await transcribe_audio_file(temp_path, language="da")
        await _reply_text(update, f"🎧 Jeg hørte:\n{transcript[:3500]}")

        reply = await _mentor_reply(conversation_id, transcript)
        await _reply_text(update, f"🇩🇰 {reply[:3900]}")

        profile: ProfileSnapshot = await _study_call(
            "get_or_create_profile",
            "telegram",
            conversation_id,
        )
        if profile.current_section == "audio" and profile.next_step == AUDIO_NEXT_STEP:
            await _study_call(
                "record_activity",
                "telegram",
                conversation_id,
                "audio",
                AUDIO_TOPIC,
                details={"transcription_completed": True},
                next_step="Lyt til svaret og vælg næste øvelse",
            )

        # Voice/audio responses are only sent in normal chats. For channel
        # posts, keep the response as a text post to avoid reply-context issues.
        if update.channel_post is None:
            try:
                voice_path = await generate_speech(reply)
                # Telegram needs the file handle to stay open during the upload.
                with open(voice_path, "rb") as voice_file:  # noqa: ASYNC230
                    await message.reply_audio(
                        audio=voice_file,
                        title="Dansk svar",
                    )
            except Exception:
                logger.exception("Telegram Danish TTS failed")
    except Exception:
        logger.exception("Telegram audio processing failed")
        await _reply_text(
            update,
            "Jeg kunne ikke forstå lydoptagelsen. Prøv igen med en kort og tydelig "
            "talebesked.",
        )
    finally:
        for path in (temp_path, voice_path):
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    logger.warning("Could not remove temporary audio file")


async def _start_quiz(update: Update, kind: str) -> None:
    user_id = await _identity_or_warn(update)
    if user_id is None:
        return
    quiz: QuizSnapshot = await _study_call(
        "start_quiz",
        "telegram",
        user_id,
        kind,
    )
    title = "🧪 Kort A1-test" if kind == "test" else "📚 Grammatikøvelse"
    await _present(update, _quiz_text(quiz, title), _quiz_markup(quiz))


async def _handle_quiz_answer(update: Update, parts: list[str]) -> None:
    if len(parts) != 5:
        return
    user_id = await _identity_or_warn(update)
    if user_id is None:
        return
    try:
        quiz_id, question_index, selected_index = map(int, parts[2:])
    except ValueError:
        return
    result: QuizAnswer = await _study_call(
        "answer_quiz",
        "telegram",
        user_id,
        quiz_id,
        question_index,
        selected_index,
    )
    if result.state in {"missing", "invalid"}:
        await _present(update, "Denne quiz er ikke længere aktiv.", _main_menu())
        return
    if result.state == "duplicate":
        if result.next_question is not None:
            await _present(
                update,
                _quiz_text(result.next_question, "Dette svar er allerede registreret."),
                _quiz_markup(result.next_question),
            )
        else:
            await _present(update, "Resultatet er allerede gemt.", _main_menu())
        return

    feedback = "✅ Korrekt!" if result.was_correct else "❌ Ikke helt."
    if result.explanation:
        feedback += f"\n{result.explanation}"
    if result.state == "complete":
        feedback += (
            "\n\nTesten er gemt: "
            f"{result.correct_answers}/{result.correct_answers + result.wrong_answers} "
            f"korrekte ({result.score}%)."
        )
        await _present(update, feedback, _main_menu())
    elif result.next_question is not None:
        await _present(
            update,
            _quiz_text(result.next_question, feedback),
            _quiz_markup(result.next_question),
        )


async def _learn_verb(update: Update) -> None:
    user_id = await _identity_or_warn(update)
    if user_id is None:
        return
    verb = await _study_call("learn_next_verb", "telegram", user_id)
    if verb is None:
        await _present(
            update,
            "Du har åbnet alle verber i denne plan. Brug repetition.",
            _verb_menu(),
        )
        return
    text = "\n".join(
        [
            "📚 Nyt verbum",
            "",
            f"{verb.infinitive} — {verb.translation_ru}",
            f"Nutid: {verb.present}",
            f"Datid: {verb.past}",
            f"Perfektum participium: {verb.past_participle}",
            "",
            "Verbet tæller først i din opgavefremgang, når du besvarer en øvelse.",
        ]
    )
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "▶️ Øv nu",
                    callback_data="study:verb:review",
                )
            ],
            [InlineKeyboardButton("⬅️ Verber", callback_data="study:verbs")],
        ]
    )
    await _present(update, text, keyboard)


async def _start_verb_review(update: Update) -> None:
    user_id = await _identity_or_warn(update)
    if user_id is None:
        return
    review: VerbReviewSnapshot | None = await _study_call(
        "create_verb_review",
        "telegram",
        user_id,
    )
    if review is None:
        await _present(
            update,
            "Der er ingen verber til repetition lige nu. Lær et nyt verbum først.",
            _verb_menu(),
        )
        return
    await _present(update, f"🔁 {review.question}", _verb_review_markup(review))


async def _handle_verb_answer(update: Update, parts: list[str]) -> None:
    if len(parts) != 4:
        return
    user_id = await _identity_or_warn(update)
    if user_id is None:
        return
    try:
        attempt_id = int(parts[2])
        selected_index = int(parts[3])
    except ValueError:
        return
    result = await _study_call(
        "submit_verb_review",
        "telegram",
        user_id,
        attempt_id,
        selected_index,
    )
    if not result.found:
        await _present(update, "Denne repetition findes ikke længere.", _verb_menu())
        return
    if result.already_answered:
        await _present(update, "Dette svar er allerede registreret.", _verb_menu())
        return
    if result.was_correct is None:
        await _present(update, "Ugyldigt svar.", _verb_menu())
        return

    if result.was_correct:
        text = "✅ Korrekt!"
    else:
        text = f"❌ Ikke helt. Det rigtige svar er: {result.correct_answer}."
    if result.verb is not None:
        text += (
            f"\n\nStatus: {result.verb.status}\n"
            f"Succesfulde repetitionstrin: {result.verb.successful_reviews}/5"
        )
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🔁 Næste repetition",
                    callback_data="study:verb:review",
                )
            ],
            [InlineKeyboardButton("⬅️ Verber", callback_data="study:verbs")],
        ]
    )
    await _present(update, text, keyboard)


async def _show_verb_stats(update: Update) -> None:
    user_id = await _identity_or_warn(update)
    if user_id is None:
        return
    stats = await _study_call("get_verb_stats", "telegram", user_id)
    denominator = max(stats["total"], 1)
    percentage = round((stats["mastered"] / denominator) * 100)
    text = "\n".join(
        [
            "🔤 Verber",
            "",
            f"Studeret i alt: {stats['total']}",
            f"🟡 Lærer: {stats['learning']}",
            f"🔁 Skal repeteres: {stats['review']}",
            f"✅ Behersket: {stats['mastered']}",
            "",
            f"Planprogress: {progress_bar(percentage)} {percentage}%",
        ]
    )
    await _present(update, text, _verb_menu())


async def _show_mastered_verbs(update: Update) -> None:
    user_id = await _identity_or_warn(update)
    if user_id is None:
        return
    verbs = await _study_call("get_mastered_verbs", "telegram", user_id)
    if verbs:
        text = "✅ Beherskede verber\n\n" + "\n".join(
            f"{verb.infinitive} — {verb.translation_ru}" for verb in verbs
        )
    else:
        text = "Der er ingen beherskede verber endnu. Et verbum kræver 5 succesfulde repetitionstrin."
    await _present(update, text, _verb_menu())


async def study_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    del context
    query = update.callback_query
    if query is None or not query.data:
        return
    try:
        await query.answer()
    except TelegramError as error:
        # Old or repeatedly pressed callbacks can no longer be acknowledged,
        # but their idempotent database action can still be handled safely.
        logger.info("Could not acknowledge Telegram callback: %s", error)
    data = query.data
    parts = data.split(":")

    if data == "study:menu":
        await _show_learn_menu(update)
    elif data == "study:progress":
        await _show_progress(update)
    elif data == "study:continue":
        await _show_continue(update)
    elif data == "study:history":
        await _show_history(update)
    elif data == "study:review":
        await _show_review(update)
    elif data == "study:verbs":
        await _show_verbs(update)
    elif data == "study:daily":
        await _show_daily_training(update)
    elif data == "study:section:audio":
        user_id = await _identity_or_warn(update)
        if user_id is not None:
            await _study_call(
                "set_current_step",
                "telegram",
                user_id,
                "audio",
                AUDIO_TOPIC,
                AUDIO_NEXT_STEP,
            )
            await _present(
                update,
                "🎧 Send en kort talebesked på dansk om din dag. Opgaven registreres "
                "først, når lydfilen er transskriberet og behandlet.",
                _main_menu(),
            )
    elif data == "study:section:tests":
        await _start_quiz(update, "test")
    elif data == "study:section:grammar":
        await _start_quiz(update, "grammar")
    elif data == "study:section:writing":
        user_id = await _identity_or_warn(update)
        if user_id is not None:
            await _study_call(
                "set_current_step",
                "telegram",
                user_id,
                "writing",
                WRITING_TOPIC,
                WRITING_NEXT_STEP,
            )
            await _present(
                update,
                "✍️ Skriv tre danske sætninger om din dag. Din tekst bliver vurderet, "
                "og konkrete fejl gemmes til senere repetition.",
                _main_menu(),
            )
    elif data.startswith("study:quiz:"):
        await _handle_quiz_answer(update, parts)
    elif data == "study:verb:learn":
        await _learn_verb(update)
    elif data == "study:verb:review":
        await _start_verb_review(update)
    elif data == "study:verb:stats":
        await _show_verb_stats(update)
    elif data == "study:verb:mastered":
        await _show_mastered_verbs(update)
    elif data.startswith("study:verb_answer:"):
        await _handle_verb_answer(update, parts)
    elif data == "study:reset:confirm":
        user_id = await _identity_or_warn(update)
        if user_id is not None:
            await _study_call("reset_progress", "telegram", user_id)
            await _present(update, "Studiehistorikken er slettet.", _main_menu())
    elif data == "study:reset:cancel":
        await _present(update, "Sletningen blev annulleret.", _main_menu())


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
    application.add_handler(CommandHandler("learn", learn_command))
    application.add_handler(CommandHandler("continue", continue_command))
    application.add_handler(CommandHandler("progress", progress_command))
    application.add_handler(CommandHandler("history", history_command))
    application.add_handler(CommandHandler("review", review_command))
    application.add_handler(CommandHandler("reset_progress", reset_progress_command))
    application.add_handler(CommandHandler("exercise", exercise_command))
    application.add_handler(CommandHandler("grammar", grammar_command))
    application.add_handler(CommandHandler("translate", translate_command))
    application.add_handler(CommandHandler("words", words_command))
    application.add_handler(CommandHandler("verbs", verbs_command))
    application.add_handler(CallbackQueryHandler(study_callback, pattern=r"^study:"))
    application.add_handler(
        MessageHandler(filters.VOICE | filters.AUDIO, audio_message)
    )
    application.add_handler(MessageHandler(filters.Document.AUDIO, audio_message))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, text_message)
    )
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

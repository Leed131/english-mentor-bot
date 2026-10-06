"""Telegram support for DU3 Modul 3 Opgave 3 paragraph-gap reading."""
import asyncio
import json
import logging
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select, update as sql_update
from telegram import InlineKeyboardButton as Button, InlineKeyboardMarkup as Markup
from telegram.ext import ApplicationHandlerStop, CallbackQueryHandler, MessageHandler, filters

from database import (
    DialoguePhrase,
    DialoguePhraseProgress,
    TextGapSession,
    utc_now,
)
from opgave3_generator import (
    LETTERS,
    RANK_ORDER,
    TEXT_PHRASES,
    completed_text,
    extract_key_phrases,
    prepare_text_gap,
    validate_text_gap,
)
from speech import generate_speech
from study_memory import get_study_memory

logger = logging.getLogger(__name__)

STATE = "opgave3_input"
PICKS = "opgave3_exam_picks"

TOPICS = [
    "Arbejde og fritid",
    "Sundhed og livsstil",
    "Familie og hverdag",
    "Bolig og naboer",
    "Transport og planer",
    "Skole og uddannelse",
]

RANK_LABELS = {
    "F": "Meget let",
    "E": "Let",
    "D": "Let+",
    "C": "DU3 Modul 3",
    "B": "Svær",
    "A": "Meget svær",
    "S": "Super svær",
}


def keyboard(rows):
    return Markup([[Button(label, callback_data=data) for label, data in row] for row in rows])


def menu():
    return keyboard([
        [("🎓 Som til prøven", "opg3:mode:exam"), ("💡 Øvelse", "opg3:mode:practice")],
        [("▶️ Fortsæt", "opg3:resume")],
        [("⬅️ Test", "study:section:tests")],
    ])


def rank_menu(mode):
    return keyboard([
        [(f"F · {RANK_LABELS['F']}", f"opg3:rank:{mode}:F"),
         (f"E · {RANK_LABELS['E']}", f"opg3:rank:{mode}:E")],
        [(f"D · {RANK_LABELS['D']}", f"opg3:rank:{mode}:D"),
         (f"C · {RANK_LABELS['C']}", f"opg3:rank:{mode}:C")],
        [(f"B · {RANK_LABELS['B']}", f"opg3:rank:{mode}:B"),
         (f"A · {RANK_LABELS['A']}", f"opg3:rank:{mode}:A")],
        [(f"S · {RANK_LABELS['S']}", f"opg3:rank:{mode}:S")],
        [("⬅️ Opgave 3", "opg3:menu")],
    ])


def topic_menu(mode, rank):
    return keyboard(
        [[(topic, f"opg3:new:{mode}:{rank}:{index}")] for index, topic in enumerate(TOPICS)]
        + [[("✍️ Eget emne", f"opg3:topic:{mode}:{rank}")],
           [("⬅️ Rang", f"opg3:mode:{mode}")]]
    )


def snapshot(row):
    return {
        "id": row.id,
        "data": json.loads(row.data_json),
        "answers": json.loads(row.answers_json),
        "mode": row.mode,
        "completed": row.completed,
        "score": row.score,
    }


def _seed_phrases(session):
    existing = {row.phrase: row for row in session.scalars(select(DialoguePhrase)).all()}
    for rank, phrase, translation, category in TEXT_PHRASES:
        row = existing.get(phrase)
        if row is None:
            session.add(DialoguePhrase(
                phrase=phrase,
                translation_ru=translation,
                rank=rank,
                category=f"opg3_{category}",
                active=True,
            ))
        else:
            # Keep one shared phrase memory across dialogue and Opgave 3 practice.
            row.translation_ru = translation
            row.active = True
    session.flush()


def _progress(session, profile_id, phrase_id):
    row = session.scalar(select(DialoguePhraseProgress).where(
        DialoguePhraseProgress.profile_id == profile_id,
        DialoguePhraseProgress.phrase_id == phrase_id,
    ))
    if row is None:
        row = DialoguePhraseProgress(profile_id=profile_id, phrase_id=phrase_id)
        session.add(row)
        session.flush()
    return row


def _apply(progress, verdict):
    now = utc_now()
    progress.last_seen = now
    if verdict == "wrong":
        progress.seen_count += 1
        progress.wrong_count += 1
        progress.successful_reviews = max(0, progress.successful_reviews - 1)
        progress.status = "weak"
        progress.next_review = now
    elif verdict == "correct":
        progress.seen_count += 1
        progress.correct_count += 1
        progress.successful_reviews += 1
        progress.status = "mastered" if progress.successful_reviews >= 3 else "review"
        intervals = (1, 3, 7, 14, 30)
        days = intervals[min(progress.successful_reviews - 1, len(intervals) - 1)]
        progress.next_review = now + timedelta(days=days)
    elif verdict == "unclear":
        progress.unclear_count += 1
        progress.successful_reviews = 0
        progress.status = "weak"
        progress.next_review = now
    elif verdict == "known":
        progress.successful_reviews += 1
        progress.status = "mastered" if progress.successful_reviews >= 3 else "review"
        progress.next_review = now + timedelta(days=3)
    else:
        raise ValueError("Ukendt status.")


def _paragraph_phrase_rows(session, data, index):
    _seed_phrases(session)
    paragraph = data["paragraphs"][index]
    text = " ".join([
        paragraph["before"],
        paragraph["options"][paragraph["answer"]],
        paragraph["after"],
    ]).casefold()
    rows = session.scalars(select(DialoguePhrase).where(DialoguePhrase.active.is_(True))).all()
    return [row for row in rows if row.phrase.casefold() in text]


def db_action(user_id, action, **args):
    memory = get_study_memory()
    with memory.database.session() as session:
        profile = memory._profile(session, "telegram", user_id)
        query = select(TextGapSession).where(TextGapSession.profile_id == profile.id)

        if action == "pause":
            session.execute(sql_update(TextGapSession).where(
                TextGapSession.profile_id == profile.id
            ).values(active=False))
            return

        if action == "recent":
            rows = session.scalars(query.order_by(TextGapSession.id.desc()).limit(12)).all()
            return [snapshot(row) for row in rows]

        if action == "create":
            data = validate_text_gap(args["data"], rank=args["data"].get("rank", "C"))
            session.execute(sql_update(TextGapSession).where(
                TextGapSession.profile_id == profile.id
            ).values(active=False))
            row = TextGapSession(
                profile_id=profile.id,
                data_json=json.dumps(data, ensure_ascii=False),
                answers_json="[]",
                mode=args.get("mode", "exam"),
            )
            session.add(row)
            session.flush()
            profile.current_section = "tests"
            profile.current_topic = "Opgave 3: " + data["topic"]
            profile.next_step = "Opgave 3: Fortsæt"
            return snapshot(row)

        if action == "get":
            row = session.scalar(query.where(TextGapSession.id == args["id"]))
            return snapshot(row) if row else None

        if action == "resume":
            row = session.scalar(
                query.where(TextGapSession.completed.is_(False))
                .order_by(TextGapSession.id.desc()).limit(1)
            )
            if row:
                session.execute(sql_update(TextGapSession).where(
                    TextGapSession.profile_id == profile.id
                ).values(active=False))
                row.active = True
                return snapshot(row)
            return None

        if action == "phrase_cards":
            _seed_phrases(session)
            data = args["data"]
            wanted = extract_key_phrases(data)
            rows = {
                row.phrase: row
                for row in session.scalars(select(DialoguePhrase)).all()
            }
            result = []
            for phrase, translation in wanted:
                row = rows.get(phrase)
                if row is None:
                    continue
                progress = session.scalar(select(DialoguePhraseProgress).where(
                    DialoguePhraseProgress.profile_id == profile.id,
                    DialoguePhraseProgress.phrase_id == row.id,
                ))
                result.append({
                    "id": row.id,
                    "phrase": phrase,
                    "translation": translation,
                    "status": progress.status if progress else "new",
                })
            return result

        if action == "phrase_feedback":
            phrase = session.get(DialoguePhrase, int(args["phrase_id"]))
            if phrase is None:
                return None
            progress = _progress(session, profile.id, phrase.id)
            _apply(progress, args["verdict"])
            return {"phrase": phrase.phrase, "status": progress.status}

        active_query = query.where(
            TextGapSession.active.is_(True),
            TextGapSession.completed.is_(False),
        )
        if "id" in args:
            active_query = active_query.where(TextGapSession.id == args["id"])
        row = session.scalar(active_query.order_by(TextGapSession.id.desc()).limit(1).with_for_update())
        if row is None:
            return None

        if action == "active":
            return snapshot(row)
        if action != "answer":
            raise ValueError("Unknown Opgave 3 action")

        data = json.loads(row.data_json)
        previous = json.loads(row.answers_json)
        answers = args["answers"]
        if row.mode == "exam":
            if previous or len(answers) != 5:
                raise ValueError("Vælg fem svar A-D.")
        elif len(answers) != 1:
            raise ValueError("Vælg ét svar A-D ad gangen.")

        if any(answer not in LETTERS for answer in answers):
            raise ValueError("Brug kun A-D.")

        start = len(previous)
        combined = previous + answers
        if len(combined) > 5:
            raise ValueError("For mange svar.")

        for offset, learner_answer in enumerate(answers):
            index = start + offset
            correct_answer = data["paragraphs"][index]["answer"]
            verdict = "correct" if learner_answer == correct_answer else "wrong"
            for phrase in _paragraph_phrase_rows(session, data, index):
                _apply(_progress(session, profile.id, phrase.id), verdict)

        row.answers_json = json.dumps(combined)
        if len(combined) == 5:
            correct = sum(
                answer == paragraph["answer"]
                for answer, paragraph in zip(combined, data["paragraphs"])
            )
            row.completed = True
            row.active = False
            row.score = round(correct / 5 * 100)
            memory._record_activity(
                session,
                profile,
                "tests",
                "Opgave 3: " + data["topic"],
                row.score,
                correct,
                5 - correct,
                {"opgave3_id": row.id, "answers": combined},
                "Opgave 3: en lignende tekst eller repetition",
            )
        session.flush()
        return snapshot(row)


async def db(user, action, **kwargs):
    return await asyncio.to_thread(db_action, user, action, **kwargs)


async def send(update, text, markup=None):
    import telegram_bot
    chunk = ""
    for line in text.splitlines():
        if len(chunk) + len(line) + 1 > 3800:
            await telegram_bot._reply_text(update, chunk)
            chunk = ""
        chunk += line + "\n"
    await telegram_bot._reply_text(update, chunk.strip(), markup)


def paragraph_text(data, index, reveal=False, learner_answer=None):
    paragraph = data["paragraphs"][index]
    gap = "_____"
    if reveal:
        answer = paragraph["answer"]
        gap = f"{answer} — {paragraph['options'][answer]}"
    elif learner_answer:
        gap = learner_answer
    lines = [
        f"{index + 1}.",
        paragraph["before"],
        f"[{gap}]",
        paragraph["after"],
        "",
    ]
    lines.extend(f"{letter}. {text}" for letter, text in paragraph["options"].items())
    return "\n".join(lines)


def full_exercise_text(item, reveal=False):
    data = item["data"]
    out = [
        f"📖 Opgave 3 · Rang {data.get('rank', 'C')}",
        data["title"],
        "",
    ]
    for index in range(5):
        learner = item["answers"][index] if index < len(item["answers"]) else None
        out.append(paragraph_text(data, index, reveal=reveal, learner_answer=learner))
        out.append("")
    return "\n".join(out).strip()


def exam_keyboard(item_id, picks=None):
    picks = {int(k): v for k, v in dict(picks or {}).items()}
    rows = []
    for index in range(5):
        selected = picks.get(index)
        rows.append([
            (
                ("✅" if letter == selected else "") + f"{index + 1}{letter}",
                f"opg3:pick:{item_id}:{index}:{letter}",
            )
            for letter in LETTERS
        ])
    if len(picks) == 5:
        rows.append([("✅ Tjek svar", f"opg3:submit:{item_id}")])
    else:
        rows.append([("Vælg 5 svar", "opg3:noop")])
    rows.append([("⬅️ Opgave 3", "opg3:menu")])
    return keyboard(rows)


async def show(update, item):
    if item["mode"] == "exam":
        await send(update, full_exercise_text(item), exam_keyboard(item["id"], {}))
        return
    index = len(item["answers"])
    if index >= 5:
        return
    rows = [[
        (letter, f"opg3:answer:{item['id']}:{index}:{letter}")
        for letter in LETTERS
    ], [("⬅️ Opgave 3", "opg3:menu")]]
    await send(
        update,
        f"📖 Opgave 3 · Rang {item['data'].get('rank', 'C')}\n"
        f"{item['data']['title']}\n\n"
        + paragraph_text(item["data"], index),
        keyboard(rows),
    )


async def completed_view(update, user, item):
    await send(update, full_exercise_text(item, reveal=True))
    cards = await db(user, "phrase_cards", data=item["data"])
    if cards:
        lines = ["🔑 Vigtige vendinger"]
        rows = []
        for index, card in enumerate(cards, 1):
            lines.append(f"{index}. {card['phrase']} — {card['translation']}")
            rows.append([
                (f"✅ {index} Forstår", f"opg3:phrase:{card['id']}:known"),
                (f"😕 {index} Uklart", f"opg3:phrase:{card['id']}:unclear"),
            ])
        await send(update, "\n".join(lines), keyboard(rows))
    await send(update, f"Resultatet er gemt: {item['score']}%.", keyboard([
        [("🔊 Lyt til teksten", f"opg3:listen:{item['id']}")],
        [("🔄 En lignende opgave", f"opg3:more:{item['id']}")],
        [("🔁 Repetition", f"opg3:retry:{item['id']}")],
        [("⬅️ Opgave 3", "opg3:menu")],
    ]))


async def grade(update, user, answers, **kwargs):
    try:
        item = await db(user, "answer", answers=answers, **kwargs)
    except ValueError as error:
        await send(update, str(error))
        return
    if not item:
        await send(update, "Opgaven er ikke aktiv længere.", menu())
        return

    if item["mode"] == "exam":
        indices = range(5)
    else:
        indices = [len(item["answers"]) - 1]

    for index in indices:
        paragraph = item["data"]["paragraphs"][index]
        correct = paragraph["answer"]
        icon = "✅" if item["answers"][index] == correct else "❌"
        await send(
            update,
            f"{icon} {index + 1}: dit svar {item['answers'][index]}, rigtigt svar {correct}.\n\n"
            + paragraph["explanation_ru"],
        )

    if item["completed"]:
        await completed_view(update, user, item)
    else:
        await show(update, item)


async def generate(update, user, topic, mode, rank):
    await send(update, "Jeg laver og kontrollerer en ny Opgave 3…")
    recent = await db(user, "recent")
    recent_titles = [item["data"]["title"] for item in recent]
    try:
        data = await asyncio.wait_for(
            prepare_text_gap(topic, rank=rank, recent_titles=recent_titles),
            timeout=85,
        )
    except Exception:
        logger.exception("Opgave 3 generation failed")
        from opgave3_examples import reserve_opgave3
        data = reserve_opgave3(topic, rank=rank, recent_titles=recent_titles)
        if data is None:
            await send(
                update,
                "Jeg kunne ikke lave en entydig tekst lige nu. Prøv igen eller vælg et andet emne.",
                menu(),
            )
            return
        await send(update, "Her er en gennemgået Opgave 3 om samme emne.")

    item = await db(user, "create", data=data, mode=mode)
    await show(update, item)


async def callback(update, context):
    import telegram_bot
    query = update.callback_query
    if query is None or not query.data:
        return
    data = query.data
    if not data.startswith("opg3:"):
        return
    await query.answer()
    user = telegram_bot._study_user_id(update)
    if not user:
        return

    parts = data.split(":")
    action = parts[1]

    if action in {"menu", "mode", "rank", "new", "topic", "more", "retry", "resume"}:
        await db(user, "pause")

    if action == "noop":
        raise ApplicationHandlerStop

    if action == "menu":
        context.user_data.pop(STATE, None)
        context.user_data.pop(PICKS, None)
        await send(
            update,
            "📖 Opgave 3 — læsning\nFem afsnit. I hvert afsnit mangler én sætning. Vælg den sætning, der passer til hele sammenhængen.",
            menu(),
        )

    elif action == "mode":
        mode = parts[2]
        if mode in {"exam", "practice"}:
            await send(
                update,
                "Vælg rang. C svarer cirka til DU3 Modul 3. På B–S bliver svarmulighederne mere ens og mindre forudsigelige.",
                rank_menu(mode),
            )

    elif action == "rank":
        mode, rank = parts[2], parts[3]
        if mode in {"exam", "practice"} and rank in RANK_ORDER:
            await send(
                update,
                f"Rang {rank} · {RANK_LABELS[rank]}\nVælg emne:",
                topic_menu(mode, rank),
            )

    elif action == "topic":
        mode, rank = parts[2], parts[3]
        context.user_data[STATE] = {"mode": mode, "rank": rank}
        await send(update, "Skriv et emne på dansk eller russisk.", menu())

    elif action == "new" and len(parts) == 5:
        mode, rank, index = parts[2], parts[3], parts[4]
        if mode in {"exam", "practice"} and rank in RANK_ORDER and index.isdigit():
            topic_index = int(index)
            if topic_index < len(TOPICS):
                await generate(update, user, TOPICS[topic_index], mode, rank)

    elif action == "pick" and len(parts) == 5:
        item_id, index, letter = parts[2], parts[3], parts[4]
        if item_id.isdigit() and index.isdigit() and letter in LETTERS:
            item = await db(user, "get", id=int(item_id))
            if item and item["mode"] == "exam" and not item["completed"]:
                all_picks = context.user_data.setdefault(PICKS, {})
                picks = dict(all_picks.get(item_id, {}))
                picks[str(int(index))] = letter
                all_picks[item_id] = picks
                try:
                    await query.edit_message_reply_markup(
                        reply_markup=exam_keyboard(int(item_id), picks)
                    )
                except Exception:
                    logger.exception("Could not refresh Opgave 3 answer buttons")
        raise ApplicationHandlerStop

    elif action == "submit" and len(parts) == 3 and parts[2].isdigit():
        item_id = parts[2]
        picks = context.user_data.get(PICKS, {}).get(item_id, {})
        if set(picks) != {str(index) for index in range(5)}:
            await send(update, "Vælg først ét svar til alle fem afsnit.")
        else:
            answers = [picks[str(index)] for index in range(5)]
            await grade(update, user, answers, id=int(item_id))
            context.user_data.get(PICKS, {}).pop(item_id, None)

    elif action == "answer" and len(parts) == 5:
        item_id, index, letter = parts[2], parts[3], parts[4]
        if item_id.isdigit() and index.isdigit() and letter in LETTERS:
            await grade(
                update,
                user,
                [letter],
                id=int(item_id),
                index=int(index),
            )

    elif action == "resume":
        item = await db(user, "resume")
        if item:
            await show(update, item)
        else:
            await send(update, "Der er ingen ufærdig Opgave 3.", menu())

    elif action in {"retry", "more"} and len(parts) == 3 and parts[2].isdigit():
        item = await db(user, "get", id=int(parts[2]))
        if not item:
            await send(update, "Opgaven findes ikke længere.", menu())
        elif action == "retry":
            repeated = await db(user, "create", data=item["data"], mode=item["mode"])
            await show(update, repeated)
        else:
            await generate(
                update,
                user,
                item["data"]["topic"],
                item["mode"],
                item["data"].get("rank", "C"),
            )

    elif action == "phrase" and len(parts) == 4 and parts[2].isdigit():
        verdict = parts[3]
        if verdict in {"known", "unclear"}:
            result = await db(
                user,
                "phrase_feedback",
                phrase_id=int(parts[2]),
                verdict=verdict,
            )
            if result:
                label = "✅ Forstået" if verdict == "known" else "😕 Gemmer som uklar"
                await send(update, f"{label}: {result['phrase']}")

    elif action == "listen" and len(parts) == 3 and parts[2].isdigit():
        item = await db(user, "get", id=int(parts[2]))
        if not item or not item["completed"]:
            await send(update, "Lyd bliver først tilgængelig efter opgaven er afsluttet.")
        else:
            await send(update, "🔊 Jeg laver lyd til den færdige tekst…")
            path = None
            try:
                path = await asyncio.wait_for(
                    generate_speech(
                        completed_text(item["data"]),
                        voice="marin",
                        instructions=(
                            "Read only the supplied Danish text in clear natural Danish. "
                            "Use a calm learner-friendly narrative pace with short pauses between paragraphs. "
                            "Do not translate or explain anything."
                        ),
                        response_format="mp3",
                    ),
                    timeout=90,
                )
                message = update.effective_message
                if message is None:
                    raise RuntimeError("Telegram message missing")
                with open(path, "rb") as audio_file:
                    await message.reply_audio(
                        audio=audio_file,
                        title=item["data"]["title"],
                        caption="🔊 Den færdige tekst på dansk. 🤖 Stemmen er AI-genereret.",
                    )
            except Exception:
                logger.exception("Opgave 3 TTS failed")
                await send(update, "Jeg kunne ikke lave lyden lige nu. Prøv igen om lidt.")
            finally:
                if path:
                    Path(path).unlink(missing_ok=True)

    raise ApplicationHandlerStop


async def text_message(update, context):
    import telegram_bot
    state = context.user_data.get(STATE)
    if not state:
        return
    user = telegram_bot._study_user_id(update)
    if not user:
        return
    text = update.effective_message.text.strip()
    if text.lower() in telegram_bot.MENU_ALIASES | telegram_bot.DU3_OPGAVE2_ALIASES:
        context.user_data.pop(STATE, None)
        return
    if len(text) > 160:
        await send(update, "Skriv et emne på højst 160 tegn.")
    else:
        context.user_data.pop(STATE, None)
        await generate(update, user, text, state["mode"], state["rank"])
    raise ApplicationHandlerStop


def install_opgave3_support():
    import telegram_bot
    if getattr(telegram_bot, "_opgave3_support_installed", False):
        return
    original = telegram_bot.build_telegram_application

    def builder(token):
        app = original(token)
        app.add_handler(CallbackQueryHandler(callback, pattern=r"^opg3:"), group=-5)
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message), group=-5)
        return app

    telegram_bot.build_telegram_application = builder
    telegram_bot._opgave3_support_installed = True

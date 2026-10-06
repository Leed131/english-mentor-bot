"""Telegram support for DU3 Modul 3 Opgave 4: match questions to three people."""
import asyncio
import json
import logging
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select, update as sql_update
from telegram import InlineKeyboardButton as Button, InlineKeyboardMarkup as Markup
from telegram.ext import ApplicationHandlerStop, CallbackQueryHandler, MessageHandler, filters

from database import DialoguePhrase, DialoguePhraseProgress, TextMatchSession, utc_now
from opgave4_generator import (
    PERSONS,
    RANK_ORDER,
    TEXT_MATCH_PHRASES,
    extract_key_phrases,
    prepare_text_match,
    validate_text_match,
)
from speech import generate_speech
from study_memory import get_study_memory

logger = logging.getLogger(__name__)

STATE = "opgave4_input"
PICKS = "opgave4_exam_picks"

TOPICS = [
    "Arbejde og kollegaer",
    "Mad og traditioner",
    "Sundhed og vaner",
    "Familie og fritid",
    "Bolig og hverdagsliv",
    "Rejser og oplevelser",
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
        [("🎓 Som til prøven", "opg4:mode:exam"), ("💡 Øvelse", "opg4:mode:practice")],
        [("📘 Julefrokost-eksemplet", "opg4:source")],
        [("▶️ Fortsæt", "opg4:resume")],
        [("⬅️ Test", "study:section:tests")],
    ])


def rank_menu(mode):
    return keyboard([
        [(f"F · {RANK_LABELS['F']}", f"opg4:rank:{mode}:F"),
         (f"E · {RANK_LABELS['E']}", f"opg4:rank:{mode}:E")],
        [(f"D · {RANK_LABELS['D']}", f"opg4:rank:{mode}:D"),
         (f"C · {RANK_LABELS['C']}", f"opg4:rank:{mode}:C")],
        [(f"B · {RANK_LABELS['B']}", f"opg4:rank:{mode}:B"),
         (f"A · {RANK_LABELS['A']}", f"opg4:rank:{mode}:A")],
        [(f"S · {RANK_LABELS['S']}", f"opg4:rank:{mode}:S")],
        [("⬅️ Opgave 4", "opg4:menu")],
    ])


def topic_menu(mode, rank):
    return keyboard(
        [[(topic, f"opg4:new:{mode}:{rank}:{index}")] for index, topic in enumerate(TOPICS)]
        + [[("✍️ Eget emne", f"opg4:topic:{mode}:{rank}")],
           [("⬅️ Rang", f"opg4:mode:{mode}")]]
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
    for rank, phrase, translation, category in TEXT_MATCH_PHRASES:
        row = existing.get(phrase)
        if row is None:
            session.add(DialoguePhrase(
                phrase=phrase,
                translation_ru=translation,
                rank=rank,
                category=f"opg4_{category}",
                active=True,
            ))
        else:
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


def _question_phrase_rows(session, data, index):
    """Only score useful chunks in the correct person's source text for this question."""
    _seed_phrases(session)
    answer = data["questions"][index]["answer"]
    profile = next(profile for profile in data["profiles"] if profile["label"] == answer)
    text = profile["text"].casefold()
    allowed = {phrase for _, phrase, _, _ in TEXT_MATCH_PHRASES}
    rows = session.scalars(select(DialoguePhrase).where(DialoguePhrase.active.is_(True))).all()
    return [row for row in rows if row.phrase in allowed and row.phrase.casefold() in text]


def _phrase_bank(session, profile_id, rank):
    _seed_phrases(session)
    max_rank = RANK_ORDER.index(rank)
    phrase_meta = {
        phrase: (phrase_rank, translation)
        for phrase_rank, phrase, translation, _ in TEXT_MATCH_PHRASES
        if RANK_ORDER.index(phrase_rank) <= max_rank
    }
    rows = {
        row.phrase: row
        for row in session.scalars(select(DialoguePhrase).where(DialoguePhrase.active.is_(True))).all()
        if row.phrase in phrase_meta
    }
    progress_rows = session.scalars(select(DialoguePhraseProgress).where(
        DialoguePhraseProgress.profile_id == profile_id
    )).all()
    progress = {row.phrase_id: row for row in progress_rows}
    now = utc_now()

    def priority(phrase):
        row = rows.get(phrase)
        item = progress.get(row.id) if row else None
        if item is None:
            return (2, 0, phrase)
        weakness = item.wrong_count * 3 + item.unclear_count * 4 - item.correct_count
        due = item.next_review is not None and item.next_review <= now
        if item.status == "weak":
            bucket = 0
        elif due:
            bucket = 1
        elif item.status == "mastered":
            bucket = 4
        else:
            bucket = 3
        return (bucket, -weakness, phrase)

    ordered = sorted(phrase_meta, key=priority)
    return [(phrase, phrase_meta[phrase][1]) for phrase in ordered]


def db_action(user_id, action, **args):
    memory = get_study_memory()
    with memory.database.session() as session:
        profile = memory._profile(session, "telegram", user_id)
        query = select(TextMatchSession).where(TextMatchSession.profile_id == profile.id)

        if action == "pause":
            session.execute(sql_update(TextMatchSession).where(
                TextMatchSession.profile_id == profile.id
            ).values(active=False))
            return

        if action == "recent":
            rows = session.scalars(query.order_by(TextMatchSession.id.desc()).limit(12)).all()
            return [snapshot(row) for row in rows]

        if action == "phrases":
            rank = args.get("rank", "C")
            if rank not in RANK_ORDER:
                raise ValueError("Ukendt rang.")
            return _phrase_bank(session, profile.id, rank)

        if action == "create":
            raw = args["data"]
            data = validate_text_match(raw, rank=raw.get("rank", "C"))
            session.execute(sql_update(TextMatchSession).where(
                TextMatchSession.profile_id == profile.id
            ).values(active=False))
            row = TextMatchSession(
                profile_id=profile.id,
                data_json=json.dumps(data, ensure_ascii=False),
                answers_json="[]",
                mode=args.get("mode", "exam"),
            )
            session.add(row)
            session.flush()
            profile.current_section = "tests"
            profile.current_topic = "Opgave 4: " + data["topic"]
            profile.next_step = "Opgave 4: Fortsæt"
            return snapshot(row)

        if action == "get":
            row = session.scalar(query.where(TextMatchSession.id == args["id"]))
            return snapshot(row) if row else None

        if action == "resume":
            row = session.scalar(
                query.where(TextMatchSession.completed.is_(False))
                .order_by(TextMatchSession.id.desc()).limit(1)
            )
            if row:
                session.execute(sql_update(TextMatchSession).where(
                    TextMatchSession.profile_id == profile.id
                ).values(active=False))
                row.active = True
                return snapshot(row)
            return None

        if action == "phrase_cards":
            _seed_phrases(session)
            wanted = extract_key_phrases(args["data"])
            rows = {row.phrase: row for row in session.scalars(select(DialoguePhrase)).all()}
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
            item = _progress(session, profile.id, phrase.id)
            _apply(item, args["verdict"])
            return {"phrase": phrase.phrase, "status": item.status}

        active_query = query.where(
            TextMatchSession.active.is_(True),
            TextMatchSession.completed.is_(False),
        )
        if "id" in args:
            active_query = active_query.where(TextMatchSession.id == args["id"])
        row = session.scalar(active_query.order_by(TextMatchSession.id.desc()).limit(1).with_for_update())
        if row is None:
            return None
        if action == "active":
            return snapshot(row)
        if action != "answer":
            raise ValueError("Unknown Opgave 4 action")

        data = json.loads(row.data_json)
        previous = json.loads(row.answers_json)
        if args.get("index", len(previous)) != len(previous):
            return None
        answers = args["answers"]

        if row.mode == "exam":
            if previous or len(answers) != 7:
                raise ValueError("Vælg syv svar A-C.")
        elif len(answers) != 1:
            raise ValueError("Vælg ét svar A-C ad gangen.")
        if any(answer not in PERSONS for answer in answers):
            raise ValueError("Brug kun A, B eller C.")

        start = len(previous)
        combined = previous + answers
        if len(combined) > 7:
            raise ValueError("For mange svar.")

        for offset, learner_answer in enumerate(answers):
            index = start + offset
            correct_answer = data["questions"][index]["answer"]
            verdict = "correct" if learner_answer == correct_answer else "wrong"
            for phrase in _question_phrase_rows(session, data, index):
                _apply(_progress(session, profile.id, phrase.id), verdict)

        row.answers_json = json.dumps(combined)
        if len(combined) == 7:
            correct = sum(
                answer == question["answer"]
                for answer, question in zip(combined, data["questions"])
            )
            row.completed = True
            row.active = False
            row.score = round(correct / 7 * 100)
            memory._record_activity(
                session,
                profile,
                "tests",
                "Opgave 4: " + data["topic"],
                row.score,
                correct,
                7 - correct,
                {"opgave4_id": row.id, "answers": combined},
                "Opgave 4: en lignende tekst eller repetition",
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


def profiles_text(data):
    out = [f"📚 Opgave 4 · Rang {data.get('rank', 'C')}", data["title"], ""]
    for profile in data["profiles"]:
        out.extend([
            f"{profile['label']}. {profile['name']}",
            profile["text"],
            "",
        ])
    return "\n".join(out).strip()


def questions_text(data, answers=None, reveal=False):
    answers = list(answers or [])
    names = "   ".join(f"{p['label']}={p['name']}" for p in data["profiles"])
    out = [names, ""]
    for index, question in enumerate(data["questions"]):
        suffix = ""
        if reveal:
            answer = question["answer"]
            name = next(p["name"] for p in data["profiles"] if p["label"] == answer)
            suffix = f"  → {answer} ({name})"
        elif index < len(answers):
            suffix = f"  [{answers[index]}]"
        out.append(f"{index + 1}. {question['question']}{suffix}")
    return "\n".join(out)


def exam_keyboard(item_id, picks=None):
    picks = {int(k): v for k, v in dict(picks or {}).items()}
    rows = []
    for index in range(7):
        selected = picks.get(index)
        rows.append([
            (
                ("✅" if letter == selected else "") + f"{index + 1}{letter}",
                f"opg4:pick:{item_id}:{index}:{letter}",
            )
            for letter in PERSONS
        ])
    rows.append([
        ("✅ Tjek svar", f"opg4:submit:{item_id}")
        if len(picks) == 7
        else ("Vælg 7 svar", "opg4:noop")
    ])
    rows.append([("⬅️ Opgave 4", "opg4:menu")])
    return keyboard(rows)


async def show(update, item):
    if item["mode"] == "exam":
        await send(
            update,
            profiles_text(item["data"]) + "\n\n" + questions_text(item["data"], item["answers"]),
            exam_keyboard(item["id"], {}),
        )
        return

    index = len(item["answers"])
    if index >= 7:
        return
    if index == 0:
        await send(update, profiles_text(item["data"]))
    question = item["data"]["questions"][index]
    rows = [[
        (
            f"{letter} · {next(p['name'] for p in item['data']['profiles'] if p['label'] == letter)}",
            f"opg4:answer:{item['id']}:{index}:{letter}",
        )
        for letter in PERSONS
    ], [("⬅️ Opgave 4", "opg4:menu")]]
    await send(
        update,
        f"Spørgsmål {index + 1}/7\n{question['question']}",
        keyboard(rows),
    )


async def completed_view(update, user, item):
    await send(
        update,
        profiles_text(item["data"]) + "\n\n" + questions_text(item["data"], reveal=True),
    )
    cards = await db(user, "phrase_cards", data=item["data"])
    if cards:
        lines = ["🔑 Vigtige vendinger"]
        rows = []
        for index, card in enumerate(cards, 1):
            lines.append(f"{index}. {card['phrase']} — {card['translation']}")
            rows.append([
                (f"✅ {index} Forstår", f"opg4:phrase:{card['id']}:known"),
                (f"😕 {index} Uklart", f"opg4:phrase:{card['id']}:unclear"),
            ])
        await send(update, "\n".join(lines), keyboard(rows))
    await send(update, f"Resultatet er gemt: {item['score']}%.", keyboard([
        [("🔊 Lyt til de tre tekster", f"opg4:listen:{item['id']}")],
        [("🔄 En lignende opgave", f"opg4:more:{item['id']}")],
        [("🔁 Repetition", f"opg4:retry:{item['id']}")],
        [("⬅️ Opgave 4", "opg4:menu")],
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

    indices = range(7) if item["mode"] == "exam" else [len(item["answers"]) - 1]
    for index in indices:
        question = item["data"]["questions"][index]
        correct = question["answer"]
        icon = "✅" if item["answers"][index] == correct else "❌"
        await send(
            update,
            f"{icon} {index + 1}: dit svar {item['answers'][index]}, rigtigt svar {correct}.\n\n"
            + question["explanation_ru"],
        )

    if item["completed"]:
        await completed_view(update, user, item)
    else:
        await show(update, item)


async def generate(update, user, topic, mode, rank):
    await send(update, "Jeg laver og kontrollerer en ny Opgave 4…")
    recent = await db(user, "recent")
    recent_titles = [item["data"]["title"] for item in recent]
    phrase_bank = await db(user, "phrases", rank=rank)
    try:
        data = await asyncio.wait_for(
            prepare_text_match(
                topic,
                rank=rank,
                recent_titles=recent_titles,
                phrase_bank=phrase_bank,
            ),
            timeout=85,
        )
    except Exception:
        logger.exception("Opgave 4 generation failed")
        from opgave4_examples import reserve_opgave4
        data = reserve_opgave4(topic, rank=rank, recent_titles=recent_titles)
        if data is None:
            await send(
                update,
                "Jeg kunne ikke lave en entydig Opgave 4 lige nu. Prøv igen eller vælg et andet emne.",
                menu(),
            )
            return
        await send(update, "Her er en gennemgået Opgave 4 om samme emne.")

    item = await db(user, "create", data=data, mode=mode)
    await show(update, item)


async def callback(update, context):
    import telegram_bot
    query = update.callback_query
    if query is None or not query.data or not query.data.startswith("opg4:"):
        return
    await query.answer()
    user = telegram_bot._study_user_id(update)
    if not user:
        return

    parts = query.data.split(":")
    action = parts[1]

    if action in {"menu", "mode", "rank", "new", "topic", "source", "more", "retry", "resume"}:
        await db(user, "pause")

    if action == "noop":
        raise ApplicationHandlerStop

    if action == "menu":
        context.user_data.pop(STATE, None)
        context.user_data.pop(PICKS, None)
        await send(
            update,
            "📚 Opgave 4 — læsning\nTre personer fortæller om samme tema. Match syv spørgsmål med den rigtige person A, B eller C.",
            menu(),
        )

    elif action == "source":
        from opgave4_examples import JULEFROKOST
        item = await db(
            user,
            "create",
            data=validate_text_match(JULEFROKOST, rank="C"),
            mode="exam",
        )
        await show(update, item)

    elif action == "mode":
        mode = parts[2]
        if mode in {"exam", "practice"}:
            await send(
                update,
                "Vælg rang. C svarer cirka til DU3 Modul 3. På B–S bliver spørgsmålene mere parafraserede og mindre forudsigelige.",
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
        if item_id.isdigit() and index.isdigit() and letter in PERSONS:
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
                    logger.exception("Could not refresh Opgave 4 answer buttons")
        raise ApplicationHandlerStop

    elif action == "submit" and len(parts) == 3 and parts[2].isdigit():
        item_id = parts[2]
        picks = context.user_data.get(PICKS, {}).get(item_id, {})
        if set(picks) != {str(index) for index in range(7)}:
            await send(update, "Vælg først ét svar til alle syv spørgsmål.")
        else:
            answers = [picks[str(index)] for index in range(7)]
            await grade(update, user, answers, id=int(item_id))
            context.user_data.get(PICKS, {}).pop(item_id, None)

    elif action == "answer" and len(parts) == 5:
        item_id, index, letter = parts[2], parts[3], parts[4]
        if item_id.isdigit() and index.isdigit() and letter in PERSONS:
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
            await send(update, "Der er ingen ufærdig Opgave 4.", menu())

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
            await send(update, "🔊 Jeg laver lyd til de tre færdige tekster…")
            voices = ("marin", "cedar", "alloy")
            paths = []
            try:
                tasks = [
                    generate_speech(
                        profile["text"],
                        voice=voices[index],
                        instructions=(
                            "Read only the supplied Danish text in clear natural Danish at a calm learner-friendly pace. "
                            "Do not translate, explain, or add words."
                        ),
                        response_format="mp3",
                    )
                    for index, profile in enumerate(item["data"]["profiles"])
                ]
                paths = await asyncio.wait_for(asyncio.gather(*tasks), timeout=90)
                message = update.effective_message
                if message is None:
                    raise RuntimeError("Telegram message missing")
                for profile, path in zip(item["data"]["profiles"], paths):
                    with open(path, "rb") as audio_file:
                        await message.reply_audio(
                            audio=audio_file,
                            title=f"{profile['label']} · {profile['name']}",
                            caption=f"🔊 {profile['label']} · {profile['name']} — AI-genereret stemme.",
                        )
            except Exception:
                logger.exception("Opgave 4 TTS failed")
                await send(update, "Jeg kunne ikke lave lyden lige nu. Prøv igen om lidt.")
            finally:
                for path in paths:
                    try:
                        Path(path).unlink(missing_ok=True)
                    except OSError:
                        logger.warning("Could not remove Opgave 4 audio file")

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


def install_opgave4_support():
    import telegram_bot
    if getattr(telegram_bot, "_opgave4_support_installed", False):
        return
    original = telegram_bot.build_telegram_application

    def builder(token):
        app = original(token)
        app.add_handler(CallbackQueryHandler(callback, pattern=r"^opg4:"), group=-6)
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message), group=-6)
        return app

    telegram_bot.build_telegram_application = builder
    telegram_bot._opgave4_support_installed = True

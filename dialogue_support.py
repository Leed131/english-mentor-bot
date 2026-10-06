"""Telegram reading dialogues, with durable private exercises and attempts."""
import asyncio
import json
import logging
import tempfile
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select, update as sql_update
from telegram import InlineKeyboardButton as Button, InlineKeyboardMarkup as Markup
from telegram.ext import (ApplicationHandlerStop, CallbackQueryHandler, CommandHandler,
                          MessageHandler, filters)

from database import DialoguePhrase, DialoguePhraseProgress, DialogueSession, utc_now
from dialogue_generator import (COMMON_PHRASES, LETTERS, RANKED_PHRASES, RANK_ORDER, parse_answers, prepare_dialogue, validate_dialogue)
from study_memory import get_study_memory

logger = logging.getLogger(__name__)
STATE = "dialogue_input"
EXAM_PICK_KEY = "dialog_exam_picks"
TOPICS = ["Aftaler og transport", "Indkøb og returvarer", "Naboer og bolig",
          "Arbejde og vagter", "Biograf og invitationer", "Familie og skole"]
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
        [("🎓 Som til prøven", "dialog:topics:exam"), ("💡 Øvelse", "dialog:topics:practice")],
        [("➕ Tilføj opgave", "dialog:add"), ("📚 Mine opgaver", "dialog:mine")],
        [("🔁 Øv dine fejl", "dialog:review"), ("▶️ Fortsæt", "dialog:resume")],
        [("🧠 Svage vendinger", "dialog:weak")],
        [("⬅️ Studiemenu", "study:menu")],
    ])


def exam_answer_keyboard(item_id, picks=None):
    """Three answer rows for exam mode; selected letters are unavailable elsewhere."""
    picks = dict(picks or {})
    used = {letter for letter in picks.values() if letter in LETTERS}
    rows = []
    for index in range(3):
        selected = picks.get(index)
        row = []
        for letter in LETTERS:
            if letter == selected:
                label = f"✅{index + 1}{letter}"
                data = f"dialog:pick:{item_id}:{index}:{letter}"
            elif letter in used:
                label = "·"
                data = "dialog:noop"
            else:
                label = f"{index + 1}{letter}"
                data = f"dialog:pick:{item_id}:{index}:{letter}"
            row.append((label, data))
        rows.append(row)
    if len(picks) == 3:
        rows.append([("✅ Tjek svar", f"dialog:submit:{item_id}")])
    else:
        rows.append([("Vælg 3 svar", "dialog:noop")])
    rows.append([("⬅️ Dialoger", "dialog:menu")])
    return keyboard(rows)


def rank_menu(mode):
    return keyboard([
        [(f"F · {RANK_LABELS['F']}", f"dialog:rank:{mode}:F"),
         (f"E · {RANK_LABELS['E']}", f"dialog:rank:{mode}:E")],
        [(f"D · {RANK_LABELS['D']}", f"dialog:rank:{mode}:D"),
         (f"C · {RANK_LABELS['C']}", f"dialog:rank:{mode}:C")],
        [(f"B · {RANK_LABELS['B']}", f"dialog:rank:{mode}:B"),
         (f"A · {RANK_LABELS['A']}", f"dialog:rank:{mode}:A")],
        [(f"S · {RANK_LABELS['S']}", f"dialog:rank:{mode}:S")],
        [("⬅️ Dialoger", "dialog:menu")],
    ])


def topic_menu(mode, rank):
    return keyboard(
        [[(topic, f"dialog:new:{mode}:{rank}:{i}")] for i, topic in enumerate(TOPICS)] +
        [[("✍️ Eget emne", f"dialog:topic:{mode}:{rank}")],
         [("⬅️ Rang", f"dialog:topics:{mode}")]]
    )


def _seed_phrase_bank(session):
    rows = {row.phrase: row for row in session.scalars(select(DialoguePhrase)).all()}
    for rank, phrase, translation, category in RANKED_PHRASES:
        row = rows.get(phrase)
        if row is None:
            session.add(DialoguePhrase(
                phrase=phrase, translation_ru=translation, rank=rank,
                category=category, active=True,
            ))
        else:
            row.translation_ru = translation
            row.rank = rank
            row.category = category
            row.active = True


def _progress_for_phrase(session, profile_id, phrase_id):
    row = session.scalar(
        select(DialoguePhraseProgress).where(
            DialoguePhraseProgress.profile_id == profile_id,
            DialoguePhraseProgress.phrase_id == phrase_id,
        )
    )
    if row is None:
        row = DialoguePhraseProgress(profile_id=profile_id, phrase_id=phrase_id)
        session.add(row)
        session.flush()
    return row


def _review_delay_days(successful_reviews):
    intervals = (1, 3, 7, 14, 30)
    return intervals[min(max(successful_reviews - 1, 0), len(intervals) - 1)]


def _apply_phrase_result(progress, verdict):
    now = utc_now()
    progress.last_seen = now
    if verdict == "correct":
        progress.seen_count += 1
        progress.correct_count += 1
        progress.successful_reviews += 1
        progress.status = "mastered" if progress.successful_reviews >= 3 else "review"
        progress.next_review = now + timedelta(days=_review_delay_days(progress.successful_reviews))
    elif verdict == "wrong":
        progress.seen_count += 1
        progress.wrong_count += 1
        progress.successful_reviews = max(0, progress.successful_reviews - 1)
        progress.status = "weak"
        progress.next_review = now
    elif verdict == "unclear":
        progress.unclear_count += 1
        progress.successful_reviews = 0
        progress.status = "weak"
        progress.next_review = now
    elif verdict == "known":
        progress.successful_reviews += 1
        progress.status = "mastered" if progress.successful_reviews >= 3 else "review"
        progress.next_review = now + timedelta(days=_review_delay_days(progress.successful_reviews))
    else:
        raise ValueError("Ukendt vending-status.")


def _matching_phrase_rows(session, text):
    _seed_phrase_bank(session)
    normalized = text.casefold()
    return [
        row for row in session.scalars(
            select(DialoguePhrase).where(DialoguePhrase.active.is_(True))
        ).all()
        if row.phrase.casefold() in normalized
    ]


def _gap_phrase_rows(session, data, index):
    lines = data["lines"]
    answer = data["answers"][index]
    text = " ".join((lines[index + 2], data["options"][answer], lines[index + 3]))
    rows = _matching_phrase_rows(session, text)
    # One answer can contain a shorter chunk inside a longer one. Keep all useful
    # chunks, but never count the same database phrase twice for one gap.
    return list({row.id: row for row in rows}.values())


def snapshot(row):
    return dict(id=row.id, data=json.loads(row.data_json), answers=json.loads(row.answers_json),
                mode=row.mode, custom=row.custom, completed=row.completed, score=row.score)


def db_action(user_id, action, **args):
    memory = get_study_memory()
    with memory.database.session() as session:
        profile = memory._profile(session, "telegram", user_id)
        query = select(DialogueSession).where(DialogueSession.profile_id == profile.id)
        if action == "phrases":
            rank = args.get("rank", "C")
            if rank not in RANK_ORDER:
                raise ValueError("Ukendt dialograng.")
            _seed_phrase_bank(session)
            session.flush()
            rows = session.scalars(
                select(DialoguePhrase).where(
                    DialoguePhrase.rank == rank,
                    DialoguePhrase.active.is_(True),
                ).order_by(DialoguePhrase.id)
            ).all()
            progress_rows = session.scalars(
                select(DialoguePhraseProgress).where(
                    DialoguePhraseProgress.profile_id == profile.id
                )
            ).all()
            progress = {row.phrase_id: row for row in progress_rows}
            now = utc_now()

            def priority(row):
                item = progress.get(row.id)
                if item is None:
                    return (1, 0, row.id)
                weakness = item.wrong_count * 3 + item.unclear_count * 4 - item.correct_count
                due = item.next_review is not None and item.next_review <= now
                if item.status == "weak":
                    bucket = 0
                elif due:
                    bucket = 1
                elif item.status == "new":
                    bucket = 2
                elif item.status == "review":
                    bucket = 3
                else:
                    bucket = 4
                return (bucket, -weakness, row.id)

            rows.sort(key=priority)
            return [(row.phrase, row.translation_ru) for row in rows]

        if action == "phrase_cards":
            data = args["data"]
            _seed_phrase_bank(session)
            session.flush()
            haystack = " ".join(
                list(data.get("lines", [])) + list(data.get("options", {}).values())
            ).casefold()
            rows = session.scalars(
                select(DialoguePhrase).where(DialoguePhrase.active.is_(True))
            ).all()
            result = []
            for row in rows:
                if row.phrase.casefold() not in haystack:
                    continue
                progress = session.scalar(
                    select(DialoguePhraseProgress).where(
                        DialoguePhraseProgress.profile_id == profile.id,
                        DialoguePhraseProgress.phrase_id == row.id,
                    )
                )
                result.append({
                    "id": row.id,
                    "phrase": row.phrase,
                    "translation": row.translation_ru,
                    "rank": row.rank,
                    "status": progress.status if progress else "new",
                })
            return result[:5]

        if action == "phrase_feedback":
            phrase_id = int(args["phrase_id"])
            phrase = session.get(DialoguePhrase, phrase_id)
            if phrase is None or not phrase.active:
                return None
            progress = _progress_for_phrase(session, profile.id, phrase.id)
            _apply_phrase_result(progress, args["verdict"])
            return {
                "phrase": phrase.phrase,
                "translation": phrase.translation_ru,
                "status": progress.status,
            }

        if action == "weak":
            _seed_phrase_bank(session)
            session.flush()
            phrases = {row.id: row for row in session.scalars(
                select(DialoguePhrase).where(DialoguePhrase.active.is_(True))
            ).all()}
            rows = session.scalars(
                select(DialoguePhraseProgress).where(
                    DialoguePhraseProgress.profile_id == profile.id,
                    DialoguePhraseProgress.status == "weak",
                )
            ).all()
            rows.sort(
                key=lambda row: (
                    -(row.wrong_count * 3 + row.unclear_count * 4 - row.correct_count),
                    row.id,
                )
            )
            result = []
            for row in rows[:8]:
                phrase = phrases.get(row.phrase_id)
                if phrase is None:
                    continue
                result.append({
                    "id": phrase.id,
                    "phrase": phrase.phrase,
                    "translation": phrase.translation_ru,
                    "rank": phrase.rank,
                    "wrong": row.wrong_count,
                    "unclear": row.unclear_count,
                })
            return result
        if action in {"recent", "mine", "review"}:
            if action == "mine":
                query = query.where(DialogueSession.custom.is_(True))
            elif action == "review":
                query = query.where(DialogueSession.completed.is_(True), DialogueSession.score < 100)
            rows = session.scalars(query.order_by(DialogueSession.id.desc()).limit(15)).all()
            return [snapshot(r) for r in rows]
        if action == "pause":
            session.execute(sql_update(DialogueSession).where(
                DialogueSession.profile_id == profile.id).values(active=False))
            return
        if action == "create":
            data = validate_dialogue(args["data"])
            session.execute(sql_update(DialogueSession).where(
                DialogueSession.profile_id == profile.id).values(active=False))
            row = DialogueSession(profile_id=profile.id, data_json=json.dumps(data, ensure_ascii=False),
                                  mode=args.get("mode", "exam"), custom=args.get("custom", False))
            session.add(row)
            session.flush()
            profile.current_section = "tests"
            profile.current_topic = data["topic"]
            profile.next_step = "Dialoger: /dialogues → Fortsæt"
            return snapshot(row)
        if action == "get":
            row = session.scalar(query.where(DialogueSession.id == args["id"]))
            return snapshot(row) if row else None
        if action == "resume":
            row = session.scalar(query.where(DialogueSession.completed.is_(False))
                                 .order_by(DialogueSession.id.desc()).limit(1))
            if row:
                session.execute(sql_update(DialogueSession).where(
                    DialogueSession.profile_id == profile.id).values(active=False))
                row.active = True
                return snapshot(row)
            return None
        query = query.where(DialogueSession.active.is_(True), DialogueSession.completed.is_(False))
        if "id" in args:
            query = query.where(DialogueSession.id == args["id"])
        row = session.scalar(query.order_by(DialogueSession.id.desc()).limit(1).with_for_update())
        if row is None:
            return None
        if action == "active":
            return snapshot(row)
        if action != "answer":
            raise ValueError("Unknown dialogue action")
        data, previous = json.loads(row.data_json), json.loads(row.answers_json)
        if args.get("index", len(previous)) != len(previous):
            return None  # stale inline button: do not count it again
        answers = args["answers"]
        if row.mode == "exam":
            if previous or len(answers) != 3:
                raise ValueError("Skriv alle tre svar, fx 1F 2D 3B.")
        elif len(answers) != 1:
            raise ValueError("I øvelsen skal du svare med ét bogstav A–F ad gangen.")
        combined = previous + answers
        if len(combined) > 3 or len(set(combined)) != len(combined) or any(a not in LETTERS for a in combined):
            raise ValueError("Brug forskellige bogstaver A–F.")

        start_index = len(previous)
        for offset, learner_answer in enumerate(answers):
            gap_index = start_index + offset
            if gap_index >= 3:
                break
            verdict = "correct" if learner_answer == data["answers"][gap_index] else "wrong"
            for phrase in _gap_phrase_rows(session, data, gap_index):
                progress = _progress_for_phrase(session, profile.id, phrase.id)
                _apply_phrase_result(progress, verdict)

        row.answers_json = json.dumps(combined)
        if len(combined) == 3:
            correct = sum(a == b for a, b in zip(combined, data["answers"]))
            row.completed, row.active, row.score = True, False, round(correct / 3 * 100)
            memory._record_activity(session, profile, "tests", data["topic"], row.score,
                                    correct, 3-correct, {"dialogue_id": row.id, "answers": combined},
                                    "Dialoger: en lignende opgave eller øv dine fejl")
        session.flush()
        return snapshot(row)


async def db(user, action, **kwargs):
    return await asyncio.to_thread(db_action, user, action, **kwargs)


def useful_phrases(data, limit=5):
    """Return reusable chunks that actually occur in this exercise."""
    haystack = " ".join(
        list(data.get("lines", [])) + list(data.get("options", {}).values())
    ).casefold()
    found = [(danish, russian) for danish, russian in COMMON_PHRASES
             if danish.casefold() in haystack]
    return found[:limit]


def exercise_text(item, reveal=False):
    data = item["data"]
    a, b = data["speakers"]
    lines = data["lines"]
    rank = data.get("rank", "C")
    out = [f"🧩 Dialoger — læsning · Rang {rank}", data["situation"], "", f"{a}: {lines[0]}", f"{b}: {lines[1]}"]
    for i in range(3):
        out.append(f"{a}: {lines[i+2]}")
        answer = data["answers"][i] if reveal else (item["answers"][i] if i < len(item["answers"]) else None)
        out.append(f"{b}: [{i+1}] " + (f"{answer} — {data['options'][answer]}" if answer else "_____"))
    out.extend([f"{a}: {lines[5]}", "", "Svarmuligheder (tre skal ikke bruges):"])
    out.extend(f"{k}. {v}" for k, v in data["options"].items())
    if not reveal:
        out.extend([
            "",
            "Svar med ét bogstav A–F." if item["mode"] == "practice"
            else "Vælg tre svar med knapperne nedenfor. Du kan også skrive fx 1F 2D 3B eller FDB.",
        ])
    return "\n".join(out)


async def send(update, text, markup=None):
    import telegram_bot
    # Keep every question and explanation in chat history. Split only at line boundaries.
    chunk = ""
    for line in text.splitlines():
        if len(chunk) + len(line) + 1 > 3800:
            await telegram_bot._reply_text(update, chunk)
            chunk = ""
        chunk += line + "\n"
    await telegram_bot._reply_text(update, chunk.strip(), markup)


async def show(update, item):
    if item["mode"] == "exam":
        markup = exam_answer_keyboard(item["id"], {})
    else:
        rows = [[
            (letter, f"dialog:answer:{item['id']}:{len(item['answers'])}:{letter}")
            for letter in LETTERS if letter not in item["answers"]
        ]]
        rows.append([("⬅️ Dialoger", "dialog:menu")])
        markup = keyboard(rows)
    await send(update, exercise_text(item), markup)


async def grade(update, user, answers, **kwargs):
    try:
        item = await db(user, "answer", answers=answers, **kwargs)
    except ValueError as error:
        await send(update, str(error))
        return
    if not item:
        await send(update, "Svaret er allerede gemt, eller opgaven er ikke aktiv. Vælg Fortsæt.", menu())
        return
    indices = range(3) if item["mode"] == "exam" else [len(item["answers"])-1]
    for i in indices:
        correct = item["data"]["answers"][i]
        await send(update, f"{'✅' if item['answers'][i] == correct else '❌'} {i+1}: dit svar {item['answers'][i]}, rigtigt svar {correct}.\n\n"
                   + item["data"]["explanations"][i])
    if item["completed"]:
        await send(update, exercise_text(item, reveal=True))
        phrase_cards = await db(user, "phrase_cards", data=item["data"])
        if phrase_cards:
            lines = ["🗣️ Nyttige vendinger"]
            rows = []
            for index, phrase in enumerate(phrase_cards, 1):
                lines.append(
                    f"{index}. {phrase['phrase']} — {phrase['translation']}"
                )
                rows.append([
                    (f"✅ {index} Forstår", f"dialog:phrase:{phrase['id']}:known"),
                    (f"😕 {index} Uklart", f"dialog:phrase:{phrase['id']}:unclear"),
                ])
            rows.append([("🧠 Svage vendinger", "dialog:weak")])
            await send(update, "\n".join(lines), keyboard(rows))
        await send(update, f"Resultatet er gemt: {item['score']}%.", keyboard([
            [("🔄 En lignende opgave", f"dialog:more:{item['id']}")],
            [("🔁 Repetition", f"dialog:retry:{item['id']}")],
            [("⬅️ Dialoger", "dialog:menu")],
        ]))
    else:
        await show(update, item)


async def generate(update, user, topic, mode, rank="C", phrase_override=None):
    await send(update, "Jeg laver og tjekker en ny dialog…")
    recent = await db(user, "recent")
    situations = [r["data"]["situation"] for r in recent]
    phrase_bank = phrase_override or await db(user, "phrases", rank=rank)
    try:
        data = await asyncio.wait_for(
            prepare_dialogue(topic, situations, rank=rank, phrase_bank=phrase_bank),
            timeout=60,
        )
    except Exception:
        logger.exception("Dialogue generation failed")
        from dialogue_examples import reserve_dialogue
        data = reserve_dialogue(topic, situations)
        if data is None:
            await send(update, "Jeg kunne ikke lave en entydig dialog lige nu. Prøv igen eller vælg et andet emne.", menu())
            return
        notice = "Den nye dialog kunne ikke kontrolleres. Her er en gennemgået øvelse om samme emne."
        if data["situation"] in situations:
            notice += " Du har set den før; du kan bruge den til repetition."
        data["rank"] = rank
        await send(update, notice)
    data["rank"] = rank
    try:
        item = await db(user, "create", data=data, mode=mode)
    except Exception:
        logger.exception("Dialogue save failed")
        await send(update, "Opgaven kunne ikke gemmes. Prøv igen om lidt.", menu())
        return
    await show(update, item)


async def import_draft(update, context, source):
    await send(update, "Jeg læser opgaven og tjekker svarene…")
    try:
        data = await prepare_dialogue("Min opgave", source=source)
    except Exception:
        logger.exception("Dialogue import failed")
        await send(update, "Opgaven kunne ikke kontrolleres. Send hele dialogen, svarmulighederne A–F og facit, hvis du har det.")
        return
    context.user_data[STATE] = {"draft": data}
    await send(update, "Tjek teksten. Hvis noget er forkert, så send hele den rettede tekst igen.")
    await send(update, exercise_text(dict(data=data, answers=[], mode="exam")), keyboard([
        [("✅ Gem og start", "dialog:save")], [("Annuller", "dialog:menu")],
    ]))


async def command(update, context):
    import telegram_bot
    user = telegram_bot._study_user_id(update)
    if not user:
        return
    context.user_data.pop("du3_opgave2_session", None)
    context.user_data.pop(STATE, None)
    context.user_data.pop(EXAM_PICK_KEY, None)
    await db(user, "pause")
    await send(update, "🧩 Dialoger — læsning\nTre huller, seks svar. Læs replikkerne før og efter hvert hul.", menu())
    raise ApplicationHandlerStop


async def callback(update, context):
    import telegram_bot
    query = update.callback_query
    data = query.data
    user = telegram_bot._study_user_id(update)
    if not user:
        return
    if not data.startswith("dialog:"):
        # Switching to another activity must release typed answers to that activity.
        context.user_data.pop(STATE, None)
        await db(user, "pause")
        if data != "study:section:tests":
            return
        await query.answer()
        context.user_data.pop("du3_opgave2_session", None)
        await send(update, "🧪 Test — vælg en type", keyboard([
            [("🧩 Dialoger — læsning", "dialog:menu")],
            [("🧪 Kort A1-test", "dialog:a1")], [("⬅️ Studiemenu", "study:menu")],
        ]))
        raise ApplicationHandlerStop
    await query.answer()
    context.user_data.pop("du3_opgave2_session", None)
    parts = data.split(":")
    action = parts[1]
    if action in {"menu", "topics", "rank", "topic", "weak", "weaktrain", "add", "mine", "review", "a1", "new", "more", "retry", "resume"}:
        context.user_data.pop(STATE, None)
        await db(user, "pause")
    if action == "noop":
        raise ApplicationHandlerStop
    if action == "pick" and len(parts) == 5 and parts[2].isdigit() and parts[3].isdigit():
        item_id = int(parts[2])
        index = int(parts[3])
        letter = parts[4]
        if index not in {0, 1, 2} or letter not in LETTERS:
            raise ApplicationHandlerStop
        item = await db(user, "get", id=item_id)
        if not item or item["mode"] != "exam" or item["completed"]:
            await send(update, "Opgaven er ikke aktiv længere.", menu())
            raise ApplicationHandlerStop
        all_picks = context.user_data.setdefault(EXAM_PICK_KEY, {})
        picks = dict(all_picks.get(str(item_id), {}))
        picks = {int(key): value for key, value in picks.items()}
        # A letter may only be used once. Choosing it for a new gap moves it.
        for other_index, other_letter in list(picks.items()):
            if other_index != index and other_letter == letter:
                picks.pop(other_index, None)
        picks[index] = letter
        all_picks[str(item_id)] = {str(key): value for key, value in picks.items()}
        try:
            await query.edit_message_reply_markup(
                reply_markup=exam_answer_keyboard(item_id, picks)
            )
        except Exception:
            logger.exception("Could not refresh exam answer buttons")
        raise ApplicationHandlerStop
    if action == "submit" and len(parts) == 3 and parts[2].isdigit():
        item_id = int(parts[2])
        all_picks = context.user_data.get(EXAM_PICK_KEY, {})
        raw_picks = all_picks.get(str(item_id), {})
        picks = {int(key): value for key, value in raw_picks.items()}
        if set(picks) != {0, 1, 2}:
            await send(update, "Vælg først ét svar til hver af de tre pladser.")
            raise ApplicationHandlerStop
        answers = [picks[index] for index in range(3)]
        await grade(update, user, answers, id=item_id)
        all_picks.pop(str(item_id), None)
        raise ApplicationHandlerStop
    if action == "menu":
        context.user_data.pop(EXAM_PICK_KEY, None)
        await send(update, "🧩 Dialoger — læsning", menu())
    elif action == "weak":
        weak = await db(user, "weak")
        if not weak:
            await send(
                update,
                "🧠 Du har ingen svage vendinger endnu. De kommer her, når du svarer forkert eller markerer en vending som Uklart.",
                menu(),
            )
        else:
            text = ["🧠 Svage vendinger"]
            text.extend(
                f"• {item['phrase']} — {item['translation']}"
                for item in weak
            )
            await send(
                update,
                "\n".join(text),
                keyboard([
                    [("▶️ Træn svage vendinger", "dialog:weaktrain")],
                    [("⬅️ Dialoger", "dialog:menu")],
                ]),
            )
    elif action == "weaktrain":
        weak = await db(user, "weak")
        if not weak:
            await send(update, "Der er ingen svage vendinger at træne.", menu())
        else:
            rank = max(
                (item["rank"] for item in weak),
                key=lambda value: RANK_ORDER.index(value),
            )
            phrase_bank = [
                (item["phrase"], item["translation"]) for item in weak
            ]
            await generate(
                update,
                user,
                "Hverdag og aftaler",
                "practice",
                rank,
                phrase_override=phrase_bank,
            )
    elif action == "phrase" and len(parts) == 4 and parts[2].isdigit():
        verdict = parts[3]
        if verdict not in {"known", "unclear"}:
            raise ApplicationHandlerStop
        result = await db(
            user,
            "phrase_feedback",
            phrase_id=int(parts[2]),
            verdict=verdict,
        )
        if result:
            label = "✅ Gemmer som forstået" if verdict == "known" else "😕 Gemmer som uklar"
            await send(
                update,
                f"{label}: {result['phrase']}\nStatus: {result['status']}",
            )
    elif action == "a1":
        await telegram_bot._start_quiz(update, "test")
    elif action == "topics":
        mode = parts[2]
        if mode not in {"exam", "practice"}:
            raise ApplicationHandlerStop
        await send(
            update,
            "Vælg rang. F er lettest, S er sværest. C svarer cirka til DU3 Modul 3.",
            rank_menu(mode),
        )
    elif action == "rank":
        mode, rank = parts[2], parts[3]
        if mode not in {"exam", "practice"} or rank not in RANK_ORDER:
            raise ApplicationHandlerStop
        await send(
            update,
            f"Rang {rank} · {RANK_LABELS[rank]}\nVælg en hverdagssituation:",
            topic_menu(mode, rank),
        )
    elif action == "topic":
        mode = parts[2]
        rank = parts[3] if len(parts) > 3 and parts[3] in RANK_ORDER else "C"
        context.user_data[STATE] = {"topic_mode": mode, "topic_rank": rank}
        await send(update, f"Rang {rank}. Skriv et emne, fx at komme for sent på arbejde.", menu())
    elif action == "new":
        if len(parts) >= 5:
            mode, rank, index_text = parts[2], parts[3], parts[4]
        else:
            mode, rank, index_text = parts[2], "C", parts[3]
        if mode in {"exam", "practice"} and rank in RANK_ORDER and index_text.isdigit() and int(index_text) < len(TOPICS):
            await generate(update, user, TOPICS[int(index_text)], mode, rank)
    elif action == "add":
        context.user_data[STATE] = {"import": True}
        await send(update, "Send tekst eller et foto med hele dialogen, tre huller og svarmulighederne A–F. "
                   "Du kan også sende facit. Du får teksten til gennemsyn, før den bliver gemt.", menu())
    elif action == "save":
        draft = context.user_data.get(STATE, {}).get("draft")
        if draft:
            item = await db(user, "create", data=draft, custom=True)
            context.user_data.pop(STATE, None)
            await show(update, item)
        else:
            await send(update, "Kladden er allerede gemt eller ikke tilgængelig. Tilføj opgaven igen.", menu())
    elif action in {"mine", "review"}:
        items = await db(user, action)
        await send(update, "Vælg en opgave:" if items else "Der er ingen opgaver her endnu.", keyboard(
            [[(f"{r['id']}: {r['data']['topic']}", f"dialog:retry:{r['id']}")] for r in items] +
            [[("⬅️ Dialoger", "dialog:menu")]]))
    elif action == "resume":
        item = await db(user, "resume")
        if item:
            await show(update, item)
        else:
            await send(update, "Der er ingen ufærdige dialoger.", menu())
    elif action in {"retry", "more"} and parts[2].isdigit():
        item = await db(user, "get", id=int(parts[2]))
        if not item:
            await send(update, "Opgaven er ikke tilgængelig.", menu())
        elif action == "more":
            await generate(
                update, user, item["data"]["topic"], item["mode"],
                item["data"].get("rank", "C"),
            )
        else:
            await show(update, await db(user, "create", data=item["data"], mode=item["mode"]))
    elif action == "answer" and len(parts) == 5 and parts[2].isdigit() and parts[3].isdigit():
        await grade(update, user, [parts[4]], id=int(parts[2]), index=int(parts[3]))
    raise ApplicationHandlerStop


async def text_message(update, context):
    import telegram_bot
    user = telegram_bot._study_user_id(update)
    if not user:
        return
    text = update.effective_message.text.strip()
    if text.lower() in telegram_bot.MENU_ALIASES | telegram_bot.DU3_OPGAVE2_ALIASES:
        context.user_data.pop(STATE, None)
        context.user_data.pop("du3_opgave2_session", None)
        context.user_data.pop(EXAM_PICK_KEY, None)
        await db(user, "pause")
        return
    state = context.user_data.get(STATE, {})
    if "topic_mode" in state:
        if len(text) > 160:
            await send(update, "Skriv et emne på højst 160 tegn.")
        else:
            context.user_data.pop(STATE, None)
            await generate(
                update, user, text, state["topic_mode"], state.get("topic_rank", "C")
            )
    elif state.get("import") or state.get("draft"):
        if len(text) > 10000:
            await send(update, "Send én opgave på højst 10.000 tegn.")
        else:
            await import_draft(update, context, text)
    else:
        item = await db(user, "active")
        if not item:
            return
        try:
            answers = parse_answers(text) if item["mode"] == "exam" else [text.upper().translate(str.maketrans("АВСЕ", "ABCE"))]
            await grade(update, user, answers, id=item["id"])
        except ValueError as error:
            await send(update, str(error))
    raise ApplicationHandlerStop


async def photo_message(update, context):
    state = context.user_data.get(STATE, {})
    if not (state.get("import") or state.get("draft")):
        return
    from vision import analyze_image_file
    message = update.effective_message
    attachment = message.photo[-1] if message.photo else message.document
    if attachment.file_size and attachment.file_size > 10_000_000:
        await send(update, "Send et foto på under 10 MB.")
        raise ApplicationHandlerStop
    suffix = ".jpg" if message.photo else {"image/png": ".png", "image/webp": ".webp"}.get(attachment.mime_type, ".jpg")
    await send(update, "Jeg læser billedet…")
    try:
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / ("dialogue" + suffix))
            file = await context.bot.get_file(attachment.file_id)
            await file.download_to_drive(custom_path=path)
            source = await analyze_image_file(path, "Transcribe the entire Danish dialogue exercise faithfully, "
                "including all surrounding lines, gap numbers, given example and all options A-F. "
                "Label handwritten answers as guesses, not an answer key. Mark unreadable text; do not invent it.")
        await import_draft(update, context, source)
    except Exception:
        logger.exception("Dialogue photo import failed")
        await send(update, "Jeg kunne ikke læse billedet. Send et tydeligere foto eller teksten.")
    raise ApplicationHandlerStop


async def leave_on_command(update, context):
    import telegram_bot
    user = telegram_bot._study_user_id(update)
    if user:
        context.user_data.pop(STATE, None)
        context.user_data.pop(EXAM_PICK_KEY, None)
        await db(user, "pause")


def install_dialogue_support():
    import telegram_bot
    if getattr(telegram_bot, "_dialogue_support_installed", False):
        return
    original = telegram_bot.build_telegram_application
    def builder(token):
        app = original(token)
        app.add_handler(CommandHandler("dialogues", command), group=-4)
        app.add_handler(MessageHandler(filters.COMMAND, leave_on_command), group=-4)
        app.add_handler(CallbackQueryHandler(callback, pattern=r"^(dialog:|study:|du3op2:|topicquiz:)"), group=-4)
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message), group=-4)
        app.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, photo_message), group=-4)
        return app
    telegram_bot.build_telegram_application = builder
    telegram_bot.HELP_TEXT += "\n/dialogues — dialoger med huller, A–F"
    telegram_bot._dialogue_support_installed = True

"""Telegram support for a DU3-style six-gap word-bank reading exercise (shown as Opgave 1)."""
import asyncio
import json
import logging
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select, update as sql_update
from telegram import InlineKeyboardButton as Button, InlineKeyboardMarkup as Markup
from telegram.ext import ApplicationHandlerStop, CallbackQueryHandler, MessageHandler, filters

from database import DialoguePhrase, DialoguePhraseProgress, WordGapSession, utc_now
from opgave1_generator import (
    FOCUS_BANK,
    RANK_ORDER,
    completed_text,
    prepare_word_gap,
    validate_word_gap,
)
from speech import generate_speech
from study_memory import get_study_memory

logger = logging.getLogger(__name__)

STATE = "opgave1_input"

TOPICS = [
    "Arbejde og hverdag",
    "Butik og indkøb",
    "Skole og uddannelse",
    "Sundhed og fritid",
    "Familie og bolig",
    "Transport og planer",
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
        [("🎓 Som til prøven", "opg1:mode:exam"), ("💡 Øvelse", "opg1:mode:practice")],
        [("📘 En gammel drøm", "opg1:source")],
        [("🧠 Hvilke ord trænes?", "opg1:types")],
        [("▶️ Fortsæt", "opg1:resume")],
        [("⬅️ Test", "study:section:tests")],
    ])


def rank_menu(mode):
    return keyboard([
        [(f"F · {RANK_LABELS['F']}", f"opg1:rank:{mode}:F"),
         (f"E · {RANK_LABELS['E']}", f"opg1:rank:{mode}:E")],
        [(f"D · {RANK_LABELS['D']}", f"opg1:rank:{mode}:D"),
         (f"C · {RANK_LABELS['C']}", f"opg1:rank:{mode}:C")],
        [(f"B · {RANK_LABELS['B']}", f"opg1:rank:{mode}:B"),
         (f"A · {RANK_LABELS['A']}", f"opg1:rank:{mode}:A")],
        [(f"S · {RANK_LABELS['S']}", f"opg1:rank:{mode}:S")],
        [("⬅️ Opgave 1", "opg1:menu")],
    ])


def topic_menu(mode, rank):
    return keyboard(
        [[(topic, f"opg1:new:{mode}:{rank}:{index}")] for index, topic in enumerate(TOPICS)]
        + [[("✍️ Eget emne", f"opg1:topic:{mode}:{rank}")],
           [("⬅️ Rang", f"opg1:mode:{mode}")]]
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


def _seed_focus_bank(session):
    rows = {row.phrase: row for row in session.scalars(select(DialoguePhrase)).all()}
    for rank, phrase, translation, category in FOCUS_BANK:
        row = rows.get(phrase)
        if row is None:
            session.add(DialoguePhrase(
                phrase=phrase,
                translation_ru=translation,
                rank=rank,
                category=f"opg1_{category}",
                active=True,
            ))
        else:
            row.translation_ru = translation
            row.active = True
    session.flush()


def _focus_row(session, data, index):
    _seed_focus_bank(session)
    focus = data["focus"][index]
    row = session.scalar(select(DialoguePhrase).where(
        DialoguePhrase.phrase == focus["phrase"]
    ))
    if row is None:
        row = DialoguePhrase(
            phrase=focus["phrase"],
            translation_ru=focus["translation_ru"],
            rank=data.get("rank", "C"),
            category=f"opg1_{focus['category']}",
            active=True,
        )
        session.add(row)
        session.flush()
    return row


def _phrase_bank(session, profile_id, rank):
    _seed_focus_bank(session)
    max_rank = RANK_ORDER.index(rank)
    allowed = {
        phrase: translation
        for phrase_rank, phrase, translation, _ in FOCUS_BANK
        if RANK_ORDER.index(phrase_rank) <= max_rank
    }
    rows = {
        row.phrase: row
        for row in session.scalars(select(DialoguePhrase).where(DialoguePhrase.active.is_(True))).all()
        if row.phrase in allowed
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

    ordered = sorted(allowed, key=priority)
    return [(phrase, allowed[phrase]) for phrase in ordered]


def db_action(user_id, action, **args):
    memory = get_study_memory()
    with memory.database.session() as session:
        profile = memory._profile(session, "telegram", user_id)
        query = select(WordGapSession).where(WordGapSession.profile_id == profile.id)

        if action == "pause":
            session.execute(sql_update(WordGapSession).where(
                WordGapSession.profile_id == profile.id
            ).values(active=False))
            return

        if action == "recent":
            rows = session.scalars(query.order_by(WordGapSession.id.desc()).limit(12)).all()
            return [snapshot(row) for row in rows]

        if action == "phrases":
            rank = args.get("rank", "C")
            if rank not in RANK_ORDER:
                raise ValueError("Ukendt rang.")
            return _phrase_bank(session, profile.id, rank)

        if action == "create":
            raw = args["data"]
            data = validate_word_gap(raw, rank=raw.get("rank", "C"))
            session.execute(sql_update(WordGapSession).where(
                WordGapSession.profile_id == profile.id
            ).values(active=False))
            row = WordGapSession(
                profile_id=profile.id,
                data_json=json.dumps(data, ensure_ascii=False),
                answers_json="[]",
                mode=args.get("mode", "exam"),
            )
            session.add(row)
            session.flush()
            profile.current_section = "tests"
            profile.current_topic = "Opgave 1: " + data["topic"]
            profile.next_step = "Opgave 1: Fortsæt"
            return snapshot(row)

        if action == "get":
            row = session.scalar(query.where(WordGapSession.id == args["id"]))
            return snapshot(row) if row else None

        if action == "resume":
            row = session.scalar(
                query.where(WordGapSession.completed.is_(False))
                .order_by(WordGapSession.id.desc()).limit(1)
            )
            if row:
                session.execute(sql_update(WordGapSession).where(
                    WordGapSession.profile_id == profile.id
                ).values(active=False))
                row.active = True
                return snapshot(row)
            return None

        if action == "phrase_cards":
            data = args["data"]
            result = []
            for index, focus in enumerate(data["focus"]):
                row = _focus_row(session, data, index)
                progress = session.scalar(select(DialoguePhraseProgress).where(
                    DialoguePhraseProgress.profile_id == profile.id,
                    DialoguePhraseProgress.phrase_id == row.id,
                ))
                result.append({
                    "id": row.id,
                    "phrase": focus["phrase"],
                    "translation": focus["translation_ru"],
                    "status": progress.status if progress else "new",
                })
            # de-duplicate repeated focus phrases while preserving order
            seen = set()
            unique = []
            for item in result:
                if item["phrase"].casefold() in seen:
                    continue
                seen.add(item["phrase"].casefold())
                unique.append(item)
            return unique[:6]

        if action == "phrase_feedback":
            phrase = session.get(DialoguePhrase, int(args["phrase_id"]))
            if phrase is None:
                return None
            item = _progress(session, profile.id, phrase.id)
            _apply(item, args["verdict"])
            return {"phrase": phrase.phrase, "status": item.status}

        active_query = query.where(
            WordGapSession.active.is_(True),
            WordGapSession.completed.is_(False),
        )
        if "id" in args:
            active_query = active_query.where(WordGapSession.id == args["id"])
        row = session.scalar(active_query.order_by(WordGapSession.id.desc()).limit(1).with_for_update())
        if row is None:
            return None
        if action == "active":
            return snapshot(row)
        if action != "answer":
            raise ValueError("Unknown Opgave 1 action")

        data = json.loads(row.data_json)
        previous = json.loads(row.answers_json)
        index = args.get("index", len(previous))
        if index != len(previous):
            return None
        answer = args["answer"]
        if answer not in data["word_bank"]:
            raise ValueError("Vælg et ord fra boksen.")
        if answer in previous:
            raise ValueError("Hvert ord må kun bruges én gang.")

        correct = data["answers"][index]
        verdict = "correct" if answer.casefold() == correct.casefold() else "wrong"
        focus_row = _focus_row(session, data, index)
        _apply(_progress(session, profile.id, focus_row.id), verdict)

        combined = previous + [answer]
        row.answers_json = json.dumps(combined, ensure_ascii=False)
        if len(combined) == 6:
            count = sum(
                learner.casefold() == expected.casefold()
                for learner, expected in zip(combined, data["answers"])
            )
            row.completed = True
            row.active = False
            row.score = round(count / 6 * 100)
            memory._record_activity(
                session,
                profile,
                "tests",
                "Opgave 1: " + data["topic"],
                row.score,
                count,
                6 - count,
                {"opgave1_id": row.id, "answers": combined},
                "Opgave 1: en lignende tekst eller repetition",
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


def exercise_text(item, reveal=False):
    data = item["data"]
    segments = data["segments"]
    answers = item["answers"]
    pieces = [f"📝 Opgave 1 · Rang {data.get('rank', 'C')}", data["title"], "", segments[0]]
    for index in range(6):
        if reveal:
            fill = f"[{index + 1}: {data['answers'][index]}]"
        elif index < len(answers):
            fill = f"[{index + 1}: {answers[index]}]"
        else:
            fill = f"[{index + 1}: _____]"
        pieces.extend([fill, segments[index + 1]])
    pieces.extend(["", "Ordboks: " + " · ".join(data["word_bank"])])
    return " ".join(pieces).replace(" \n", "\n").replace("\n ", "\n")


def answer_keyboard(item):
    index = len(item["answers"])
    used = set(item["answers"])
    available = [word for word in item["data"]["word_bank"] if word not in used]
    rows = []
    for start in range(0, len(available), 3):
        rows.append([
            (word, f"opg1:answer:{item['id']}:{index}:{word}")
            for word in available[start:start + 3]
        ])
    rows.append([("⬅️ Opgave 1", "opg1:menu")])
    return keyboard(rows)


async def show(update, item):
    if item["completed"]:
        return
    index = len(item["answers"])
    await send(
        update,
        exercise_text(item) + f"\n\nVælg ord til hul {index + 1}/6:",
        answer_keyboard(item),
    )


async def completed_view(update, user, item):
    await send(update, exercise_text(item, reveal=True))
    cards = await db(user, "phrase_cards", data=item["data"])
    if cards:
        lines = ["🔑 Fokusord og mønstre"]
        rows = []
        for index, card in enumerate(cards, 1):
            lines.append(f"{index}. {card['phrase']} — {card['translation']}")
            rows.append([
                (f"✅ {index} Forstår", f"opg1:phrase:{card['id']}:known"),
                (f"😕 {index} Uklart", f"opg1:phrase:{card['id']}:unclear"),
            ])
        await send(update, "\n".join(lines), keyboard(rows))
    await send(update, f"Resultatet er gemt: {item['score']}%.", keyboard([
        [("🔊 Lyt til teksten", f"opg1:listen:{item['id']}")],
        [("🔄 En lignende opgave", f"opg1:more:{item['id']}")],
        [("🔁 Repetition", f"opg1:retry:{item['id']}")],
        [("⬅️ Opgave 1", "opg1:menu")],
    ]))


async def grade(update, user, answer, item_id, index):
    try:
        item = await db(user, "answer", id=item_id, index=index, answer=answer)
    except ValueError as error:
        await send(update, str(error))
        return
    if not item:
        await send(update, "Svaret er allerede gemt, eller opgaven er ikke aktiv.", menu())
        return

    answered_index = len(item["answers"]) - 1
    if item["mode"] == "practice":
        expected = item["data"]["answers"][answered_index]
        icon = "✅" if item["answers"][answered_index].casefold() == expected.casefold() else "❌"
        await send(
            update,
            f"{icon} Hul {answered_index + 1}: dit svar {item['answers'][answered_index]}, rigtigt svar {expected}.\n\n"
            + item["data"]["explanations_ru"][answered_index],
        )

    if item["completed"]:
        if item["mode"] == "exam":
            for gap_index, learner in enumerate(item["answers"]):
                expected = item["data"]["answers"][gap_index]
                icon = "✅" if learner.casefold() == expected.casefold() else "❌"
                await send(
                    update,
                    f"{icon} Hul {gap_index + 1}: dit svar {learner}, rigtigt svar {expected}.\n\n"
                    + item["data"]["explanations_ru"][gap_index],
                )
        await completed_view(update, user, item)
    else:
        await show(update, item)


async def generate(update, user, topic, mode, rank):
    await send(update, "Jeg laver og kontrollerer en ny Opgave 1… Det tager højst ca. 35 sekunder.")
    recent = await db(user, "recent")
    recent_titles = [item["data"]["title"] for item in recent]
    phrase_bank = await db(user, "phrases", rank=rank)
    try:
        data = await asyncio.wait_for(
            prepare_word_gap(
                topic,
                rank=rank,
                recent_titles=recent_titles,
                phrase_bank=phrase_bank,
            ),
            timeout=35,
        )
    except Exception:
        logger.exception("Opgave 1 generation failed")
        from opgave1_examples import reserve_opgave1
        data = reserve_opgave1(topic, rank=rank, recent_titles=recent_titles)
        if data is None:
            from opgave1_examples import EN_GAMMEL_DROEM
            data = validate_word_gap(EN_GAMMEL_DROEM, rank="C")
            await send(
                update,
                "Den nye opgave kunne ikke kontrolleres, så du får et gennemgået C-eksempel i stedet. Du kan stadig træne formatet nu.",
            )
        else:
            await send(update, "Her er en gennemgået opgave af samme type.")

    item = await db(user, "create", data=data, mode=mode)
    await show(update, item)


async def callback(update, context):
    import telegram_bot
    query = update.callback_query
    if query is None or not query.data or not query.data.startswith("opg1:"):
        return
    await query.answer()
    user = telegram_bot._study_user_id(update)
    if not user:
        return

    context.user_data.pop("du3_opgave2_session", None)
    parts = query.data.split(":")
    action = parts[1]

    if action in {"menu", "mode", "rank", "new", "topic", "source", "more", "retry", "resume"}:
        await db(user, "pause")

    if action == "menu":
        context.user_data.pop(STATE, None)
        await send(
            update,
            "📝 Opgave 1 — manglende ord\nLæs teksten lokalt og vælg seks ord fra en boks med ti. Hvert ord må kun bruges én gang.",
            menu(),
        )

    elif action == "types":
        await send(
            update,
            "🧠 Opgave 1 træner især grammatiske ord i kontekst:\n"
            "• personlige pronominer: han/hun/de → ham/hende/dem\n"
            "• possessiver: sin/sit/sine ↔ hans/hendes/deres\n"
            "• hovedsætningskonjunktioner: og, men, for\n"
            "• ledsætninger: fordi, selvom, at, når, da, mens\n"
            "• relative/spørgeord: som, hvor, hvad, der\n"
            "• adverbier: ikke, også, derfor, aldrig\n"
            "• kun få verber/substantiver/adjektiver.\n\n"
            "På rang C–S skal grammatik- og referenceord være flertallet.",
            menu(),
        )

    elif action == "source":
        from opgave1_examples import EN_GAMMEL_DROEM
        item = await db(
            user,
            "create",
            data=validate_word_gap(EN_GAMMEL_DROEM, rank="C"),
            mode="exam",
        )
        await show(update, item)

    elif action == "mode":
        mode = parts[2]
        if mode in {"exam", "practice"}:
            await send(
                update,
                "Vælg rang. C svarer cirka til DU3 Modul 3. På B–S bliver ordene i boksen mere ens og mindre forudsigelige.",
                rank_menu(mode),
            )

    elif action == "rank":
        mode, rank = parts[2], parts[3]
        if mode in {"exam", "practice"} and rank in RANK_ORDER:
            await send(update, f"Rang {rank} · {RANK_LABELS[rank]}\nVælg emne:", topic_menu(mode, rank))

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

    elif action == "answer" and len(parts) >= 5:
        item_id, index = parts[2], parts[3]
        word = ":".join(parts[4:])
        if item_id.isdigit() and index.isdigit():
            await grade(update, user, word, int(item_id), int(index))

    elif action == "resume":
        item = await db(user, "resume")
        if item:
            await show(update, item)
        else:
            await send(update, "Der er ingen ufærdig Opgave 1.", menu())

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
                            "Read only the supplied Danish text in clear natural Danish at a calm learner-friendly pace. "
                            "Do not translate, explain, or add words."
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
                logger.exception("Opgave 1 TTS failed")
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


def install_opgave1_support():
    import telegram_bot
    if getattr(telegram_bot, "_opgave1_support_installed", False):
        return
    original = telegram_bot.build_telegram_application

    def builder(token):
        app = original(token)
        app.add_handler(CallbackQueryHandler(callback, pattern=r"^opg1:"), group=-7)
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message), group=-7)
        return app

    telegram_bot.build_telegram_application = builder
    telegram_bot._opgave1_support_installed = True

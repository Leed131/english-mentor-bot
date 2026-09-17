"""Telegram reading dialogues, with durable private exercises and attempts."""
import asyncio
import json
import logging
import tempfile
from pathlib import Path

from sqlalchemy import select, update as sql_update
from telegram import InlineKeyboardButton as Button, InlineKeyboardMarkup as Markup
from telegram.ext import (ApplicationHandlerStop, CallbackQueryHandler, CommandHandler,
                          MessageHandler, filters)

from database import DialogueSession
from dialogue_generator import dialogue_signature, LETTERS, parse_answers, prepare_dialogue, validate_dialogue
from study_memory import get_study_memory

logger = logging.getLogger(__name__)
STATE = "dialogue_input"
TOPICS = ["Aftaler og transport", "Indkøb og returvarer", "Naboer og bolig",
          "Arbejde og vagter", "Biograf og invitationer", "Familie og skole"]


def keyboard(rows):
    return Markup([[Button(label, callback_data=data) for label, data in row] for row in rows])


def menu():
    return keyboard([
        [("🎓 Som til prøven", "dialog:topics:exam"), ("💡 Øvelse", "dialog:topics:practice")],
        [("➕ Tilføj opgave", "dialog:add"), ("📚 Mine opgaver", "dialog:mine")],
        [("🔁 Øv dine fejl", "dialog:review"), ("▶️ Fortsæt", "dialog:resume")],
        [("⬅️ Studiemenu", "study:menu")],
    ])


def snapshot(row):
    return dict(id=row.id, data=json.loads(row.data_json), answers=json.loads(row.answers_json),
                mode=row.mode, custom=row.custom, completed=row.completed, score=row.score)


def db_action(user_id, action, **args):
    memory = get_study_memory()
    with memory.database.session() as session:
        profile = memory._profile(session, "telegram", user_id)
        query = select(DialogueSession).where(DialogueSession.profile_id == profile.id)
        if action in {"recent", "mine", "review"}:
            if action == "mine":
                query = query.where(DialogueSession.custom.is_(True))
            elif action == "review":
                query = query.where(DialogueSession.completed.is_(True), DialogueSession.score < 100)
            query = query.order_by(DialogueSession.id.desc())
            if action != "recent":
                query = query.limit(15)
            rows = session.scalars(query).all()
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


def exercise_text(item, reveal=False):
    data = item["data"]
    a, b = data["speakers"]
    lines = data["lines"]
    out = ["🧩 Dialoger — læsning", data["situation"], "", f"{a}: {lines[0]}", f"{b}: {lines[1]} (eksempel)"]
    for i in range(3):
        out.append(f"{a}: {lines[i+2]}")
        answer = data["answers"][i] if reveal else (item["answers"][i] if i < len(item["answers"]) else None)
        out.append(f"{b}: [{i+1}] " + (f"{answer} — {data['options'][answer]}" if answer else "_____"))
    out.extend([f"{a}: {lines[5]}", "", "Svarmuligheder (tre skal ikke bruges):"])
    out.extend(f"{k}. {v}" for k, v in data["options"].items())
    if not reveal:
        out.extend(["", "Svar med ét bogstav A–F." if item["mode"] == "practice" else "Skriv tre svar, fx 1F 2D 3B eller FDB."])
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
    rows = []
    if item["mode"] == "practice":
        rows.append([(letter, f"dialog:answer:{item['id']}:{len(item['answers'])}:{letter}")
                     for letter in LETTERS if letter not in item["answers"]])
    rows.append([("⬅️ Dialoger", "dialog:menu")])
    await send(update, exercise_text(item), keyboard(rows))


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
        await send(update, f"Resultatet er gemt: {item['score']}%.", keyboard([
            [("🔄 En lignende opgave", f"dialog:more:{item['id']}")],
            [("🔁 Repetition", f"dialog:retry:{item['id']}")],
            [("⬅️ Dialoger", "dialog:menu")],
        ]))
    else:
        await show(update, item)


async def generate(update, user, topic, mode):
    await send(update, "Jeg laver og tjekker en ny dialog…")
    recent = await db(user, "recent")
    situations = [r["data"]["situation"] for r in recent]
    try:
        data = await asyncio.wait_for(prepare_dialogue(topic, situations, avoid_dialogues=[r["data"] for r in recent]), timeout=60)
        if dialogue_signature(data) in {dialogue_signature(r["data"]) for r in recent}:
            raise ValueError("Previously shown dialogue")
    except Exception:
        logger.exception("Dialogue generation failed")
        from dialogue_examples import reserve_dialogue
        data = reserve_dialogue(topic, situations)
        if data is None or dialogue_signature(data) in {dialogue_signature(r["data"]) for r in recent}:
            await send(update, "Jeg kunne ikke lave en ny, kontrolleret dialog lige nu. Jeg gentager ikke den gamle. Prøv igen eller vælg et andet emne. Brug Repetition, hvis du vil øve den samme opgave.", menu())
            return
        notice = "Den nye dialog kunne ikke kontrolleres. Her er en gennemgået øvelse om samme emne."
        await send(update, notice)
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
    if action in {"menu", "topics", "topic", "add", "mine", "review", "a1", "new", "more", "retry", "resume"}:
        context.user_data.pop(STATE, None)
        await db(user, "pause")
    if action == "menu":
        await send(update, "🧩 Dialoger — læsning", menu())
    elif action == "a1":
        await telegram_bot._start_quiz(update, "test")
    elif action == "topics":
        mode = parts[2]
        if mode not in {"exam", "practice"}:
            raise ApplicationHandlerStop
        await send(update, "Vælg en hverdagssituation:", keyboard(
            [[(topic, f"dialog:new:{mode}:{i}")] for i, topic in enumerate(TOPICS)] +
            [[("✍️ Eget emne", f"dialog:topic:{mode}")], [("⬅️ Dialoger", "dialog:menu")]]))
    elif action == "topic":
        context.user_data[STATE] = {"topic_mode": parts[2]}
        await send(update, "Skriv et emne, fx at komme for sent på arbejde.", menu())
    elif action == "new":
        if parts[2] in {"exam", "practice"} and parts[3].isdigit() and int(parts[3]) < len(TOPICS):
            await generate(update, user, TOPICS[int(parts[3])], parts[2])
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
            await generate(update, user, item["data"]["topic"], item["mode"])
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
        await db(user, "pause")
        return
    state = context.user_data.get(STATE, {})
    if "topic_mode" in state:
        if len(text) > 160:
            await send(update, "Skriv et emne på højst 160 tegn.")
        else:
            context.user_data.pop(STATE, None)
            await generate(update, user, text, state["topic_mode"])
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

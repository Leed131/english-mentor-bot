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
from dialogue_generator import LETTERS, parse_answers, prepare_dialogue, validate_dialogue
from study_memory import get_study_memory

logger = logging.getLogger(__name__)
STATE = "dialogue_input"
TOPICS = ["Встречи и транспорт", "Покупки и возврат товара", "Соседи и жильё",
          "Работа и смены", "Кино и приглашения", "Семья и школа"]


def keyboard(rows):
    return Markup([[Button(label, callback_data=data) for label, data in row] for row in rows])


def menu():
    return keyboard([
        [("🎓 Как на экзамене", "dialog:topics:exam"), ("💡 Тренировка", "dialog:topics:practice")],
        [("➕ Добавить задание", "dialog:add"), ("📚 Мои задания", "dialog:mine")],
        [("🔁 Повторить ошибки", "dialog:review"), ("▶️ Продолжить", "dialog:resume")],
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
            profile.next_step = "Диалоги: /dialogues → Продолжить"
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
                raise ValueError("Введи все три ответа: 1F 2D 3B.")
        elif len(answers) != 1:
            raise ValueError("В тренировке отвечай по одной букве A–F.")
        combined = previous + answers
        if len(combined) > 3 or len(set(combined)) != len(combined) or any(a not in LETTERS for a in combined):
            raise ValueError("Нужны разные буквы A–F.")
        row.answers_json = json.dumps(combined)
        if len(combined) == 3:
            correct = sum(a == b for a, b in zip(combined, data["answers"]))
            row.completed, row.active, row.score = True, False, round(correct / 3 * 100)
            memory._record_activity(session, profile, "tests", data["topic"], row.score,
                                    correct, 3-correct, {"dialogue_id": row.id, "answers": combined},
                                    "Диалоги: ещё похожее или повторить ошибки")
        session.flush()
        return snapshot(row)


async def db(user, action, **kwargs):
    return await asyncio.to_thread(db_action, user, action, **kwargs)


def exercise_text(item, reveal=False):
    data = item["data"]
    a, b = data["speakers"]
    lines = data["lines"]
    out = ["🧩 Диалоги — чтение", data["situation"], "", f"{a}: {lines[0]}", f"{b}: {lines[1]} (пример)"]
    for i in range(3):
        out.append(f"{a}: {lines[i+2]}")
        answer = data["answers"][i] if reveal else (item["answers"][i] if i < len(item["answers"]) else None)
        out.append(f"{b}: [{i+1}] " + (f"{answer} — {data['options'][answer]}" if answer else "_____"))
    out.extend([f"{a}: {lines[5]}", "", "Варианты (три лишние):"])
    out.extend(f"{k}. {v}" for k, v in data["options"].items())
    if not reveal:
        out.extend(["", "Отвечай одной буквой A–F." if item["mode"] == "practice" else "Введи три буквы: 1F 2D 3B или FDB."])
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
    rows.append([("⬅️ Диалоги", "dialog:menu")])
    await send(update, exercise_text(item), keyboard(rows))


async def grade(update, user, answers, **kwargs):
    try:
        item = await db(user, "answer", answers=answers, **kwargs)
    except ValueError as error:
        await send(update, str(error))
        return
    if not item:
        await send(update, "Этот ответ уже учтён или задание не активно. Открой «Продолжить».", menu())
        return
    indices = range(3) if item["mode"] == "exam" else [len(item["answers"])-1]
    for i in indices:
        correct = item["data"]["answers"][i]
        await send(update, f"{'✅' if item['answers'][i] == correct else '❌'} {i+1}: твой ответ {item['answers'][i]}, правильный {correct}.\n\n"
                   + item["data"]["explanations"][i])
    if item["completed"]:
        await send(update, exercise_text(item, reveal=True))
        await send(update, f"Результат сохранён: {item['score']}%.", keyboard([
            [("🔄 Ещё похожее", f"dialog:more:{item['id']}")],
            [("🔁 Повторить", f"dialog:retry:{item['id']}")],
            [("⬅️ Диалоги", "dialog:menu")],
        ]))
    else:
        await show(update, item)


async def generate(update, user, topic, mode):
    await send(update, "Готовлю и проверяю новый диалог…")
    recent = await db(user, "recent")
    try:
        data = await prepare_dialogue(topic, [r["data"]["situation"] for r in recent])
        item = await db(user, "create", data=data, mode=mode)
    except Exception:
        logger.exception("Dialogue generation failed")
        await send(update, "Не удалось подготовить проверенный диалог. Попробуй ещё раз.", menu())
        return
    await show(update, item)


async def import_draft(update, context, source):
    await send(update, "Читаю задание и проверяю ответы…")
    try:
        data = await prepare_dialogue("Моё задание", source=source)
    except Exception:
        logger.exception("Dialogue import failed")
        await send(update, "Не удалось разобрать однозначное задание. Пришли полный текст: диалог, варианты A–F и ключ, если он есть.")
        return
    context.user_data[STATE] = {"draft": data}
    await send(update, "Проверь распознанный текст. Для исправления пришли полный исправленный текст ещё раз.")
    await send(update, exercise_text(dict(data=data, answers=[], mode="exam")), keyboard([
        [("✅ Сохранить и начать", "dialog:save")], [("Отмена", "dialog:menu")],
    ]))


async def command(update, context):
    import telegram_bot
    user = telegram_bot._study_user_id(update)
    if not user:
        return
    context.user_data.pop("du3_opgave2_session", None)
    context.user_data.pop(STATE, None)
    await db(user, "pause")
    await send(update, "🧩 Диалоги — чтение\nТри пропуска, шесть вариантов. Читай реплики до и после пропуска.", menu())
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
        await send(update, "🧪 Тесты — выбери формат", keyboard([
            [("🧩 Диалоги — чтение", "dialog:menu")],
            [("🧪 Короткий A1-тест", "dialog:a1")], [("⬅️ Studiemenu", "study:menu")],
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
        await send(update, "🧩 Диалоги — чтение", menu())
    elif action == "a1":
        await telegram_bot._start_quiz(update, "test")
    elif action == "topics":
        mode = parts[2]
        if mode not in {"exam", "practice"}:
            raise ApplicationHandlerStop
        await send(update, "Выбери бытовую ситуацию:", keyboard(
            [[(topic, f"dialog:new:{mode}:{i}")] for i, topic in enumerate(TOPICS)] +
            [[("✍️ Своя тема", f"dialog:topic:{mode}")], [("⬅️ Диалоги", "dialog:menu")]]))
    elif action == "topic":
        context.user_data[STATE] = {"topic_mode": parts[2]}
        await send(update, "Напиши тему, например: опоздание на работу.", menu())
    elif action == "new":
        if parts[2] in {"exam", "practice"} and parts[3].isdigit() and int(parts[3]) < len(TOPICS):
            await generate(update, user, TOPICS[int(parts[3])], parts[2])
    elif action == "add":
        context.user_data[STATE] = {"import": True}
        await send(update, "Пришли текст или фото задания: весь диалог с тремя пропусками и варианты A–F. "
                   "Можешь указать правильные буквы. Перед сохранением покажу текст для проверки.", menu())
    elif action == "save":
        draft = context.user_data.get(STATE, {}).get("draft")
        if draft:
            item = await db(user, "create", data=draft, custom=True)
            context.user_data.pop(STATE, None)
            await show(update, item)
        else:
            await send(update, "Черновик уже сохранён или недоступен. Добавь задание снова.", menu())
    elif action in {"mine", "review"}:
        items = await db(user, action)
        await send(update, "Выбери задание:" if items else "Пока нет таких заданий.", keyboard(
            [[(f"{r['id']}: {r['data']['topic']}", f"dialog:retry:{r['id']}")] for r in items] +
            [[("⬅️ Диалоги", "dialog:menu")]]))
    elif action == "resume":
        item = await db(user, "resume")
        if item:
            await show(update, item)
        else:
            await send(update, "Нет незаконченных диалогов.", menu())
    elif action in {"retry", "more"} and parts[2].isdigit():
        item = await db(user, "get", id=int(parts[2]))
        if not item:
            await send(update, "Задание недоступно.", menu())
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
            await send(update, "Сократи тему до 160 символов.")
        else:
            context.user_data.pop(STATE, None)
            await generate(update, user, text, state["topic_mode"])
    elif state.get("import") or state.get("draft"):
        if len(text) > 10000:
            await send(update, "Пришли одно задание длиной до 10 000 символов.")
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
        await send(update, "Пришли фото меньше 10 МБ.")
        raise ApplicationHandlerStop
    suffix = ".jpg" if message.photo else {"image/png": ".png", "image/webp": ".webp"}.get(attachment.mime_type, ".jpg")
    await send(update, "Распознаю фотографию…")
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
        await send(update, "Не удалось прочитать фото. Пришли более чёткое изображение или текст.")
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
    telegram_bot.HELP_TEXT += "\n/dialogues — диалоги с пропусками, A–F"
    telegram_bot._dialogue_support_installed = True

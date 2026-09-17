import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import func, select
from database import DialogueSession, StudyDatabase
from dialogue_generator import parse_answers, prepare_dialogue, validate_dialogue
from dialogue_support import db_action, exercise_text, callback, text_message, STATE
from study_memory import StudyMemory
from telegram.ext import ApplicationHandlerStop


def example():
    return dict(topic="Встреча", situation="Anna og Bo skal mødes på en café.",
        speakers=["Anna", "Bo"],
        lines=["Skal vi mødes i morgen?", "Ja, gerne!", "Kan du klokken tre?",
               "Så mødes vi klokken fire. Skal jeg bestille et bord?",
               "Godt. Jeg bestiller til os begge. Vil du sidde udenfor?",
               "Så tager vi et bord indenfor. Vi ses!"],
        options=dict(A="Ja tak, bestil til to.", B="Nej, det bliver for koldt.",
                     C="Jeg har allerede spist morgenmad.", D="Nej, jeg har først fri klokken fire.",
                     E="Jeg bor i Odense.", F="Min cykel er blå."),
        answers=["D", "A", "B"], explanations=["Объяснение первой связи.", "Объяснение второй связи.", "Объяснение третьей связи."])


class ValidationTests(unittest.TestCase):
    def test_input_formats_and_rejections(self):
        for text in ["1D 2A 3B", "dab", "D, A, B", "1D 2А 3В"]:
            self.assertEqual(parse_answers(text), ["D", "A", "B"])
        for text in ["AAB", "1D 3A 2B", "DAB extra", "AB", "GAB"]:
            with self.assertRaises(ValueError):
                parse_answers(text)

    def test_malformed_payloads_rejected(self):
        for key, value in [("lines", ["x"]), ("answers", ["D", "D", "B"]),
                           ("answers", [0, 1, 2]), ("options", {}),
                           ("explanations", ["", "x", "x"])]:
            raw = example()
            raw[key] = value
            with self.assertRaises(ValueError):
                validate_dialogue(raw)
        raw = example()
        raw["options"]["B"] = raw["options"]["A"]
        with self.assertRaises(ValueError):
            validate_dialogue(raw)

    def test_question_preserves_context_and_hides_key(self):
        text = exercise_text(dict(data=example(), answers=[], mode="exam"))
        for line in example()["lines"]:
            self.assertIn(line, text)
        self.assertIn("[3] _____", text)
        self.assertNotIn("Объяснение", text)
        self.assertNotIn("[1] D", text)
        self.assertLess(len(text), 3800)


class GenerationTests(unittest.IsolatedAsyncioTestCase):
    async def test_blind_solver_and_feedback_verifier(self):
        call = AsyncMock(side_effect=[example(), {"valid":True,"answers":["D","A","B"],"candidates":[["D"],["A"],["B"]]}, {"valid":True}])
        with patch("dialogue_generator._json_call", call):
            self.assertEqual((await prepare_dialogue("кафе"))["answers"], ["D","A","B"])
        blind = json.loads(call.call_args_list[1].args[1])
        self.assertNotIn("answers", blind)
        self.assertNotIn("explanations", blind)

    async def test_ambiguous_generation_never_reaches_learner(self):
        with patch("dialogue_generator._json_call", AsyncMock(side_effect=[example(), {"valid":False}, example(), {"valid":False}, example(), {"valid":False}])):
            with self.assertRaises(ValueError):
                await prepare_dialogue("кафе")


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.url = "sqlite:///" + str(Path(self.temp.name) / "study.db")
        self.memory = StudyMemory(StudyDatabase(self.url))
        self.patch = patch("dialogue_support.get_study_memory", lambda: self.memory)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.memory.database.dispose()
        self.temp.cleanup()

    def test_exam_grades_once_and_keeps_other_users_private(self):
        item = db_action("one", "create", data=example())
        self.assertIsNone(db_action("two", "get", id=item["id"]))
        self.assertIsNone(db_action("two", "answer", id=item["id"], answers=["D","A","B"]))
        graded = db_action("one", "answer", id=item["id"], answers=["D","A","B"])
        self.assertEqual(graded["score"], 100)
        self.assertIsNone(db_action("one", "answer", id=item["id"], answers=["D","A","B"]))
        self.assertEqual(self.memory.get_test_stats("telegram", "one")["count"], 1)

    def test_practice_stale_buttons_and_resume_after_restart(self):
        item = db_action("one", "create", data=example(), mode="practice")
        db_action("one", "answer", id=item["id"], index=0, answers=["D"])
        self.assertIsNone(db_action("one", "answer", id=item["id"], index=0, answers=["D"]))
        self.assertEqual(self.memory.get_test_stats("telegram", "one")["count"], 0)
        db_action("one", "pause")
        self.assertIsNone(db_action("one", "active"))
        self.memory.database.dispose()
        self.memory = StudyMemory(StudyDatabase(self.url))
        self.assertEqual(db_action("one", "resume")["answers"], ["D"])
        db_action("one", "answer", index=1, answers=["A"])
        self.assertEqual(db_action("one", "answer", index=2, answers=["B"])["score"], 100)

    def test_custom_exercises_errors_and_reset(self):
        item = db_action("one", "create", data=example(), custom=True)
        self.assertEqual(db_action("one", "mine")[0]["id"], item["id"])
        db_action("one", "answer", answers=["A","D","B"])
        self.assertEqual(len(db_action("one", "review")), 1)
        self.memory.reset_progress("telegram", "one")
        self.assertEqual(db_action("one", "mine"), [])
        with self.memory.database.session() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(DialogueSession)), 0)


class RoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_test_menu_intercepts_old_quiz_start(self):
        query = SimpleNamespace(data="study:section:tests", answer=AsyncMock())
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(user_data={"du3_opgave2_session": {}, STATE: {"import": True}})
        with patch("telegram_bot._study_user_id", return_value="one"), patch("dialogue_support.db", AsyncMock()), patch("dialogue_support.send", AsyncMock()) as send:
            with self.assertRaises(ApplicationHandlerStop):
                await callback(update, context)
        buttons = [b.callback_data for row in send.call_args.args[2].inline_keyboard for b in row]
        self.assertIn("dialog:a1", buttons)
        self.assertIn("dialog:menu", buttons)
        self.assertEqual(context.user_data, {})

    async def test_menu_alias_releases_dialogue_and_du3(self):
        update = SimpleNamespace(effective_message=SimpleNamespace(text="меню"))
        context = SimpleNamespace(user_data={STATE: {"import":True}, "du3_opgave2_session":{}})
        with patch("telegram_bot._study_user_id", return_value="one"), patch("dialogue_support.db", AsyncMock()) as db:
            await text_message(update, context)
        db.assert_awaited_once_with("one", "pause")
        self.assertEqual(context.user_data, {})

    async def test_stale_answer_does_not_grade_different_dialogue(self):
        update = SimpleNamespace(callback_query=SimpleNamespace(data="dialog:answer:42:1:A", answer=AsyncMock()))
        context = SimpleNamespace(user_data={})
        with patch("telegram_bot._study_user_id", return_value="one"), patch("dialogue_support.grade", AsyncMock()) as grade:
            with self.assertRaises(ApplicationHandlerStop):
                await callback(update, context)
        grade.assert_awaited_once_with(update, "one", ["A"], id=42, index=1)

class InstallationTests(unittest.TestCase):
    def test_all_extensions_register_together(self):
        import os
        import telegram_bot
        from du3_opgave2_support import install_du3_opgave2_support
        from telegram_image_support import install_telegram_image_support
        from topic_quiz_support import install_topic_quiz_support
        from dialogue_support import install_dialogue_support
        from telegram.ext import CommandHandler
        environment = {k:v for k,v in os.environ.items() if not k.lower().endswith('_proxy')}
        with patch.dict(os.environ, environment, clear=True):
            install_telegram_image_support()
            install_topic_quiz_support()
            install_du3_opgave2_support()
            install_dialogue_support()
            app = telegram_bot.build_telegram_application("123:TEST")
        self.assertTrue({-4, -3, -2, 0}.issubset(app.handlers))
        self.assertTrue(any(isinstance(h, CommandHandler) and "dialogues" in h.commands
                            for h in app.handlers[-4]))
        before = telegram_bot.build_telegram_application
        install_dialogue_support()
        self.assertIs(before, telegram_bot.build_telegram_application)


class ImportRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_draft_is_previewed_before_save(self):
        from dialogue_support import import_draft
        context = SimpleNamespace(user_data={STATE:{"import":True}})
        with patch("dialogue_support.prepare_dialogue", AsyncMock(return_value=example())), patch("dialogue_support.send", AsyncMock()), patch("dialogue_support.db", AsyncMock()) as db:
            await import_draft(object(), context, "source text")
        db.assert_not_called()
        self.assertEqual(context.user_data[STATE]["draft"], example())

    async def test_resume_clears_import_state(self):
        update = SimpleNamespace(callback_query=SimpleNamespace(data="dialog:resume", answer=AsyncMock()))
        context = SimpleNamespace(user_data={STATE:{"draft":example()}})
        with patch("telegram_bot._study_user_id", return_value="one"), patch("dialogue_support.db", AsyncMock(return_value=None)), patch("dialogue_support.send", AsyncMock()):
            with self.assertRaises(ApplicationHandlerStop):
                await callback(update, context)
        self.assertNotIn(STATE, context.user_data)

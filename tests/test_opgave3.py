import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import func, select

from database import StudyDatabase, TextGapSession
from opgave3_examples import ADRIAN, reserve_opgave3
from opgave3_generator import (
    RANK_ORDER,
    completed_text,
    extract_key_phrases,
    prepare_text_gap,
    validate_text_gap,
)
from opgave3_support import (
    PICKS,
    STATE,
    callback,
    db_action,
    exam_keyboard,
)
from study_memory import StudyMemory
from telegram.ext import ApplicationHandlerStop


class Opgave3ValidationTests(unittest.TestCase):
    def test_adrian_source_is_valid_and_key_is_expected(self):
        data = validate_text_gap(ADRIAN, rank="C")
        self.assertEqual(
            [paragraph["answer"] for paragraph in data["paragraphs"]],
            ["C", "B", "B", "A", "C"],
        )
        self.assertEqual(len(data["paragraphs"]), 5)
        self.assertEqual(data["title"], "Adrians nye livsstil")

    def test_completed_text_inserts_answers(self):
        data = validate_text_gap(ADRIAN, rank="C")
        text = completed_text(data)
        self.assertIn("Det er altid rart med lidt ekstra penge.", text)
        self.assertIn("Derfor vil han i gang med at spille håndbold igen.", text)
        self.assertNotIn("Han sparer alle pengene op.", text)

    def test_key_phrases_are_reusable_not_trivial(self):
        data = validate_text_gap(ADRIAN, rank="C")
        phrases = dict(extract_key_phrases(data))
        self.assertIn("komme i gang med at", phrases)
        self.assertIn("i fremtiden", phrases)
        self.assertIn("plejer at", phrases)

    def test_rank_order_and_reserve(self):
        self.assertEqual(RANK_ORDER, ("F", "E", "D", "C", "B", "A", "S"))
        reserve = reserve_opgave3("Sundhed og livsstil", rank="C", recent_titles=())
        self.assertIsNotNone(reserve)
        self.assertIsNone(
            reserve_opgave3(
                "Sundhed og livsstil",
                rank="C",
                recent_titles=("Adrians nye livsstil",),
            )
        )

    def test_exam_keyboard_has_five_answer_rows(self):
        markup = exam_keyboard(42, {"0": "C", "1": "B"})
        self.assertEqual(len(markup.inline_keyboard), 7)
        self.assertEqual(markup.inline_keyboard[0][2].text, "✅1C")
        self.assertEqual(markup.inline_keyboard[1][1].text, "✅2B")
        completed = exam_keyboard(
            42, {"0": "C", "1": "B", "2": "B", "3": "A", "4": "C"}
        )
        self.assertEqual(
            completed.inline_keyboard[5][0].callback_data,
            "opg3:submit:42",
        )


class Opgave3PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.url = "sqlite:///" + str(Path(self.temp.name) / "study.db")
        self.memory = StudyMemory(StudyDatabase(self.url))
        self.patch = patch("opgave3_support.get_study_memory", lambda: self.memory)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.memory.database.dispose()
        self.temp.cleanup()

    def test_exam_persists_and_scores(self):
        item = db_action(
            "one",
            "create",
            data=validate_text_gap(ADRIAN, rank="C"),
            mode="exam",
        )
        result = db_action(
            "one",
            "answer",
            id=item["id"],
            answers=["C", "B", "B", "A", "C"],
        )
        self.assertTrue(result["completed"])
        self.assertEqual(result["score"], 100)
        with self.memory.database.session() as session:
            self.assertEqual(
                session.scalar(select(func.count()).select_from(TextGapSession)),
                1,
            )

    def test_practice_advances_one_paragraph_at_a_time(self):
        item = db_action(
            "one",
            "create",
            data=validate_text_gap(ADRIAN, rank="C"),
            mode="practice",
        )
        first = db_action(
            "one",
            "answer",
            id=item["id"],
            index=0,
            answers=["C"],
        )
        self.assertEqual(first["answers"], ["C"])
        self.assertFalse(first["completed"])


class Opgave3RoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_menu_opens(self):
        query = SimpleNamespace(data="opg3:menu", answer=AsyncMock())
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(user_data={PICKS: {}, STATE: {}})
        with patch("telegram_bot._study_user_id", return_value="one"), patch(
            "opgave3_support.db", AsyncMock(return_value=None)
        ), patch("opgave3_support.send", AsyncMock()) as send:
            with self.assertRaises(ApplicationHandlerStop):
                await callback(update, context)
        self.assertIn("Opgave 3", send.call_args.args[1])
        self.assertNotIn(PICKS, context.user_data)
        self.assertNotIn(STATE, context.user_data)


class Opgave3GenerationTests(unittest.IsolatedAsyncioTestCase):
    async def test_high_rank_prompt_demands_less_predictable_logic(self):
        raw = validate_text_gap(ADRIAN, rank="S")
        review = {
            "valid": True,
            "answers": ["C", "B", "B", "A", "C"],
            "candidates": [["C"], ["B"], ["B"], ["A"], ["C"]],
            "reason": "",
        }
        calls = AsyncMock(side_effect=[raw, review, {"valid": True, "reason": ""}])
        with patch("opgave3_generator._json_call", calls):
            result = await prepare_text_gap("arbejde", rank="S")
        self.assertEqual(result["rank"], "S")
        generation_prompt = calls.call_args_list[0].args[1]
        self.assertIn("Do NOT make every answer depend on an obvious connector", generation_prompt)


if __name__ == "__main__":
    unittest.main()

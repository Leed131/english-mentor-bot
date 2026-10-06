import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from sqlalchemy import func, select

from database import StudyDatabase, TextMatchSession
from opgave4_examples import JULEFROKOST, reserve_opgave4
from opgave4_generator import (
    RANK_ORDER,
    extract_key_phrases,
    prepare_text_match,
    validate_text_match,
)
from opgave4_support import db_action, exam_keyboard
from study_memory import StudyMemory


class Opgave4ValidationTests(unittest.TestCase):
    def test_source_key_matches_the_printed_exercise(self):
        data = validate_text_match(JULEFROKOST, rank="C")
        self.assertEqual(
            [question["answer"] for question in data["questions"]],
            ["A", "C", "A", "C", "B", "A", "B"],
        )
        self.assertEqual([p["name"] for p in data["profiles"]], ["Meng", "Hanna", "Ivan"])

    def test_key_phrases_are_meaningful_chunks(self):
        data = validate_text_match(JULEFROKOST, rank="C")
        phrases = dict(extract_key_phrases(data))
        self.assertIn("gøre et godt indtryk", phrases)
        self.assertIn("som det plejer at være", phrases)
        self.assertIn("blev nødt til at", phrases)

    def test_rank_order_and_source_reserve(self):
        self.assertEqual(RANK_ORDER, ("F", "E", "D", "C", "B", "A", "S"))
        self.assertIsNotNone(
            reserve_opgave4("Mad og traditioner", rank="C", recent_titles=())
        )
        self.assertIsNone(
            reserve_opgave4("Mad og traditioner", rank="B", recent_titles=())
        )

    def test_exam_keyboard_has_seven_rows(self):
        markup = exam_keyboard(42, {"0": "A", "1": "C"})
        self.assertEqual(len(markup.inline_keyboard), 9)
        self.assertEqual(markup.inline_keyboard[0][0].text, "✅1A")
        self.assertEqual(markup.inline_keyboard[1][2].text, "✅2C")
        completed = exam_keyboard(
            42,
            {"0": "A", "1": "C", "2": "A", "3": "C", "4": "B", "5": "A", "6": "B"},
        )
        self.assertEqual(
            completed.inline_keyboard[7][0].callback_data,
            "opg4:submit:42",
        )


class Opgave4PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.url = "sqlite:///" + str(Path(self.temp.name) / "study.db")
        self.memory = StudyMemory(StudyDatabase(self.url))
        self.patch = patch("opgave4_support.get_study_memory", lambda: self.memory)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.memory.database.dispose()
        self.temp.cleanup()

    def test_exam_scores_and_persists(self):
        item = db_action(
            "one",
            "create",
            data=validate_text_match(JULEFROKOST, rank="C"),
            mode="exam",
        )
        result = db_action(
            "one",
            "answer",
            id=item["id"],
            answers=["A", "C", "A", "C", "B", "A", "B"],
        )
        self.assertTrue(result["completed"])
        self.assertEqual(result["score"], 100)
        with self.memory.database.session() as session:
            self.assertEqual(
                session.scalar(select(func.count()).select_from(TextMatchSession)),
                1,
            )

    def test_practice_answers_one_question_at_a_time(self):
        item = db_action(
            "one",
            "create",
            data=validate_text_match(JULEFROKOST, rank="C"),
            mode="practice",
        )
        first = db_action(
            "one",
            "answer",
            id=item["id"],
            index=0,
            answers=["A"],
        )
        self.assertEqual(first["answers"], ["A"])
        self.assertFalse(first["completed"])


class Opgave4GenerationTests(unittest.IsolatedAsyncioTestCase):
    async def test_high_rank_prompt_requires_paraphrase_not_keyword_matching(self):
        raw = validate_text_match(JULEFROKOST, rank="S")
        review = {
            "valid": True,
            "answers": ["A", "C", "A", "C", "B", "A", "B"],
            "candidates": [["A"], ["C"], ["A"], ["C"], ["B"], ["A"], ["B"]],
            "reason": "",
        }
        calls = AsyncMock(side_effect=[raw, review, {"valid": True, "reason": ""}])
        with patch("opgave4_generator._json_call", calls):
            result = await prepare_text_match("traditioner", rank="S")
        self.assertEqual(result["rank"], "S")
        prompt = calls.call_args_list[0].args[1]
        self.assertIn("do not let a single shared keyword reveal the person", prompt)


if __name__ == "__main__":
    unittest.main()

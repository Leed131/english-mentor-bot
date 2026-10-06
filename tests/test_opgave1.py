import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from sqlalchemy import func, select

from database import StudyDatabase, WordGapSession
from opgave1_examples import EN_GAMMEL_DROEM, reserve_opgave1
from opgave1_generator import (
    RANK_ORDER,
    WORD_TYPE_RULES,
    completed_text,
    prepare_word_gap,
    validate_word_gap,
)
from opgave1_support import answer_keyboard, db_action
from study_memory import StudyMemory


class Opgave1ValidationTests(unittest.TestCase):
    def test_generated_gap_template_is_parsed(self):
        raw = dict(EN_GAMMEL_DROEM)
        raw.pop("segments")
        raw["text_with_gaps"] = (
            "Hun kender børnetøj, [[1]] hun har arbejdet i en butik. "
            "Hun har [[2]] været i en skobutik. [[3]] i hendes butik er der kun tøj. "
            "Der [[4]] er kemikalier i tøjet. Lige nu [[5]] hun travlt. "
            "Hun er glad for sin egen [[6]]."
        )
        data = validate_word_gap(raw, rank="C")
        self.assertEqual(len(data["segments"]), 7)
        self.assertIn("hun har arbejdet", data["segments"][1])

    def test_source_answers_match_user_sheet(self):
        data = validate_word_gap(EN_GAMMEL_DROEM, rank="C")
        self.assertEqual(
            data["answers"],
            ["fordi", "også", "men", "ikke", "har", "butik"],
        )
        self.assertEqual(len(data["word_bank"]), 10)
        self.assertEqual(len(set(data["answers"])), 6)

    def test_source_word_types_match_exam_pattern(self):
        data = validate_word_gap(EN_GAMMEL_DROEM, rank="C")
        types = data["word_types"]
        self.assertEqual(types["fordi"], "conjunction")
        self.assertEqual(types["også"], "adverb")
        self.assertEqual(types["ikke"], "negation")
        self.assertEqual(types["har"], "verb")
        self.assertEqual(types["butik"], "noun")
        answer_types = {types[word] for word in data["answers"]}
        self.assertGreaterEqual(len(answer_types), 4)

    def test_completed_text_restores_natural_patterns(self):
        data = validate_word_gap(EN_GAMMEL_DROEM, rank="C")
        text = completed_text(data)
        self.assertIn("fordi hun har arbejdet", text)
        self.assertIn("har også været", text)
        self.assertIn("har travlt med at", text)
        self.assertIn("sin egen butik", text)

    def test_word_type_rules_cover_exam_patterns(self):
        self.assertIn("for + main-clause word order versus fordi", WORD_TYPE_RULES)
        self.assertIn("han/ham", WORD_TYPE_RULES)
        self.assertIn("sin/sit/sine", WORD_TYPE_RULES)
        self.assertIn("som/hvor/der/hvad", WORD_TYPE_RULES)
        self.assertIn("ikke/også", WORD_TYPE_RULES)

    def test_rank_order_and_source_reserve(self):
        self.assertEqual(RANK_ORDER, ("F", "E", "D", "C", "B", "A", "S"))
        self.assertIsNotNone(
            reserve_opgave1("Arbejde og butik", rank="C", recent_titles=())
        )
        self.assertIsNone(
            reserve_opgave1(
                "Arbejde og butik",
                rank="C",
                recent_titles=("En gammel drøm",),
            )
        )

    def test_keyboard_removes_used_words(self):
        data = validate_word_gap(EN_GAMMEL_DROEM, rank="C")
        item = {"id": 42, "data": data, "answers": ["fordi"], "mode": "exam", "completed": False}
        markup = answer_keyboard(item)
        labels = [button.text for row in markup.inline_keyboard for button in row]
        self.assertNotIn("fordi", labels)
        self.assertIn("også", labels)
        callbacks = [
            button.callback_data
            for row in markup.inline_keyboard
            for button in row
            if button.callback_data
        ]
        self.assertIn("opg1:answer:42:1:også", callbacks)


class Opgave1PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.url = "sqlite:///" + str(Path(self.temp.name) / "study.db")
        self.memory = StudyMemory(StudyDatabase(self.url))
        self.patch = patch("opgave1_support.get_study_memory", lambda: self.memory)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.memory.database.dispose()
        self.temp.cleanup()

    def test_exam_accepts_six_sequential_unique_words(self):
        item = db_action(
            "one",
            "create",
            data=validate_word_gap(EN_GAMMEL_DROEM, rank="C"),
            mode="exam",
        )
        current = item
        for index, answer in enumerate(["fordi", "også", "men", "ikke", "har", "butik"]):
            current = db_action(
                "one",
                "answer",
                id=item["id"],
                index=index,
                answer=answer,
            )
        self.assertTrue(current["completed"])
        self.assertEqual(current["score"], 100)
        with self.memory.database.session() as session:
            self.assertEqual(
                session.scalar(select(func.count()).select_from(WordGapSession)),
                1,
            )

    def test_same_word_cannot_be_used_twice(self):
        item = db_action(
            "one",
            "create",
            data=validate_word_gap(EN_GAMMEL_DROEM, rank="C"),
            mode="practice",
        )
        db_action("one", "answer", id=item["id"], index=0, answer="fordi")
        with self.assertRaises(ValueError):
            db_action("one", "answer", id=item["id"], index=1, answer="fordi")


class Opgave1GenerationTests(unittest.IsolatedAsyncioTestCase):
    async def test_high_rank_prompt_requires_close_distractors(self):
        raw = validate_word_gap(EN_GAMMEL_DROEM, rank="S")
        review = {
            "valid": True,
            "answers": ["fordi", "også", "men", "ikke", "har", "butik"],
            "candidates": [["fordi"], ["også"], ["men"], ["ikke"], ["har"], ["butik"]],
            "reason": "",
        }
        calls = AsyncMock(side_effect=[raw, review, {"valid": True, "reason": ""}])
        with patch("opgave1_generator._json_call", calls):
            result = await prepare_word_gap("arbejde", rank="S")
        self.assertEqual(result["rank"], "S")
        prompt = calls.call_args_list[0].args[1]
        self.assertIn("same grammatical", prompt)
        self.assertIn("one-use-only", prompt)
        self.assertIn("grammar/reference words must dominate", prompt)
        self.assertIn("for + main-clause word order versus fordi", prompt)


if __name__ == "__main__":
    unittest.main()

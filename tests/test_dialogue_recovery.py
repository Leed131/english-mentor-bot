import json
import re
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from dialogue_examples import EXAMPLES, reserve_dialogue
from dialogue_generator import prepare_dialogue, review_payload
from dialogue_support import generate, menu, TOPICS
from test_dialogues import example


def approval():
    return {"valid": True, "answers": ["D", "A", "B"], "candidates": [["D"], ["A"], ["B"]]}


class RecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejection_is_repaired_with_specific_feedback(self):
        reason = "Gap 2: A and E both fit the next line; make the time explicit."
        calls = AsyncMock(side_effect=[example(), {"valid":False,"reason":reason},
                                      example(), approval(), {"valid":True}])
        with patch("dialogue_generator._json_call", calls):
            result = await prepare_dialogue("Indkøb")
        repair = json.loads(calls.call_args_list[2].args[1][calls.call_args_list[2].args[1].index("{"): ])
        self.assertIn(reason, repair["rejection_feedback"])
        self.assertEqual(repair["previous_candidate"], example())
        self.assertEqual(result["answers"], ["D", "A", "B"])

    async def test_valid_flag_does_not_override_ambiguous_candidates(self):
        bad = approval()
        bad["candidates"][0] = ["D", "F"]
        with patch("dialogue_generator._json_call", AsyncMock(side_effect=[example(), bad]*3)):
            with self.assertRaises(ValueError):
                await prepare_dialogue("Indkøb")

    async def test_generation_failure_serves_labelled_reserve(self):
        update = object()
        async def database(user, action, **kwargs):
            if action == "recent":
                return []
            self.assertEqual(action, "create")
            self.assertEqual(kwargs["data"]["topic"], TOPICS[0])
            return {"id":1}
        with patch("dialogue_support.prepare_dialogue", AsyncMock(side_effect=ValueError("ambiguous"))), patch("dialogue_support.db", database), patch("dialogue_support.send", AsyncMock()) as send, patch("dialogue_support.show", AsyncMock()) as show:
            await generate(update, "one", TOPICS[0], "exam")
        self.assertTrue(any("gennemgået" in c.args[1] for c in send.call_args_list))
        show.assert_awaited_once_with(update, {"id":1})

    async def test_database_failure_does_not_trigger_another_exercise(self):
        database = AsyncMock(side_effect=[[], RuntimeError("offline")])
        with patch("dialogue_support.prepare_dialogue", AsyncMock(return_value=example())), patch("dialogue_support.db", database), patch("dialogue_support.send", AsyncMock()) as send, patch("dialogue_support.show", AsyncMock()) as show, patch("dialogue_examples.reserve_dialogue") as reserve:
            await generate(object(), "one", TOPICS[0], "exam")
        reserve.assert_not_called()
        show.assert_not_called()
        self.assertIn("gemmes", send.call_args.args[1])


class ContextTests(unittest.TestCase):
    def test_solver_sees_actual_turn_order_and_both_neighbours(self):
        raw = example()
        payload = review_payload(raw)
        self.assertEqual(len(payload["dialogue"]), 9)
        self.assertEqual([t["speaker"] for t in payload["dialogue"]], ["Anna","Bo","Anna","Bo","Anna","Bo","Anna","Bo","Anna"])
        for i, gap in enumerate(payload["gaps"]):
            self.assertEqual(gap["before"]["text"], raw["lines"][i+2])
            self.assertEqual(gap["after"]["text"], raw["lines"][i+3])
            self.assertEqual(payload["dialogue"][3+2*i]["text"], f"[GAP {i+1}]")
        self.assertNotIn("answers", payload)
        self.assertNotIn("explanations", payload)
        completed = review_payload(raw, filled=True)
        for i, key in enumerate(raw["answers"]):
            self.assertEqual(completed["dialogue"][3+2*i]["text"], raw["options"][key])

    def test_reserve_keys_survive_shuffling_and_recent_filter(self):
        for raw in EXAMPLES:
            for _ in range(5):
                data = reserve_dialogue(raw["topic"])
                self.assertEqual([data["options"][a] for a in data["answers"]], raw["replies"])
            self.assertEqual(reserve_dialogue(raw["topic"], [raw["situation"]])["situation"], raw["situation"])
        self.assertIsNone(reserve_dialogue("an unrelated custom topic"))

    def test_all_static_menus_are_danish_and_callbacks_unchanged(self):
        import telegram_bot
        from topic_quiz_support import _continuation_markup
        from progress import SECTION_LABELS
        texts = list(TOPICS) + list(SECTION_LABELS.values())
        for markup in [menu(), telegram_bot._main_menu(), telegram_bot._verb_menu(), _continuation_markup(1)]:
            texts.extend(b.text for row in markup.inline_keyboard for b in row)
        self.assertFalse(re.search('[А-Яа-я]', ' '.join(texts)))
        callbacks = [b.callback_data for row in menu().inline_keyboard for b in row]
        self.assertIn('dialog:topics:exam', callbacks)

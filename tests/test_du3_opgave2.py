import unittest

from du3_opgave2_support import (
    TOPICS,
    _feedback_prompt,
    _individual_turn_text,
    _new_session,
    _pair_turn_text,
)


class Du3Opgave2Tests(unittest.TestCase):
    def test_all_topics_have_four_fixed_situations_and_questions(self):
        self.assertEqual(
            set(TOPICS),
            {"dansk", "venner", "bolig", "gron", "sund"},
        )
        for topic in TOPICS.values():
            self.assertEqual(len(topic.situations), 4)
            self.assertEqual(len(topic.situation_questions), 4)
            self.assertGreaterEqual(len(topic.individual_questions), 3)
            self.assertLessEqual(len(topic.individual_questions), 5)

    def test_new_session_starts_with_first_tester_question(self):
        session = _new_session("bolig")
        self.assertEqual(session["phase"], "pair")
        self.assertEqual(session["situation_index"], 0)
        self.assertEqual(session["question_index"], 0)
        self.assertNotIn("turn", session)

    def test_pair_turn_has_clear_roles(self):
        topic = TOPICS["venner"]
        text = _pair_turn_text(topic, 0)

        self.assertIn("Situation 1/4", text)
        self.assertIn(topic.situations[0], text)
        self.assertIn("🤖 Spørgsmål:", text)
        self.assertIn(topic.situation_questions[0], text)
        self.assertIn("🎙️ Din tur:", text)

    def test_individual_turn_has_one_fixed_question(self):
        topic = TOPICS["sund"]
        text = _individual_turn_text(topic, 1)

        self.assertIn("Del 2", text)
        self.assertIn("spørgsmål 2/4", text)
        self.assertIn(topic.individual_questions[1], text)
        self.assertIn("🎙️ Din tur:", text)

    def test_feedback_prompt_forbids_new_questions(self):
        prompt = _feedback_prompt(
            "Hvor ofte dyrker du motion?",
            "Jeg cykler fem dage om ugen.",
        )

        self.assertIn("Evaluate only this answer", prompt)
        self.assertIn("Do not answer the question yourself", prompt)
        self.assertIn("do not ask any new question", prompt)


if __name__ == "__main__":
    unittest.main()

import unittest

from du3_opgave2_support import (
    TOPICS,
    _individual_prompt,
    _is_likely_question,
    _new_session,
    _pair_answer_prompt,
)


class Du3Opgave2Tests(unittest.TestCase):
    def test_all_topics_have_four_situations_and_individual_questions(self):
        self.assertEqual(
            set(TOPICS),
            {"dansk", "venner", "bolig", "gron", "sund"},
        )
        for topic in TOPICS.values():
            self.assertEqual(len(topic.situations), 4)
            self.assertGreaterEqual(len(topic.individual_questions), 3)
            self.assertLessEqual(len(topic.individual_questions), 5)

    def test_new_session_starts_with_learner_question(self):
        session = _new_session("bolig")
        self.assertEqual(session["phase"], "pair")
        self.assertEqual(session["situation_index"], 0)
        self.assertEqual(session["turn"], "learner_question")

    def test_question_detection_works_without_question_mark(self):
        self.assertTrue(_is_likely_question("Hvor vil du helst bo"))
        self.assertTrue(_is_likely_question("Kan du lide at cykle"))
        self.assertFalse(_is_likely_question("Jeg vil helst bo i byen"))

    def test_last_pair_answer_transitions_to_del_2(self):
        topic = TOPICS["gron"]
        session = _new_session("gron")
        session["situation_index"] = 3
        session["turn"] = "learner_answer"

        prompt, starts_individual = _pair_answer_prompt(
            topic,
            session,
            "Jeg prøver at undgå madspild.",
        )

        self.assertTrue(starts_individual)
        self.assertIn("Del 2", prompt)
        self.assertIn(topic.individual_questions[0], prompt)

    def test_last_individual_question_finishes_exercise(self):
        topic = TOPICS["sund"]
        session = _new_session("sund")
        session["phase"] = "individual"
        session["question_index"] = len(topic.individual_questions) - 1

        prompt, is_last = _individual_prompt(
            topic,
            session,
            "Jeg vil gerne dyrke mere motion.",
        )

        self.assertTrue(is_last)
        self.assertIn("Opgave 2 er færdig", prompt)


if __name__ == "__main__":
    unittest.main()

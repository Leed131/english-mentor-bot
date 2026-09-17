import unittest

from quiz_generator import _validate_questions
from topic_quiz_support import _continuation_markup, _quiz_text
from study_memory import QuizSnapshot


class TopicQuizTests(unittest.TestCase):
    def test_validates_generated_questions(self):
        questions = _validate_questions(
            {
                "questions": [
                    {
                        "question": "Vælg den korrekte sætning.",
                        "options": ["Jeg ikke kommer.", "Jeg kommer ikke.", "Ikke jeg kommer."],
                        "correct_index": 1,
                        "explanation": "I en hovedsætning står ikke efter verbet.",
                    },
                    {
                        "question": "Hvad er korrekt?",
                        "options": ["I dag jeg arbejder.", "I dag arbejder jeg.", "I dag jeg arbejde."],
                        "correct_index": 1,
                        "explanation": "Efter et forfelt kommer verbet før subjektet.",
                    },
                    {
                        "question": "Vælg spørgsmålet.",
                        "options": ["Du kommer?", "Kommer du?", "Du kommer ikke?"],
                        "correct_index": 1,
                        "explanation": "I spørgsmål står verbet før subjektet.",
                    },
                ]
            },
            "ordstilling",
            5,
        )
        self.assertEqual(len(questions), 3)
        self.assertEqual(questions[0]["topic"], "ordstilling")
        self.assertIn("Jeg kommer ikke.", questions[0]["explanation"])

    def test_continuation_markup_offers_another_five(self):
        markup = _continuation_markup(42)
        buttons = [button for row in markup.inline_keyboard for button in row]
        labels = {button.text for button in buttons}
        callbacks = {button.callback_data for button in buttons}

        self.assertIn("➡️ Fem nye om emnet", labels)
        self.assertIn("topicquiz:more:42", callbacks)

    def test_quiz_text_has_position_without_percent(self):
        quiz = QuizSnapshot(
            id=1,
            kind="grammar",
            topic="ordstilling",
            question_index=0,
            question_count=5,
            question="Vælg den korrekte sætning.",
            options=("A", "B", "C"),
            correct_answers=0,
            wrong_answers=0,
        )
        text = _quiz_text(quiz, "🧩 Øvelser")
        self.assertIn("Spørgsmål 1/5", text)
        self.assertNotIn("%", text)


if __name__ == "__main__":
    unittest.main()

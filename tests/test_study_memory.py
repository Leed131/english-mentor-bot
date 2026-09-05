import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import inspect

from database import StudyDatabase, normalize_database_url
from progress import (
    calculate_overall_progress,
    calculate_section_progress,
    progress_bar,
)
from study_memory import StudyMemory
from verbs import calculate_next_review


class StudyMemoryTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_directory.name, "study.db").as_posix()
        self.database_url = f"sqlite:///{database_path}"
        self.database = StudyDatabase(self.database_url)
        self.memory = StudyMemory(self.database)

    def tearDown(self):
        self.database.dispose()
        self.temp_directory.cleanup()


class PersistenceTests(StudyMemoryTestCase):
    def test_schema_is_initialized_non_destructively(self):
        expected_tables = {
            "learner_profiles",
            "section_progress",
            "grammar_topics",
            "learner_errors",
            "verb_progress",
            "verb_review_attempts",
            "vocabulary_items",
            "exercise_results",
            "quiz_sessions",
        }
        self.database.initialize()
        self.assertTrue(
            expected_tables.issubset(inspect(self.database.engine).get_table_names())
        )

    def test_progress_survives_database_reopen(self):
        self.memory.record_activity(
            "telegram",
            "42",
            "audio",
            "introductions",
            score=80,
            correct_answers=4,
            wrong_answers=1,
        )
        self.database.dispose()

        reopened_database = StudyDatabase(self.database_url)
        reopened_memory = StudyMemory(reopened_database)
        try:
            profile = reopened_memory.get_or_create_profile("telegram", "42")
            sections = reopened_memory.get_sections("telegram", "42")
        finally:
            reopened_database.dispose()

        self.assertEqual(profile.current_topic, "introductions")
        self.assertEqual(sections["audio"].completed_tasks, 1)
        self.assertEqual(sections["audio"].correct_answers, 4)
        self.assertEqual(sections["audio"].wrong_answers, 1)
        self.assertEqual(sections["audio"].percentage, 10)

    def test_users_and_platforms_do_not_share_progress(self):
        self.memory.record_activity("telegram", "42", "tests", "A1 test", score=80)

        telegram_other = self.memory.get_sections("telegram", "99")
        discord_same_id = self.memory.get_sections("discord", "42", language="en")

        self.assertEqual(telegram_other["tests"].completed_tasks, 0)
        self.assertEqual(discord_same_id["tests"].completed_tasks, 0)

    def test_reset_removes_only_selected_profile(self):
        self.memory.record_activity("telegram", "42", "tests", "A1 test", score=80)
        self.memory.record_activity("telegram", "99", "tests", "A1 test", score=100)

        self.memory.reset_progress("telegram", "42")

        self.assertEqual(
            self.memory.get_sections("telegram", "42")["tests"].completed_tasks,
            0,
        )
        self.assertEqual(
            self.memory.get_sections("telegram", "99")["tests"].completed_tasks,
            1,
        )

    def test_writing_result_and_structured_error_are_persisted(self):
        self.memory.save_writing_evaluation(
            "telegram",
            "42",
            "min dag",
            75,
            [
                {
                    "error_type": "word_order",
                    "example": "Jeg ikke arbejder.",
                    "correction": "Jeg arbejder ikke.",
                }
            ],
            [],
        )

        sections = self.memory.get_sections("telegram", "42")
        history = self.memory.get_history("telegram", "42")
        self.assertEqual(sections["writing"].completed_tasks, 1)
        self.assertEqual(sections["writing"].last_score, 75)
        self.assertIn("word_order", history["errors"])
        self.assertIn("min dag", history["completed"])


class QuizTests(StudyMemoryTestCase):
    def test_quiz_is_resumable_and_duplicate_callback_is_idempotent(self):
        quiz = self.memory.start_quiz("telegram", "42", "test")
        resumed = self.memory.get_active_quiz("telegram", "42")
        self.assertEqual(resumed, quiz)

        first_correct_index = quiz.options.index("lærer")
        result = self.memory.answer_quiz(
            "telegram",
            "42",
            quiz.id,
            quiz.question_index,
            first_correct_index,
        )
        duplicate = self.memory.answer_quiz(
            "telegram",
            "42",
            quiz.id,
            quiz.question_index,
            first_correct_index,
        )

        self.assertEqual(result.state, "next")
        self.assertEqual(duplicate.state, "duplicate")
        self.assertEqual(
            self.memory.get_sections("telegram", "42")["tests"].completed_tasks, 0
        )

        current = result.next_question
        while current is not None:
            correct_values = ("var", "Jeg har ikke tid.", "tog", "spist")
            selected = next(
                index
                for index, option in enumerate(current.options)
                if option in correct_values
            )
            result = self.memory.answer_quiz(
                "telegram",
                "42",
                current.id,
                current.question_index,
                selected,
            )
            current = result.next_question

        self.assertEqual(result.state, "complete")
        self.assertEqual(result.score, 100)
        sections = self.memory.get_sections("telegram", "42")
        self.assertEqual(sections["tests"].completed_tasks, 1)
        self.assertEqual(sections["tests"].correct_answers, 5)
        self.assertEqual(
            self.memory.get_test_stats("telegram", "42"),
            {"count": 1, "latest": 100, "best": 100, "average": 100},
        )

    def test_wrong_grammar_answer_is_saved_for_review(self):
        quiz = self.memory.start_quiz("telegram", "42", "grammar")
        result = self.memory.answer_quiz(
            "telegram",
            "42",
            quiz.id,
            quiz.question_index,
            0,
        )
        history = self.memory.get_history("telegram", "42")

        self.assertEqual(result.state, "complete")
        self.assertIn("word order with ikke", history["review"])
        self.assertIn("word_order", history["errors"])


class VerbReviewTests(StudyMemoryTestCase):
    def test_five_successful_reviews_master_a_verb(self):
        learned = self.memory.learn_next_verb("telegram", "42")
        self.assertIsNotNone(learned)
        review_time = datetime.now(timezone.utc) + timedelta(minutes=1)
        result = None

        for _ in range(5):
            review = self.memory.create_verb_review(
                "telegram",
                "42",
                now=review_time,
            )
            self.assertIsNotNone(review)
            selected = review.options.index(learned.past)
            result = self.memory.submit_verb_review(
                "telegram",
                "42",
                review.id,
                selected,
                now=review_time,
            )
            self.assertFalse(result.already_answered)
            review_time = result.verb.next_review + timedelta(minutes=1)

        self.assertEqual(result.verb.status, "mastered")
        self.assertEqual(result.verb.successful_reviews, 5)
        self.assertEqual(
            self.memory.get_sections("telegram", "42")["verbs"].completed_tasks,
            5,
        )

    def test_repeated_verb_callback_does_not_increment_twice(self):
        learned = self.memory.learn_next_verb("telegram", "42")
        review = self.memory.create_verb_review(
            "telegram",
            "42",
            now=datetime.now(timezone.utc) + timedelta(minutes=1),
        )
        selected = review.options.index(learned.past)

        first = self.memory.submit_verb_review("telegram", "42", review.id, selected)
        duplicate = self.memory.submit_verb_review(
            "telegram",
            "42",
            review.id,
            selected,
        )

        self.assertTrue(first.was_correct)
        self.assertTrue(duplicate.already_answered)
        self.assertEqual(
            self.memory.get_sections("telegram", "42")["verbs"].completed_tasks,
            1,
        )


class ProgressCalculationTests(unittest.TestCase):
    def test_progress_is_weighted_plan_progress(self):
        sections = {
            "audio": 60,
            "tests": 70,
            "grammar": 80,
            "writing": 50,
            "verbs": 70,
        }
        self.assertEqual(calculate_overall_progress(sections), 66)
        self.assertEqual(calculate_section_progress(6, 10), 60)
        self.assertEqual(progress_bar(60), "██████░░░░")

    def test_review_interval_changes_after_correct_and_wrong_answers(self):
        now = datetime(2026, 9, 5, tzinfo=timezone.utc)
        first = calculate_next_review(0, True, now)
        second = calculate_next_review(first.successful_reviews, True, now)
        wrong = calculate_next_review(second.successful_reviews, False, now)

        self.assertEqual(first.next_review, now + timedelta(days=1))
        self.assertEqual(second.next_review, now + timedelta(days=3))
        self.assertEqual(wrong.status, "review")
        self.assertEqual(wrong.successful_reviews, 1)
        self.assertEqual(wrong.next_review, now + timedelta(days=1))

    def test_render_postgres_url_uses_psycopg_driver(self):
        self.assertEqual(
            normalize_database_url("postgres://user:password@example/db"),
            "postgresql+psycopg://user:password@example/db",
        )

        database = StudyDatabase("postgresql://user:password@localhost/db")
        try:
            self.assertEqual(database.engine.dialect.name, "postgresql")
            self.assertEqual(database.engine.dialect.driver, "psycopg")
        finally:
            database.dispose()


if __name__ == "__main__":
    unittest.main()

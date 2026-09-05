import json
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Final

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database import (
    ExerciseResult,
    GrammarTopic,
    LearnerError,
    LearnerProfile,
    QuizSession,
    SectionProgress,
    StudyDatabase,
    VerbProgress,
    VerbReviewAttempt,
    VocabularyItem,
    normalize_database_url,
    utc_now,
)
from progress import (
    DEFAULT_SECTION_TOTALS,
    SECTION_LABELS,
    STUDY_SECTIONS,
    calculate_section_progress,
)
from verbs import DEFAULT_DANISH_VERBS, calculate_next_review

TEST_QUESTIONS: Final[list[dict[str, Any]]] = [
    {
        "question": "Vælg det rigtige ord: Jeg ___ dansk hver dag.",
        "options": ["lærer", "lærte", "lært"],
        "correct_index": 0,
        "explanation": "Nutid bruges om en vane: Jeg lærer dansk hver dag.",
        "topic": "present tense",
    },
    {
        "question": "Vælg det rigtige ord: I går ___ jeg hjemme.",
        "options": ["er", "var", "været"],
        "correct_index": 1,
        "explanation": "I går kræver datid: Jeg var hjemme.",
        "topic": "past tense",
    },
    {
        "question": "Vælg den korrekte ordstilling.",
        "options": ["Jeg ikke har tid.", "Jeg har ikke tid.", "Ikke jeg har tid."],
        "correct_index": 1,
        "explanation": "I en hovedsætning står ikke normalt efter det bøjede verbum.",
        "topic": "word order",
    },
    {
        "question": "Vælg det rigtige ord: Vi ___ toget i går.",
        "options": ["tager", "tog", "taget"],
        "correct_index": 1,
        "explanation": "Datid af at tage er tog.",
        "topic": "irregular verbs",
    },
    {
        "question": "Vælg det rigtige ord: De har ___ maden.",
        "options": ["spise", "spiste", "spist"],
        "correct_index": 2,
        "explanation": "Efter har bruges perfektum participium: spist.",
        "topic": "perfect tense",
    },
]

GRAMMAR_QUESTIONS: Final[list[dict[str, Any]]] = [
    {
        "question": "Vælg den korrekte sætning.",
        "options": [
            "Jeg ikke taler dansk hver dag.",
            "Jeg taler ikke dansk hver dag.",
            "Ikke jeg taler dansk hver dag.",
        ],
        "correct_index": 1,
        "explanation": "I en dansk hovedsætning står ikke efter det bøjede verbum.",
        "topic": "word order with ikke",
        "error_type": "word_order",
        "error_example": "Jeg ikke taler dansk.",
        "error_correction": "Jeg taler ikke dansk.",
    }
]


@dataclass(frozen=True)
class ProfileSnapshot:
    id: int
    platform: str
    user_id: str
    language: str
    current_level: str
    current_section: str | None
    current_topic: str | None
    last_activity: datetime
    next_step: str | None


@dataclass(frozen=True)
class SectionSnapshot:
    section: str
    completed_tasks: int
    total_tasks: int
    correct_answers: int
    wrong_answers: int
    last_topic: str | None
    last_score: float | None
    percentage: int


@dataclass(frozen=True)
class QuizSnapshot:
    id: int
    kind: str
    topic: str
    question_index: int
    question_count: int
    question: str
    options: tuple[str, ...]
    correct_answers: int
    wrong_answers: int


@dataclass(frozen=True)
class QuizAnswer:
    state: str
    was_correct: bool | None
    explanation: str | None
    next_question: QuizSnapshot | None
    score: int | None
    correct_answers: int
    wrong_answers: int


@dataclass(frozen=True)
class VerbSnapshot:
    id: int
    infinitive: str
    present: str
    past: str
    past_participle: str
    translation_ru: str
    status: str
    correct_count: int
    wrong_count: int
    successful_reviews: int
    next_review: datetime | None


@dataclass(frozen=True)
class VerbReviewSnapshot:
    id: int
    verb_id: int
    question: str
    options: tuple[str, ...]


@dataclass(frozen=True)
class VerbReviewResult:
    found: bool
    already_answered: bool
    was_correct: bool | None
    correct_answer: str | None
    verb: VerbSnapshot | None


def _profile_snapshot(profile: LearnerProfile) -> ProfileSnapshot:
    return ProfileSnapshot(
        id=profile.id,
        platform=profile.platform,
        user_id=profile.user_id,
        language=profile.language,
        current_level=profile.current_level,
        current_section=profile.current_section,
        current_topic=profile.current_topic,
        last_activity=profile.last_activity,
        next_step=profile.next_step,
    )


def _verb_snapshot(verb: VerbProgress) -> VerbSnapshot:
    return VerbSnapshot(
        id=verb.id,
        infinitive=verb.infinitive,
        present=verb.present,
        past=verb.past,
        past_participle=verb.past_participle,
        translation_ru=verb.translation_ru,
        status=verb.status,
        correct_count=verb.correct_count,
        wrong_count=verb.wrong_count,
        successful_reviews=verb.successful_reviews,
        next_review=verb.next_review,
    )


class StudyMemory:
    def __init__(self, database: StudyDatabase | None = None) -> None:
        self.database = database or StudyDatabase()
        self.database.initialize()

    def _profile(
        self,
        session: Session,
        platform: str,
        user_id: str | int,
        language: str = "da",
    ) -> LearnerProfile:
        normalized_user_id = str(user_id)
        profile = session.scalar(
            select(LearnerProfile).where(
                LearnerProfile.platform == platform,
                LearnerProfile.user_id == normalized_user_id,
                LearnerProfile.language == language,
            )
        )
        if profile is None:
            profile = LearnerProfile(
                platform=platform,
                user_id=normalized_user_id,
                language=language,
                current_level="A1",
                next_step="Åbn /learn og vælg den første øvelse",
            )
            session.add(profile)
            session.flush()

        existing_sections = {
            row.section
            for row in session.scalars(
                select(SectionProgress).where(SectionProgress.profile_id == profile.id)
            )
        }
        for section in STUDY_SECTIONS:
            if section not in existing_sections:
                session.add(
                    SectionProgress(
                        profile_id=profile.id,
                        section=section,
                        total_tasks=DEFAULT_SECTION_TOTALS[section],
                    )
                )
        return profile

    def get_or_create_profile(
        self,
        platform: str,
        user_id: str | int,
        language: str = "da",
    ) -> ProfileSnapshot:
        with self.database.session() as session:
            return _profile_snapshot(
                self._profile(session, platform, user_id, language)
            )

    def set_current_step(
        self,
        platform: str,
        user_id: str | int,
        section: str,
        topic: str,
        next_step: str,
        language: str = "da",
    ) -> ProfileSnapshot:
        with self.database.session() as session:
            profile = self._profile(session, platform, user_id, language)
            profile.current_section = section
            profile.current_topic = topic
            profile.next_step = next_step
            profile.last_activity = utc_now()
            profile.updated_at = utc_now()
            session.flush()
            return _profile_snapshot(profile)

    def get_sections(
        self,
        platform: str,
        user_id: str | int,
        language: str = "da",
    ) -> dict[str, SectionSnapshot]:
        with self.database.session() as session:
            profile = self._profile(session, platform, user_id, language)
            rows = session.scalars(
                select(SectionProgress).where(SectionProgress.profile_id == profile.id)
            ).all()
            return {
                row.section: SectionSnapshot(
                    section=row.section,
                    completed_tasks=row.completed_tasks,
                    total_tasks=row.total_tasks,
                    correct_answers=row.correct_answers,
                    wrong_answers=row.wrong_answers,
                    last_topic=row.last_topic,
                    last_score=row.last_score,
                    percentage=calculate_section_progress(
                        row.completed_tasks,
                        row.total_tasks,
                    ),
                )
                for row in rows
            }

    def _record_activity(
        self,
        session: Session,
        profile: LearnerProfile,
        section: str,
        topic: str,
        score: float | None,
        correct_answers: int,
        wrong_answers: int,
        details: dict[str, Any] | None,
        next_step: str,
    ) -> None:
        progress = session.scalar(
            select(SectionProgress).where(
                SectionProgress.profile_id == profile.id,
                SectionProgress.section == section,
            )
        )
        if progress is None:
            progress = SectionProgress(
                profile_id=profile.id,
                section=section,
                total_tasks=DEFAULT_SECTION_TOTALS.get(section, 10),
            )
            session.add(progress)

        progress.completed_tasks += 1
        progress.correct_answers += max(correct_answers, 0)
        progress.wrong_answers += max(wrong_answers, 0)
        progress.last_topic = topic
        progress.last_score = score
        progress.updated_at = utc_now()

        session.add(
            ExerciseResult(
                profile_id=profile.id,
                section=section,
                topic=topic,
                score=score,
                correct_answers=max(correct_answers, 0),
                wrong_answers=max(wrong_answers, 0),
                details_json=(
                    json.dumps(details, ensure_ascii=False)
                    if details is not None
                    else None
                ),
            )
        )

        profile.current_section = section
        profile.current_topic = topic
        profile.next_step = next_step
        profile.last_activity = utc_now()
        profile.updated_at = utc_now()

    def record_activity(
        self,
        platform: str,
        user_id: str | int,
        section: str,
        topic: str,
        *,
        score: float | None = None,
        correct_answers: int = 0,
        wrong_answers: int = 0,
        details: dict[str, Any] | None = None,
        next_step: str = "Vælg den næste øvelse i /learn",
        language: str = "da",
    ) -> None:
        with self.database.session() as session:
            profile = self._profile(session, platform, user_id, language)
            self._record_activity(
                session,
                profile,
                section,
                topic,
                score,
                correct_answers,
                wrong_answers,
                details,
                next_step,
            )

    def _record_error(
        self,
        session: Session,
        profile: LearnerProfile,
        error_type: str,
        example: str,
        correction: str,
    ) -> None:
        row = session.scalar(
            select(LearnerError).where(
                LearnerError.profile_id == profile.id,
                LearnerError.error_type == error_type[:80],
                LearnerError.example == example,
            )
        )
        if row is None:
            row = LearnerError(
                profile_id=profile.id,
                error_type=error_type[:80],
                example=example,
                correction=correction,
                count=1,
                status="review",
                next_review=utc_now() + timedelta(days=1),
            )
            session.add(row)
        else:
            row.count += 1
            row.correction = correction
            row.last_seen = utc_now()
            row.status = "review"
            row.next_review = utc_now() + timedelta(days=1)

    def save_writing_evaluation(
        self,
        platform: str,
        user_id: str | int,
        topic: str,
        score: int,
        grammar_errors: list[dict[str, str]],
        vocabulary_errors: list[dict[str, str]],
        language: str = "da",
    ) -> None:
        with self.database.session() as session:
            profile = self._profile(session, platform, user_id, language)
            all_errors = [*grammar_errors, *vocabulary_errors]
            for error in all_errors:
                example = str(error.get("example", "")).strip()
                correction = str(error.get("correction", "")).strip()
                if not example or not correction:
                    continue
                self._record_error(
                    session,
                    profile,
                    str(error.get("error_type", "other")),
                    example,
                    correction,
                )

            error_count = len(all_errors)
            self._record_activity(
                session,
                profile,
                "writing",
                topic,
                max(0, min(100, score)),
                1 if error_count == 0 else 0,
                error_count,
                {
                    "grammar_errors": len(grammar_errors),
                    "vocabulary_errors": len(vocabulary_errors),
                },
                "Ret teksten og prøv en ny skriveøvelse",
            )

    def _quiz_snapshot(self, quiz: QuizSession) -> QuizSnapshot | None:
        questions = json.loads(quiz.questions_json)
        if quiz.completed or quiz.current_index >= len(questions):
            return None
        current = questions[quiz.current_index]
        return QuizSnapshot(
            id=quiz.id,
            kind=quiz.kind,
            topic=quiz.topic,
            question_index=quiz.current_index,
            question_count=len(questions),
            question=str(current["question"]),
            options=tuple(str(option) for option in current["options"]),
            correct_answers=quiz.correct_answers,
            wrong_answers=quiz.wrong_answers,
        )

    def start_quiz(
        self,
        platform: str,
        user_id: str | int,
        kind: str,
        language: str = "da",
    ) -> QuizSnapshot:
        if kind == "test":
            topic = "A1 mixed test"
            questions = TEST_QUESTIONS
            section = "tests"
        elif kind == "grammar":
            topic = "word order with ikke"
            questions = GRAMMAR_QUESTIONS
            section = "grammar"
        else:
            raise ValueError(f"Unsupported quiz kind: {kind}")

        with self.database.session() as session:
            profile = self._profile(session, platform, user_id, language)
            unfinished = session.scalars(
                select(QuizSession).where(
                    QuizSession.profile_id == profile.id,
                    QuizSession.kind == kind,
                    QuizSession.completed.is_(False),
                )
            ).all()
            for old_quiz in unfinished:
                old_quiz.completed = True

            quiz = QuizSession(
                profile_id=profile.id,
                kind=kind,
                topic=topic,
                questions_json=json.dumps(questions, ensure_ascii=False),
            )
            session.add(quiz)
            session.flush()
            profile.current_section = section
            profile.current_topic = topic
            profile.next_step = f"Svar på spørgsmål 1 af {len(questions)}"
            profile.last_activity = utc_now()
            snapshot = self._quiz_snapshot(quiz)
            if snapshot is None:
                raise RuntimeError("Quiz has no questions")
            return snapshot

    def get_active_quiz(
        self,
        platform: str,
        user_id: str | int,
        language: str = "da",
    ) -> QuizSnapshot | None:
        with self.database.session() as session:
            profile = self._profile(session, platform, user_id, language)
            quiz = session.scalar(
                select(QuizSession)
                .where(
                    QuizSession.profile_id == profile.id,
                    QuizSession.completed.is_(False),
                )
                .order_by(QuizSession.created_at.desc(), QuizSession.id.desc())
            )
            return self._quiz_snapshot(quiz) if quiz is not None else None

    def _update_grammar_topic(
        self,
        session: Session,
        profile: LearnerProfile,
        question: dict[str, Any],
        correct: bool,
    ) -> None:
        topic_name = str(question.get("topic", "grammar"))
        topic = session.scalar(
            select(GrammarTopic).where(
                GrammarTopic.profile_id == profile.id,
                GrammarTopic.topic == topic_name,
            )
        )
        if topic is None:
            topic = GrammarTopic(
                profile_id=profile.id,
                topic=topic_name,
                status="new",
                correct_count=0,
                wrong_count=0,
            )
            session.add(topic)

        topic.last_reviewed = utc_now()
        if correct:
            topic.correct_count += 1
            topic.status = "mastered" if topic.correct_count >= 5 else "learning"
            interval = (1, 3, 7, 14, 30)[min(topic.correct_count - 1, 4)]
            topic.next_review = utc_now() + timedelta(days=interval)
        else:
            topic.wrong_count += 1
            topic.status = "review"
            topic.next_review = utc_now() + timedelta(days=1)
            self._record_error(
                session,
                profile,
                str(question.get("error_type", "grammar")),
                str(question.get("error_example", question["question"])),
                str(question.get("error_correction", question["explanation"])),
            )

    def answer_quiz(
        self,
        platform: str,
        user_id: str | int,
        quiz_id: int,
        question_index: int,
        selected_index: int,
        language: str = "da",
    ) -> QuizAnswer:
        with self.database.session() as session:
            profile = self._profile(session, platform, user_id, language)
            quiz = session.scalar(
                select(QuizSession)
                .where(
                    QuizSession.id == quiz_id,
                    QuizSession.profile_id == profile.id,
                )
                .with_for_update()
            )
            if quiz is None:
                return QuizAnswer("missing", None, None, None, None, 0, 0)

            questions = json.loads(quiz.questions_json)
            if quiz.completed or question_index != quiz.current_index:
                total = quiz.correct_answers + quiz.wrong_answers
                score = round((quiz.correct_answers / total) * 100) if total else None
                return QuizAnswer(
                    "duplicate",
                    None,
                    None,
                    self._quiz_snapshot(quiz),
                    score,
                    quiz.correct_answers,
                    quiz.wrong_answers,
                )

            question = questions[quiz.current_index]
            options = question["options"]
            if selected_index < 0 or selected_index >= len(options):
                return QuizAnswer(
                    "invalid",
                    None,
                    None,
                    self._quiz_snapshot(quiz),
                    None,
                    quiz.correct_answers,
                    quiz.wrong_answers,
                )

            correct = selected_index == int(question["correct_index"])
            if correct:
                quiz.correct_answers += 1
            else:
                quiz.wrong_answers += 1

            if quiz.kind == "grammar":
                self._update_grammar_topic(session, profile, question, correct)

            quiz.current_index += 1
            explanation = str(question.get("explanation", ""))
            if quiz.current_index >= len(questions):
                quiz.completed = True
                quiz.completed_at = utc_now()
                total = quiz.correct_answers + quiz.wrong_answers
                score = round((quiz.correct_answers / total) * 100) if total else 0
                section = "tests" if quiz.kind == "test" else "grammar"
                self._record_activity(
                    session,
                    profile,
                    section,
                    quiz.topic,
                    score,
                    quiz.correct_answers,
                    quiz.wrong_answers,
                    {"quiz_id": quiz.id, "questions": len(questions)},
                    "Se resultatet og vælg næste øvelse i /learn",
                )
                return QuizAnswer(
                    "complete",
                    correct,
                    explanation,
                    None,
                    score,
                    quiz.correct_answers,
                    quiz.wrong_answers,
                )

            profile.next_step = (
                f"Svar på spørgsmål {quiz.current_index + 1} af {len(questions)}"
            )
            profile.last_activity = utc_now()
            return QuizAnswer(
                "next",
                correct,
                explanation,
                self._quiz_snapshot(quiz),
                None,
                quiz.correct_answers,
                quiz.wrong_answers,
            )

    def _ensure_verbs(self, session: Session, profile: LearnerProfile) -> None:
        existing = set(
            session.scalars(
                select(VerbProgress.infinitive).where(
                    VerbProgress.profile_id == profile.id
                )
            )
        )
        for verb in DEFAULT_DANISH_VERBS:
            if verb.infinitive not in existing:
                session.add(
                    VerbProgress(
                        profile_id=profile.id,
                        infinitive=verb.infinitive,
                        present=verb.present,
                        past=verb.past,
                        past_participle=verb.past_participle,
                        translation_ru=verb.translation_ru,
                    )
                )
        session.flush()

    def learn_next_verb(
        self,
        platform: str,
        user_id: str | int,
        language: str = "da",
    ) -> VerbSnapshot | None:
        with self.database.session() as session:
            profile = self._profile(session, platform, user_id, language)
            self._ensure_verbs(session, profile)
            verb = session.scalar(
                select(VerbProgress)
                .where(
                    VerbProgress.profile_id == profile.id,
                    VerbProgress.status == "new",
                )
                .order_by(VerbProgress.id)
            )
            if verb is None:
                return None
            verb.status = "learning"
            verb.next_review = utc_now()
            profile.current_section = "verbs"
            profile.current_topic = verb.infinitive
            profile.next_step = f"Øv formerne af {verb.infinitive}"
            profile.last_activity = utc_now()
            session.flush()
            return _verb_snapshot(verb)

    def create_verb_review(
        self,
        platform: str,
        user_id: str | int,
        language: str = "da",
        now: datetime | None = None,
    ) -> VerbReviewSnapshot | None:
        review_time = now or utc_now()
        with self.database.session() as session:
            profile = self._profile(session, platform, user_id, language)
            self._ensure_verbs(session, profile)
            verb = session.scalar(
                select(VerbProgress)
                .where(
                    VerbProgress.profile_id == profile.id,
                    VerbProgress.status != "new",
                    VerbProgress.next_review.is_not(None),
                    VerbProgress.next_review <= review_time,
                )
                .order_by(VerbProgress.next_review, VerbProgress.id)
            )
            if verb is None:
                return None

            other_forms = list(
                session.scalars(
                    select(VerbProgress.past)
                    .where(
                        VerbProgress.profile_id == profile.id,
                        VerbProgress.id != verb.id,
                    )
                    .order_by(VerbProgress.id)
                    .limit(4)
                )
            )
            distractors = [form for form in other_forms if form != verb.past][:2]
            options = [verb.past, *distractors]
            while len(options) < 3:
                options.append(f"{verb.present}{len(options)}")
            shift = (verb.id + verb.correct_count + verb.wrong_count) % len(options)
            options = options[shift:] + options[:shift]
            correct_index = options.index(verb.past)

            attempt = VerbReviewAttempt(
                verb_id=verb.id,
                question=f"Hvad er datid af '{verb.infinitive}'?",
                options_json=json.dumps(options, ensure_ascii=False),
                correct_index=correct_index,
            )
            session.add(attempt)
            session.flush()
            profile.current_section = "verbs"
            profile.current_topic = verb.infinitive
            profile.next_step = f"Svar på repetitionsspørgsmålet om {verb.infinitive}"
            profile.last_activity = utc_now()
            return VerbReviewSnapshot(
                id=attempt.id,
                verb_id=verb.id,
                question=attempt.question,
                options=tuple(options),
            )

    def submit_verb_review(
        self,
        platform: str,
        user_id: str | int,
        attempt_id: int,
        selected_index: int,
        language: str = "da",
        now: datetime | None = None,
    ) -> VerbReviewResult:
        review_time = now or utc_now()
        with self.database.session() as session:
            profile = self._profile(session, platform, user_id, language)
            attempt = session.scalar(
                select(VerbReviewAttempt)
                .join(VerbProgress)
                .where(
                    VerbReviewAttempt.id == attempt_id,
                    VerbProgress.profile_id == profile.id,
                )
                .with_for_update()
            )
            if attempt is None:
                return VerbReviewResult(False, False, None, None, None)

            verb = attempt.verb
            options = json.loads(attempt.options_json)
            correct_answer = str(options[attempt.correct_index])
            if attempt.completed:
                return VerbReviewResult(
                    True,
                    True,
                    attempt.was_correct,
                    correct_answer,
                    _verb_snapshot(verb),
                )
            if selected_index < 0 or selected_index >= len(options):
                return VerbReviewResult(
                    True, False, None, correct_answer, _verb_snapshot(verb)
                )

            correct = selected_index == attempt.correct_index
            attempt.completed = True
            attempt.was_correct = correct
            attempt.completed_at = review_time
            schedule = calculate_next_review(
                verb.successful_reviews,
                correct,
                review_time,
            )
            verb.successful_reviews = schedule.successful_reviews
            verb.status = schedule.status
            verb.next_review = schedule.next_review
            verb.last_reviewed = review_time
            if correct:
                verb.correct_count += 1
            else:
                verb.wrong_count += 1

            self._record_activity(
                session,
                profile,
                "verbs",
                verb.infinitive,
                100 if correct else 0,
                1 if correct else 0,
                0 if correct else 1,
                {"verb_id": verb.id, "attempt_id": attempt.id},
                "Gentag de forfaldne verber eller lær et nyt",
            )
            session.flush()
            return VerbReviewResult(
                True,
                False,
                correct,
                correct_answer,
                _verb_snapshot(verb),
            )

    def get_verb_stats(
        self,
        platform: str,
        user_id: str | int,
        language: str = "da",
        now: datetime | None = None,
    ) -> dict[str, int]:
        review_time = now or utc_now()
        with self.database.session() as session:
            profile = self._profile(session, platform, user_id, language)
            self._ensure_verbs(session, profile)
            verbs = session.scalars(
                select(VerbProgress).where(VerbProgress.profile_id == profile.id)
            ).all()
            return {
                "total": sum(verb.status != "new" for verb in verbs),
                "new": sum(verb.status == "new" for verb in verbs),
                "learning": sum(verb.status == "learning" for verb in verbs),
                "review": sum(verb.status == "review" for verb in verbs),
                "mastered": sum(verb.status == "mastered" for verb in verbs),
                "due": sum(
                    verb.status != "new"
                    and verb.next_review is not None
                    and self._is_due(verb.next_review, review_time)
                    for verb in verbs
                ),
            }

    @staticmethod
    def _is_due(value: datetime, now: datetime) -> bool:
        if value.tzinfo is None and now.tzinfo is not None:
            now = now.replace(tzinfo=None)
        return value <= now

    def get_mastered_verbs(
        self,
        platform: str,
        user_id: str | int,
        language: str = "da",
    ) -> list[VerbSnapshot]:
        with self.database.session() as session:
            profile = self._profile(session, platform, user_id, language)
            self._ensure_verbs(session, profile)
            rows = session.scalars(
                select(VerbProgress)
                .where(
                    VerbProgress.profile_id == profile.id,
                    VerbProgress.status == "mastered",
                )
                .order_by(VerbProgress.infinitive)
            ).all()
            return [_verb_snapshot(row) for row in rows]

    def get_review_counts(
        self,
        platform: str,
        user_id: str | int,
        language: str = "da",
        now: datetime | None = None,
    ) -> dict[str, int]:
        review_time = now or utc_now()
        with self.database.session() as session:
            profile = self._profile(session, platform, user_id, language)
            return {
                "verbs": session.scalar(
                    select(func.count(VerbProgress.id)).where(
                        VerbProgress.profile_id == profile.id,
                        VerbProgress.status != "new",
                        VerbProgress.next_review.is_not(None),
                        VerbProgress.next_review <= review_time,
                    )
                )
                or 0,
                "grammar": session.scalar(
                    select(func.count(GrammarTopic.id)).where(
                        GrammarTopic.profile_id == profile.id,
                        GrammarTopic.next_review.is_not(None),
                        GrammarTopic.next_review <= review_time,
                    )
                )
                or 0,
                "errors": session.scalar(
                    select(func.count(LearnerError.id)).where(
                        LearnerError.profile_id == profile.id,
                        LearnerError.status == "review",
                        LearnerError.next_review.is_not(None),
                        LearnerError.next_review <= review_time,
                    )
                )
                or 0,
                "words": session.scalar(
                    select(func.count(VocabularyItem.id)).where(
                        VocabularyItem.profile_id == profile.id,
                        VocabularyItem.next_review.is_not(None),
                        VocabularyItem.next_review <= review_time,
                    )
                )
                or 0,
            }

    def get_history(
        self,
        platform: str,
        user_id: str | int,
        language: str = "da",
    ) -> dict[str, list[str] | str | None]:
        with self.database.session() as session:
            profile = self._profile(session, platform, user_id, language)
            topics = session.scalars(
                select(GrammarTopic)
                .where(GrammarTopic.profile_id == profile.id)
                .order_by(GrammarTopic.updated_at.desc())
            ).all()
            errors = session.scalars(
                select(LearnerError)
                .where(
                    LearnerError.profile_id == profile.id,
                    LearnerError.status == "review",
                )
                .order_by(LearnerError.count.desc(), LearnerError.last_seen.desc())
                .limit(5)
            ).all()
            completed_topics = session.scalars(
                select(ExerciseResult.topic)
                .where(ExerciseResult.profile_id == profile.id)
                .order_by(ExerciseResult.completed_at.desc())
                .limit(10)
            ).all()
            return {
                "completed": list(dict.fromkeys(completed_topics)),
                "mastered": [
                    topic.topic for topic in topics if topic.status == "mastered"
                ],
                "learning": [
                    topic.topic for topic in topics if topic.status == "learning"
                ],
                "review": [topic.topic for topic in topics if topic.status == "review"],
                "errors": [error.error_type for error in errors],
                "current_topic": profile.current_topic,
                "next_step": profile.next_step,
            }

    def get_test_stats(
        self,
        platform: str,
        user_id: str | int,
        language: str = "da",
    ) -> dict[str, int | None]:
        with self.database.session() as session:
            profile = self._profile(session, platform, user_id, language)
            scores = list(
                session.scalars(
                    select(ExerciseResult.score)
                    .where(
                        ExerciseResult.profile_id == profile.id,
                        ExerciseResult.section == "tests",
                        ExerciseResult.score.is_not(None),
                    )
                    .order_by(ExerciseResult.completed_at.desc())
                )
            )
            return {
                "count": len(scores),
                "latest": round(scores[0]) if scores else None,
                "best": round(max(scores)) if scores else None,
                "average": round(sum(scores) / len(scores)) if scores else None,
            }

    def get_today_summary(
        self,
        platform: str,
        user_id: str | int,
        language: str = "da",
        now: datetime | None = None,
    ) -> dict[str, int | float]:
        current_time = now or utc_now()
        day_start = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
        with self.database.session() as session:
            profile = self._profile(session, platform, user_id, language)
            results = session.scalars(
                select(ExerciseResult).where(
                    ExerciseResult.profile_id == profile.id,
                    ExerciseResult.completed_at >= day_start,
                )
            ).all()
            scores = [result.score for result in results if result.score is not None]
            summary: dict[str, int | float] = {
                section: sum(result.section == section for result in results)
                for section in STUDY_SECTIONS
            }
            summary["score"] = round(sum(scores) / len(scores)) if scores else 0
            summary["total"] = len(results)
            return summary

    def build_learner_context(
        self,
        platform: str,
        user_id: str | int,
        language: str = "da",
    ) -> str:
        with self.database.session() as session:
            profile = self._profile(session, platform, user_id, language)
            sections = session.scalars(
                select(SectionProgress).where(SectionProgress.profile_id == profile.id)
            ).all()
            errors = session.scalars(
                select(LearnerError)
                .where(
                    LearnerError.profile_id == profile.id,
                    LearnerError.status == "review",
                )
                .order_by(LearnerError.count.desc(), LearnerError.last_seen.desc())
                .limit(2)
            ).all()
            learned_verbs = session.scalars(
                select(VerbProgress)
                .where(
                    VerbProgress.profile_id == profile.id,
                    VerbProgress.status != "new",
                )
                .order_by(VerbProgress.last_reviewed.desc(), VerbProgress.id.desc())
                .limit(3)
            ).all()
            due_verbs = session.scalars(
                select(VerbProgress)
                .where(
                    VerbProgress.profile_id == profile.id,
                    VerbProgress.status != "new",
                    VerbProgress.next_review.is_not(None),
                    VerbProgress.next_review <= utc_now(),
                )
                .order_by(VerbProgress.next_review)
                .limit(2)
            ).all()

            weak_area = "not identified yet"
            if errors:
                weak_area = ", ".join(error.error_type for error in errors)
            elif any(row.completed_tasks for row in sections):
                weakest = min(
                    sections,
                    key=lambda row: calculate_section_progress(
                        row.completed_tasks,
                        row.total_tasks,
                    ),
                )
                weak_area = SECTION_LABELS.get(weakest.section, weakest.section)

            return "\n".join(
                [
                    "Learner:",
                    f"Level: {profile.current_level}",
                    f"Current topic: {profile.current_topic or 'not selected'}",
                    f"Weak area: {weak_area}",
                    "Recently learned verbs: "
                    + (", ".join(verb.infinitive for verb in learned_verbs) or "none"),
                    "Due for review: "
                    + (", ".join(verb.infinitive for verb in due_verbs) or "none"),
                    f"Next step: {profile.next_step or 'open /learn'}",
                ]
            )

    def reset_progress(
        self,
        platform: str,
        user_id: str | int,
        language: str = "da",
    ) -> ProfileSnapshot:
        normalized_user_id = str(user_id)
        with self.database.session() as session:
            profile = session.scalar(
                select(LearnerProfile).where(
                    LearnerProfile.platform == platform,
                    LearnerProfile.user_id == normalized_user_id,
                    LearnerProfile.language == language,
                )
            )
            if profile is not None:
                session.delete(profile)
                session.flush()
            return _profile_snapshot(
                self._profile(session, platform, normalized_user_id, language)
            )


_memory_lock = threading.Lock()
_memory: StudyMemory | None = None


def get_study_memory() -> StudyMemory:
    global _memory
    configured_url = normalize_database_url(
        os.getenv("DATABASE_URL") or "sqlite:///study_memory.db"
    )
    with _memory_lock:
        if _memory is None or _memory.database.url != configured_url:
            if _memory is not None:
                _memory.database.dispose()
            _memory = StudyMemory(StudyDatabase(configured_url))
        return _memory


def initialize_study_memory() -> None:
    get_study_memory()

import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship
from sqlalchemy.pool import StaticPool


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class LearnerProfile(Base):
    __tablename__ = "learner_profiles"
    __table_args__ = (
        UniqueConstraint(
            "platform",
            "user_id",
            "language",
            name="uq_learner_platform_user_language",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    language: Mapped[str] = mapped_column(String(16), nullable=False, default="da")
    current_level: Mapped[str] = mapped_column(String(8), nullable=False, default="A1")
    current_section: Mapped[str | None] = mapped_column(String(32))
    current_topic: Mapped[str | None] = mapped_column(String(160))
    last_activity: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    next_step: Mapped[str | None] = mapped_column(String(240))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    sections: Mapped[list["SectionProgress"]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
    )
    grammar_topics: Mapped[list["GrammarTopic"]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
    )
    errors: Mapped[list["LearnerError"]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
    )
    verbs: Mapped[list["VerbProgress"]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
    )
    vocabulary: Mapped[list["VocabularyItem"]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
    )
    results: Mapped[list["ExerciseResult"]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
    )
    quizzes: Mapped[list["QuizSession"]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
    )


class SectionProgress(Base):
    __tablename__ = "section_progress"
    __table_args__ = (
        UniqueConstraint("profile_id", "section", name="uq_profile_section"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("learner_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    section: Mapped[str] = mapped_column(String(32), nullable=False)
    completed_tasks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tasks: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    correct_answers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    wrong_answers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_topic: Mapped[str | None] = mapped_column(String(160))
    last_score: Mapped[float | None] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    profile: Mapped[LearnerProfile] = relationship(back_populates="sections")


class GrammarTopic(Base):
    __tablename__ = "grammar_topics"
    __table_args__ = (
        UniqueConstraint("profile_id", "topic", name="uq_profile_grammar_topic"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("learner_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    topic: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="new")
    correct_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    wrong_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_reviewed: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_review: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    profile: Mapped[LearnerProfile] = relationship(back_populates="grammar_topics")


class LearnerError(Base):
    __tablename__ = "learner_errors"
    __table_args__ = (
        UniqueConstraint(
            "profile_id",
            "error_type",
            "example",
            name="uq_profile_error_example",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("learner_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    error_type: Mapped[str] = mapped_column(String(80), nullable=False)
    example: Mapped[str] = mapped_column(Text, nullable=False)
    correction: Mapped[str] = mapped_column(Text, nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="review")
    next_review: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )

    profile: Mapped[LearnerProfile] = relationship(back_populates="errors")


class VerbProgress(Base):
    __tablename__ = "verb_progress"
    __table_args__ = (
        UniqueConstraint("profile_id", "infinitive", name="uq_profile_verb"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("learner_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    infinitive: Mapped[str] = mapped_column(String(80), nullable=False)
    present: Mapped[str] = mapped_column(String(80), nullable=False)
    past: Mapped[str] = mapped_column(String(80), nullable=False)
    past_participle: Mapped[str] = mapped_column(String(80), nullable=False)
    translation_ru: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="new")
    correct_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    wrong_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    successful_reviews: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_reviewed: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_review: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    profile: Mapped[LearnerProfile] = relationship(back_populates="verbs")
    attempts: Mapped[list["VerbReviewAttempt"]] = relationship(
        back_populates="verb",
        cascade="all, delete-orphan",
    )


class VocabularyItem(Base):
    __tablename__ = "vocabulary_items"
    __table_args__ = (
        UniqueConstraint("profile_id", "term", name="uq_profile_vocabulary"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("learner_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    term: Mapped[str] = mapped_column(String(160), nullable=False)
    translation: Mapped[str] = mapped_column(String(240), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="new")
    correct_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    wrong_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_reviewed: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_review: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )

    profile: Mapped[LearnerProfile] = relationship(back_populates="vocabulary")


class ExerciseResult(Base):
    __tablename__ = "exercise_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("learner_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    section: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    topic: Mapped[str] = mapped_column(String(160), nullable=False)
    score: Mapped[float | None] = mapped_column(Float)
    correct_answers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    wrong_answers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    details_json: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        index=True,
    )

    profile: Mapped[LearnerProfile] = relationship(back_populates="results")


class QuizSession(Base):
    __tablename__ = "quiz_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("learner_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    topic: Mapped[str] = mapped_column(String(160), nullable=False)
    questions_json: Mapped[str] = mapped_column(Text, nullable=False)
    current_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    correct_answers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    wrong_answers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    profile: Mapped[LearnerProfile] = relationship(back_populates="quizzes")


class VerbReviewAttempt(Base):
    __tablename__ = "verb_review_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    verb_id: Mapped[int] = mapped_column(
        ForeignKey("verb_progress.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    options_json: Mapped[str] = mapped_column(Text, nullable=False)
    correct_index: Mapped[int] = mapped_column(Integer, nullable=False)
    completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    was_correct: Mapped[bool | None] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    verb: Mapped[VerbProgress] = relationship(back_populates="attempts")


def normalize_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url.removeprefix("postgres://")
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return url


class StudyDatabase:
    def __init__(self, url: str | None = None) -> None:
        raw_url = url or os.getenv("DATABASE_URL") or "sqlite:///study_memory.db"
        self.url = normalize_database_url(raw_url)

        engine_kwargs: dict[str, object] = {
            "pool_pre_ping": True,
        }
        if self.url.startswith("sqlite"):
            engine_kwargs["connect_args"] = {"check_same_thread": False}
            if self.url in {"sqlite://", "sqlite:///:memory:"}:
                engine_kwargs["poolclass"] = StaticPool

        self.engine: Engine = create_engine(self.url, **engine_kwargs)

    def initialize(self) -> None:
        Base.metadata.create_all(self.engine)

    @contextmanager
    def session(self) -> Iterator[Session]:
        with Session(self.engine, expire_on_commit=False) as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

    def dispose(self) -> None:
        self.engine.dispose()

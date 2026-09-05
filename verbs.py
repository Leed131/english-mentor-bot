from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final


@dataclass(frozen=True)
class DanishVerb:
    infinitive: str
    present: str
    past: str
    past_participle: str
    translation_ru: str


DEFAULT_DANISH_VERBS: Final[tuple[DanishVerb, ...]] = (
    DanishVerb("at være", "er", "var", "været", "быть"),
    DanishVerb("at have", "har", "havde", "haft", "иметь"),
    DanishVerb("at gå", "går", "gik", "gået", "идти"),
    DanishVerb("at komme", "kommer", "kom", "kommet", "приходить"),
    DanishVerb("at spise", "spiser", "spiste", "spist", "есть"),
    DanishVerb("at se", "ser", "så", "set", "видеть"),
    DanishVerb("at gøre", "gør", "gjorde", "gjort", "делать"),
    DanishVerb("at tage", "tager", "tog", "taget", "брать"),
    DanishVerb("at sige", "siger", "sagde", "sagt", "говорить"),
    DanishVerb("at bo", "bor", "boede", "boet", "жить"),
)

REVIEW_INTERVAL_DAYS: Final[tuple[int, ...]] = (1, 3, 7, 14, 30)
MASTERY_REVIEWS: Final = 5


@dataclass(frozen=True)
class ReviewSchedule:
    successful_reviews: int
    status: str
    next_review: datetime


def calculate_next_review(
    successful_reviews: int,
    correct: bool,
    now: datetime,
) -> ReviewSchedule:
    if correct:
        new_count = min(successful_reviews + 1, MASTERY_REVIEWS)
        interval_index = min(new_count - 1, len(REVIEW_INTERVAL_DAYS) - 1)
        status = "mastered" if new_count >= MASTERY_REVIEWS else "learning"
        return ReviewSchedule(
            successful_reviews=new_count,
            status=status,
            next_review=now + timedelta(days=REVIEW_INTERVAL_DAYS[interval_index]),
        )

    new_count = max(0, successful_reviews - 1)
    return ReviewSchedule(
        successful_reviews=new_count,
        status="review",
        next_review=now + timedelta(days=1),
    )

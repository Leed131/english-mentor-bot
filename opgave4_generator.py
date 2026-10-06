"""Validated DU3 Modul 3 Opgave 4: match seven questions to three people."""
import json
import logging
import random

from quiz_generator import _get_client, _model

logger = logging.getLogger(__name__)

PERSONS = ("A", "B", "C")
RANK_ORDER = ("F", "E", "D", "C", "B", "A", "S")

RANK_GUIDANCE = {
    "F": (
        "Very easy A1. Each answer is stated directly in one profile, with strong lexical overlap "
        "between question and source text. Keep the three people clearly different."
    ),
    "E": (
        "Easy A1/A2. Use simple synonyms and direct facts. A learner should compare all three profiles "
        "but should not need subtle inference."
    ),
    "D": (
        "A2. Use everyday paraphrase, time/order clues and preferences. Some profiles may mention the same "
        "general topic, but only one must satisfy each question."
    ),
    "C": (
        "DU3 Modul 3 baseline, A2/B1, like official-style Opgave 4. Questions should often paraphrase rather "
        "than copy the exact wording. The learner must locate details across three medium-length texts."
    ),
    "B": (
        "Strong B1. Reduce obvious keyword overlap. Use semantic paraphrase and close distractor details: "
        "two people may mention the same theme, but only one matches the exact question."
    ),
    "A": (
        "B1+/B2. Questions may require combining two nearby facts or interpreting attitude, sequence or habit. "
        "Avoid trick wording; evidence must still be explicit enough to prove one answer."
    ),
    "S": (
        "Extra challenge around B2. Use dense but natural profiles, subtle paraphrase and highly similar themes. "
        "Do not make answers predictable from one repeated noun; require precise comprehension of the full passage."
    ),
}

# Rank, Danish chunk, Russian meaning, category.
TEXT_MATCH_PHRASES = (
    ("F", "kan godt lide", "нравится", "præference"),
    ("F", "jeg husker, at", "я помню, что…", "fortælling"),
    ("F", "til sidst", "в конце / в итоге", "tid"),
    ("E", "være på besøg", "быть в гостях", "hverdag"),
    ("E", "være nervøs", "нервничать", "følelse"),
    ("E", "gå fint", "пройти хорошо", "vurdering"),
    ("E", "være vant til", "быть привыкшим к…", "vane"),
    ("D", "gøre et godt indtryk", "произвести хорошее впечатление", "hverdag"),
    ("D", "have det med", "иметь это с собой / принести", "hverdag"),
    ("D", "blive nødt til at", "быть вынужденным…", "hverdag"),
    ("D", "tage videre til", "поехать / пойти дальше в другое место", "tid"),
    ("D", "være vild med", "очень любить / быть в восторге от", "præference"),
    ("C", "det gode er, at", "хорошо то, что…", "vurdering"),
    ("C", "som regel", "как правило", "vane"),
    ("C", "i forbindelse med", "в связи с…", "forbinder"),
    ("C", "kunne sammenligne", "мочь сравнить", "vurdering"),
    ("C", "opføre sig", "вести себя", "hverdag"),
    ("C", "som det plejer at være", "как обычно", "vane"),
    ("C", "for hver gang", "с каждым разом", "tid"),
    ("B", "være opmærksom på", "обращать внимание на / следить за…", "vurdering"),
    ("B", "lyde negativ", "звучать негативно", "vurdering"),
    ("B", "ikke forstå en joke", "не понять шутку", "hverdag"),
    ("B", "være kendt for at", "быть известным тем, что…", "vurdering"),
    ("A", "det virker til, at", "создаётся впечатление, что…", "vurdering"),
    ("A", "i modsætning til", "в отличие от…", "forbinder"),
    ("A", "det hænger sammen med", "это связано с…", "forbinder"),
    ("S", "set fra hans/hendes synspunkt", "с его/её точки зрения", "vurdering"),
    ("S", "det tyder på, at", "это указывает на то, что…", "vurdering"),
    ("S", "uden at sige det direkte", "не говоря об этом прямо", "vurdering"),
)

SCHEMA = """Return JSON only:
{
  "title":"Danish title",
  "topic":"short Danish topic",
  "profiles":[
    {"label":"A","name":"Meng","text":"Danish first-person profile"},
    {"label":"B","name":"Hanna","text":"Danish first-person profile"},
    {"label":"C","name":"Ivan","text":"Danish first-person profile"}
  ],
  "questions":[
    {"question":"Hvem ...?","answer":"A","explanation_ru":"Russian explanation with concrete evidence"}
  ]
}
Exactly 3 profiles labelled A, B, C and exactly 7 questions.
Each question has exactly one provably correct person A/B/C. Answer letters may repeat.
The three profiles must be comparable in length and all discuss the same broad everyday theme from different experiences.
Questions must test detailed reading: preference, event sequence, habit/background, attitude, consequence, or one precise experience.
Do not write yes/no questions. Use natural Danish question wording, usually Hvem...?
At ranks C-S, avoid merely copying a distinctive phrase from the correct profile into the question; paraphrase naturally.
Russian explanations must identify the decisive evidence and distinguish the closest competing profile when useful.
Max lengths: title 120, topic 100, name 40, profile 1800, question 220, explanation 650 characters.
"""


def validate_text_match(raw, rank="C"):
    if rank not in RANK_ORDER:
        raise ValueError("Ukendt rang.")
    if not isinstance(raw, dict):
        raise ValueError("Ожидается объект задания.")

    def text(value, limit):
        if not isinstance(value, str) or not value.strip() or len(value) > limit:
            raise ValueError("Пустой или слишком длинный текст.")
        return value.strip()

    profiles = raw.get("profiles")
    if not isinstance(profiles, list) or len(profiles) != 3:
        raise ValueError("Нужны ровно три текста A-C.")
    clean_profiles = []
    seen_labels = set()
    for profile in profiles:
        if not isinstance(profile, dict):
            raise ValueError("Неверный профиль.")
        label = text(profile.get("label"), 1)
        if label not in PERSONS or label in seen_labels:
            raise ValueError("Профили должны быть A, B, C.")
        seen_labels.add(label)
        clean_profiles.append({
            "label": label,
            "name": text(profile.get("name"), 40),
            "text": text(profile.get("text"), 1800),
        })
    clean_profiles.sort(key=lambda item: PERSONS.index(item["label"]))

    questions = raw.get("questions")
    if not isinstance(questions, list) or len(questions) != 7:
        raise ValueError("Нужно ровно семь вопросов.")
    clean_questions = []
    for question in questions:
        if not isinstance(question, dict):
            raise ValueError("Неверный вопрос.")
        answer = text(question.get("answer"), 1)
        if answer not in PERSONS:
            raise ValueError("Ответ должен быть A, B или C.")
        clean_questions.append({
            "question": text(question.get("question"), 220),
            "answer": answer,
            "explanation_ru": text(question.get("explanation_ru"), 650),
        })

    if len({" ".join(q["question"].casefold().split()) for q in clean_questions}) != 7:
        raise ValueError("Вопросы повторяются.")

    return {
        "title": text(raw.get("title"), 120),
        "topic": text(raw.get("topic"), 100),
        "rank": rank,
        "profiles": clean_profiles,
        "questions": clean_questions,
    }


async def _json_call(system, prompt):
    response = await _get_client().chat.completions.create(
        model=_model(),
        messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.45,
        max_tokens=7600,
        timeout=75,
    )
    return json.loads(response.choices[0].message.content or "{}")


def _phrase_targets(rank, phrase_bank=None):
    if phrase_bank:
        return list(phrase_bank)[:8]
    max_index = RANK_ORDER.index(rank)
    eligible = [
        (phrase, translation)
        for phrase_rank, phrase, translation, _ in TEXT_MATCH_PHRASES
        if RANK_ORDER.index(phrase_rank) <= max_index
    ]
    if not eligible:
        return []
    count = 5 if rank in {"F", "E"} else 4 if rank in {"D", "C"} else 3
    return random.SystemRandom().sample(eligible, min(count, len(eligible)))


def _review_payload(data):
    return {
        "profiles": data["profiles"],
        "questions": [
            {"index": index + 1, "question": q["question"]}
            for index, q in enumerate(data["questions"])
        ],
    }


async def prepare_text_match(topic, rank="C", recent_titles=(), phrase_bank=None):
    if rank not in RANK_ORDER:
        raise ValueError("Ukendt rang.")
    targets = _phrase_targets(rank, phrase_bank)
    last_error = None
    previous = None

    for attempt in range(3):
        stage = "generation"
        try:
            if rank in {"B", "A", "S"}:
                unpredictability = (
                    "Make answer selection less predictable: do not let a single shared keyword reveal the person. "
                    "Use paraphrase, contrast, event order, attitude and background. At least some questions should have "
                    "two profiles mentioning the same general subject, with only one matching the exact detail. "
                )
            else:
                unpredictability = (
                    "Use clear but natural distinctions appropriate to the rank. "
                )

            prompt = (
                "Create a NEW DU3 Modul 3 Opgave 4-style Danish reading exercise. "
                + RANK_GUIDANCE[rank] + " " + unpredictability +
                "All three people discuss one coherent everyday theme from different perspectives. "
                "Useful chunks may recur naturally, especially earlier items in this learning-priority list, but do not "
                "force them or make them answer giveaways: "
                + "; ".join(phrase for phrase, _ in targets) + ". "
                "Vary the answer distribution naturally. Repeated A/B/C answers are allowed, but avoid obvious cycles or patterns. "
            )
            if previous is not None:
                prompt += (
                    "Repair the previous candidate using the reviewer feedback. Make every question uniquely attributable to one profile. "
                )

            raw = await _json_call(
                SCHEMA,
                prompt + json.dumps({
                    "topic": topic,
                    "rank": rank,
                    "recent_titles_to_avoid": list(recent_titles),
                    "previous_candidate": previous,
                    "review_feedback": str(last_error) if last_error else None,
                }, ensure_ascii=False),
            )
            previous = raw
            data = validate_text_match(raw, rank=rank)
            if data["title"].casefold() in {title.casefold() for title in recent_titles}:
                raise ValueError("Repeat of a recent title.")

            stage = "logic"
            review = await _json_call(
                (
                    "Independently answer seven Danish reading questions from three labelled profiles A, B, C. "
                    "For EVERY question compare all three profiles and list every candidate supported by the text. "
                    'Return JSON only: {"valid":true,"answers":["A","C","B","A","C","B","A"],'
                    '"candidates":[["A"],["C"],["B"],["A"],["C"],["B"],["A"]],"reason":"..."}. '
                    "valid=false if any question is ambiguous, unsupported, or depends on invented assumptions. "
                    "Each candidates list must contain exactly one person for a valid task."
                ),
                json.dumps(_review_payload(data), ensure_ascii=False),
            )
            expected_answers = [q["answer"] for q in data["questions"]]
            expected_candidates = [[answer] for answer in expected_answers]
            if (
                review.get("valid") is not True
                or review.get("answers") != expected_answers
                or review.get("candidates") != expected_candidates
            ):
                raise ValueError(
                    "Logical review rejected candidate: "
                    + str(review.get("reason", ""))[:800]
                    + "; candidates="
                    + str(review.get("candidates"))[:220]
                )

            stage = "explanations"
            check = await _json_call(
                (
                    'Check the seven Russian explanations against the Danish profiles and answer key. '
                    'Return JSON {"valid":true,"reason":""}; valid=false for any wrong translation, unsupported detail, '
                    'or explanation that fails to justify the selected person.'
                ),
                json.dumps({"exercise": data, "answers": expected_answers}, ensure_ascii=False),
            )
            if check.get("valid") is not True:
                raise ValueError("Explanation review: " + str(check.get("reason", ""))[:800])
            return data

        except (ValueError, TypeError, KeyError) as error:
            last_error = error
            logger.warning("Opgave4 candidate rejected: stage=%s attempt=%d", stage, attempt + 1)

    raise ValueError("Opgave 4 kunne ikke kontrolleres.") from last_error


def completed_profiles_text(data):
    parts = [data["title"]]
    for profile in data["profiles"]:
        parts.append(f"{profile['label']}. {profile['name']}\n{profile['text']}")
    return "\n\n".join(parts)


def extract_key_phrases(data, limit=6):
    full = completed_profiles_text(data).casefold()
    rank = data.get("rank", "C")
    max_rank = RANK_ORDER.index(rank)
    matches = []
    for phrase_rank, phrase, russian, category in TEXT_MATCH_PHRASES:
        if RANK_ORDER.index(phrase_rank) > max_rank:
            continue
        if phrase.casefold() not in full:
            continue
        words = len(phrase.split())
        category_bonus = 5 if category in {"vurdering", "vane", "præference"} else 3
        score = words * 10 + category_bonus + RANK_ORDER.index(phrase_rank)
        matches.append((score, phrase, russian))
    matches.sort(key=lambda item: (-item[0], item[1]))
    result = []
    for _, phrase, russian in matches:
        normalized = phrase.casefold()
        if any(
            normalized in chosen.casefold() or chosen.casefold() in normalized
            for chosen, _ in result
        ):
            continue
        result.append((phrase, russian))
        if len(result) >= limit:
            break
    return result

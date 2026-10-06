"""Validated DU3 Modul 3-style paragraph gap exercises."""
import json
import logging
import random

from quiz_generator import _get_client, _model

logger = logging.getLogger(__name__)

LETTERS = "ABCD"
RANK_ORDER = ("F", "E", "D", "C", "B", "A", "S")

RANK_GUIDANCE = {
    "F": (
        "Very easy A1. Use short paragraphs and very explicit logical clues. "
        "The correct sentence may contain a clear connector such as derfor, men or så."
    ),
    "E": (
        "Easy A1/A2. Use direct time, cause and consequence clues. Distractors should be plausible "
        "but clearly contradicted by the next sentence."
    ),
    "D": (
        "A2. Use everyday narrative, pronouns and short fordi/selvom clauses. The learner should "
        "need to read both before and after the gap."
    ),
    "C": (
        "DU3 Modul 3 baseline, A2/B1, like official-style Opgave 3. All four options should be "
        "grammatically plausible; the correct choice must fit the paragraph's meaning and the following sentence."
    ),
    "B": (
        "Strong B1. Make distractors semantically close. Do not let one repeated word or one connector alone reveal "
        "the answer. Use paraphrase, temporal sequence and cause/effect across several sentences."
    ),
    "A": (
        "B1+/B2. Use natural narrative with indirect clues, reference words and nuanced contrast. At least two options "
        "should seem possible from the sentence before the gap, but only one must fit what follows."
    ),
    "S": (
        "Extra challenge around B2. Use subtle discourse logic and close distractors of similar length and register. "
        "Avoid making the answer predictable from connector matching; require inference from the whole paragraph."
    ),
}

# Rank, Danish chunk, Russian meaning, category.
TEXT_PHRASES = (
    ("F", "derfor", "поэтому", "forbinder"),
    ("F", "men", "но", "forbinder"),
    ("F", "så", "так / поэтому / тогда", "forbinder"),
    ("E", "fordi", "потому что", "forbinder"),
    ("E", "for", "ведь / потому что", "forbinder"),
    ("E", "bagefter", "после этого", "tid"),
    ("D", "nemlig", "а именно / ведь", "forbinder"),
    ("D", "selvom", "хотя", "forbinder"),
    ("D", "på den måde", "таким образом", "forbinder"),
    ("D", "have tid til at", "иметь время на то, чтобы…", "hverdag"),
    ("D", "komme i gang med at", "начать / взяться за…", "hverdag"),
    ("C", "det er ikke så mærkeligt, at", "неудивительно, что…", "vurdering"),
    ("C", "være glad for", "быть довольным / любить", "hverdag"),
    ("C", "have lyst til at", "хотеть / иметь желание…", "ønske"),
    ("C", "plejer at", "обычно делать…", "vane"),
    ("C", "i fremtiden", "в будущем", "tid"),
    ("C", "et par dage efter", "через пару дней", "tid"),
    ("C", "glæde sig til", "ждать с радостью", "ønske"),
    ("B", "det betyder, at", "это означает, что…", "forbinder"),
    ("B", "samtidig", "одновременно / в то же время", "forbinder"),
    ("B", "alligevel", "всё же / несмотря на это", "forbinder"),
    ("B", "på grund af", "из-за / по причине", "forbinder"),
    ("B", "være nødt til at", "быть вынужденным…", "hverdag"),
    ("A", "til gengæld", "зато / с другой стороны", "forbinder"),
    ("A", "derimod", "напротив / зато", "forbinder"),
    ("A", "efterhånden", "постепенно / со временем", "tid"),
    ("A", "i modsætning til", "в отличие от…", "forbinder"),
    ("A", "det viser sig, at", "оказывается, что…", "vurdering"),
    ("S", "ikke desto mindre", "тем не менее", "forbinder"),
    ("S", "set i bakspejlet", "оглядываясь назад", "vurdering"),
    ("S", "i den forbindelse", "в этой связи", "forbinder"),
    ("S", "det hænger sammen med, at", "это связано с тем, что…", "forbinder"),
    ("S", "på trods af det", "несмотря на это", "forbinder"),
)

SCHEMA = """Return JSON only:
{
 "title":"Danish title",
 "topic":"short Danish topic",
 "paragraphs":[
   {
     "before":"Danish text before one missing sentence",
     "after":"Danish text after the missing sentence",
     "options":{"A":"sentence","B":"sentence","C":"sentence","D":"sentence"},
     "answer":"C",
     "explanation_ru":"Russian explanation of why it fits both sides and why the best distractor fails"
   }
 ]
}
Exactly 5 paragraphs. Each paragraph has exactly one missing COMPLETE sentence and exactly four distinct options A-D.
The five paragraphs must form ONE coherent short story or informational text with continuity.
Each correct sentence must fit BOTH before and after the gap, not merely the preceding sentence.
Every option must be grammatical Danish and locally plausible. Only one option may fit the entire paragraph.
Correct letters may repeat, as in real Opgave 3. Do not use a fixed answer pattern.
Russian explanations must cite concrete clues before and after the gap.
Max lengths: title 120, topic 100, before 900, after 900, option 220, explanation 650 characters.
"""


def validate_text_gap(raw, rank="C"):
    if rank not in RANK_ORDER:
        raise ValueError("Ukendt rang.")
    if not isinstance(raw, dict):
        raise ValueError("Ожидается объект задания.")

    def text(value, limit):
        if not isinstance(value, str) or not value.strip() or len(value) > limit:
            raise ValueError("Пустой или слишком длинный текст.")
        return value.strip()

    paragraphs = raw.get("paragraphs")
    if not isinstance(paragraphs, list) or len(paragraphs) != 5:
        raise ValueError("Нужно ровно пять абзацев.")

    clean = []
    for paragraph in paragraphs:
        if not isinstance(paragraph, dict):
            raise ValueError("Неверный абзац.")
        options = paragraph.get("options")
        if not isinstance(options, dict) or set(options) != set(LETTERS):
            raise ValueError("В каждом абзаце нужны варианты A-D.")
        options = {letter: text(options[letter], 220) for letter in LETTERS}
        if len({" ".join(value.casefold().split()) for value in options.values()}) != 4:
            raise ValueError("Варианты повторяются.")
        answer = text(paragraph.get("answer"), 1)
        if answer not in LETTERS:
            raise ValueError("Неверный ключ.")
        clean.append({
            "before": text(paragraph.get("before"), 900),
            "after": text(paragraph.get("after"), 900),
            "options": options,
            "answer": answer,
            "explanation_ru": text(paragraph.get("explanation_ru"), 650),
        })

    return {
        "title": text(raw.get("title"), 120),
        "topic": text(raw.get("topic"), 100),
        "rank": rank,
        "paragraphs": clean,
    }


async def _json_call(system, prompt):
    response = await _get_client().chat.completions.create(
        model=_model(),
        messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.45,
        max_tokens=7000,
        timeout=75,
    )
    return json.loads(response.choices[0].message.content or "{}")


def _phrase_targets(rank):
    index = RANK_ORDER.index(rank)
    eligible = [(p, r) for phrase_rank, p, r, _ in TEXT_PHRASES
                if RANK_ORDER.index(phrase_rank) <= index]
    if not eligible:
        return []
    count = 4 if rank in {"F", "E"} else 3 if rank in {"D", "C"} else 2
    return random.SystemRandom().sample(eligible, min(count, len(eligible)))


def _review_payload(data):
    return {
        "title": data["title"],
        "paragraphs": [
            {
                "index": index + 1,
                "before": paragraph["before"],
                "after": paragraph["after"],
                "options": paragraph["options"],
            }
            for index, paragraph in enumerate(data["paragraphs"])
        ],
    }


async def prepare_text_gap(topic, rank="C", recent_titles=()):
    if rank not in RANK_ORDER:
        raise ValueError("Ukendt rang.")
    targets = _phrase_targets(rank)
    last_error = None
    previous = None

    for attempt in range(3):
        stage = "generation"
        try:
            unpredictability = (
                "At B/A/S, do NOT make every answer depend on an obvious connector. "
                "Use paraphrase, reference, chronology and consequences; keep option length/register similar. "
                "At least two options may look plausible from the left context, but only one may fit the right context. "
                if rank in {"B", "A", "S"} else
                "Use clear but natural discourse clues appropriate to the rank. "
            )
            prompt = (
                "Create a NEW Danish reading exercise of the DU3 Modul 3 Opgave 3 type. "
                + RANK_GUIDANCE[rank] + " " + unpredictability +
                "The five paragraphs must tell one coherent everyday story. "
                "Useful target chunks may appear naturally, but never force all of them and never make connector matching the only skill: "
                + "; ".join(phrase for phrase, _ in targets) + ". "
                "Vary the correct answer positions naturally; repeated letters are allowed. "
            )
            if previous is not None:
                prompt += (
                    "Repair the previous candidate using the reviewer feedback. Make each gap uniquely solvable from both sides. "
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
            data = validate_text_gap(raw, rank=rank)
            if data["title"].casefold() in {title.casefold() for title in recent_titles}:
                raise ValueError("Repeat of a recent title.")

            stage = "logic"
            review = await _json_call(
                (
                    "Independently solve five Danish paragraph gaps. For each paragraph test ALL four options against BOTH "
                    "the text before and after the gap and the wider story. Return JSON only: "
                    '{"valid":true,"answers":["A","B","C","D","A"],'
                    '"candidates":[["A"],["B"],["C"],["D"],["A"]],"reason":"..."}. '
                    "valid=false if any paragraph is ambiguous, incoherent, or has no suitable answer. "
                    "Each candidates list must contain exactly one letter for a valid exercise."
                ),
                json.dumps(_review_payload(data), ensure_ascii=False),
            )
            expected_answers = [p["answer"] for p in data["paragraphs"]]
            expected_candidates = [[letter] for letter in expected_answers]
            if (
                review.get("valid") is not True
                or review.get("answers") != expected_answers
                or review.get("candidates") != expected_candidates
            ):
                raise ValueError(
                    "Logical review rejected the candidate: "
                    + str(review.get("reason", ""))[:800]
                    + "; candidates="
                    + str(review.get("candidates"))[:200]
                )

            stage = "explanations"
            check = await _json_call(
                (
                    'Check the five Russian explanations against the Danish text and answer key. '
                    'Return JSON {"valid":true,"reason":""}. Set valid=false for any wrong translation, '
                    'unsupported clue, or explanation that ignores the text after the gap.'
                ),
                json.dumps({
                    "exercise": data,
                    "answers": expected_answers,
                }, ensure_ascii=False),
            )
            if check.get("valid") is not True:
                raise ValueError("Explanation review: " + str(check.get("reason", ""))[:800])
            return data
        except (ValueError, TypeError, KeyError) as error:
            last_error = error
            logger.warning("Opgave3 candidate rejected: stage=%s attempt=%d", stage, attempt + 1)

    raise ValueError("Opgave 3 kunne ikke kontrolleres.") from last_error


def extract_key_phrases(data, limit=6):
    """Prefer reusable chunks/connectors that actually occur in the completed text."""
    full = completed_text(data).casefold()
    rank = data.get("rank", "C")
    max_rank = RANK_ORDER.index(rank)
    matches = []
    for phrase_rank, phrase, russian, category in TEXT_PHRASES:
        if RANK_ORDER.index(phrase_rank) > max_rank:
            continue
        if phrase.casefold() not in full:
            continue
        words = len(phrase.split())
        score = words * 10 + (5 if category != "forbinder" else 2) + RANK_ORDER.index(phrase_rank)
        matches.append((score, phrase, russian))
    matches.sort(key=lambda item: (-item[0], item[1]))
    result = []
    for _, phrase, russian in matches:
        normalized = phrase.casefold()
        if any(normalized in chosen.casefold() or chosen.casefold() in normalized
               for chosen, _ in result):
            continue
        result.append((phrase, russian))
        if len(result) >= limit:
            break
    return result


def completed_text(data):
    pieces = [data["title"]]
    for paragraph in data["paragraphs"]:
        pieces.extend([
            paragraph["before"],
            paragraph["options"][paragraph["answer"]],
            paragraph["after"],
        ])
    return "\n\n".join(pieces)

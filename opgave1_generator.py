"""Validated word-bank gap exercises modelled on DU3 Modul 3 local-cohesion reading tasks."""
import json
import logging
import random

from quiz_generator import _get_client, _model

logger = logging.getLogger(__name__)

RANK_ORDER = ("F", "E", "D", "C", "B", "A", "S")

RANK_GUIDANCE = {
    "F": (
        "Very easy A1. Six gaps. Use very common pronouns, conjunctions, negation, simple verbs and nouns. "
        "The local grammar should make most answers quite clear."
    ),
    "E": (
        "Easy A1/A2. Use simple function words and common everyday vocabulary. Include a few distractors of the same "
        "part of speech, but keep the surrounding sentence explicit."
    ),
    "D": (
        "A2. Mix conjunctions, adverbs, pronouns, auxiliaries and one or two content words. The learner must read the "
        "whole sentence, not only the word immediately before the gap."
    ),
    "C": (
        "DU3 Modul 3 baseline. Use six gaps and ten single-word choices, four unused. Test local text cohesion and "
        "grammar in context: conjunctions, adverbs, negation, pronouns, verb forms and occasional nouns. "
        "Several unused choices should be grammatically plausible somewhere, but only one global assignment is correct."
    ),
    "B": (
        "Strong B1. Make distractors less predictable. Use several words from similar grammatical categories, and make "
        "the correct choice depend on meaning plus syntax, not merely one obvious collocation."
    ),
    "A": (
        "B1+/B2. Use close adverb/conjunction/pronoun distractors and natural sentence structure. At least some gaps "
        "should have two locally plausible choices until the learner considers the wider clause or the one-use-only rule."
    ),
    "S": (
        "Extra challenge around B2. Keep all ten choices natural and similar in register. Avoid giveaway vocabulary. "
        "Require precise local cohesion, reference, negation, word order and global elimination while preserving one unique solution."
    ),
}

# Helpful reusable structures. These are learning priorities, not mandatory answers.
FOCUS_BANK = (
    ("F", "fordi", "потому что", "forbinder"),
    ("F", "men", "но", "forbinder"),
    ("F", "og", "и", "forbinder"),
    ("F", "ikke", "не", "negation"),
    ("F", "også", "тоже / также", "adverbium"),
    ("E", "har travlt med at", "быть занятым тем, что…", "mønster"),
    ("E", "sin egen", "свой собственный / своя собственная", "mønster"),
    ("E", "både ... og", "и … и / как … так и", "mønster"),
    ("E", "lige nu", "прямо сейчас", "tid"),
    ("D", "derfor", "поэтому", "forbinder"),
    ("D", "selvom", "хотя", "forbinder"),
    ("D", "heller ikke", "тоже не", "negation"),
    ("D", "aldrig", "никогда", "adverbium"),
    ("D", "allerede", "уже", "adverbium"),
    ("C", "nemlig", "ведь / а именно", "forbinder"),
    ("C", "på den måde", "таким образом", "forbinder"),
    ("C", "siden", "с тех пор как / поскольку", "forbinder"),
    ("C", "som regel", "как правило", "adverbium"),
    ("C", "til sidst", "в конце / наконец", "tid"),
    ("B", "derimod", "напротив / зато", "forbinder"),
    ("B", "alligevel", "всё же / несмотря на это", "forbinder"),
    ("B", "samtidig", "одновременно / в то же время", "forbinder"),
    ("A", "til gengæld", "зато / с другой стороны", "forbinder"),
    ("A", "efterhånden", "постепенно / со временем", "adverbium"),
    ("S", "ikke desto mindre", "тем не менее", "forbinder"),
)

SCHEMA = """Return JSON only:
{
  "title":"Danish title",
  "topic":"short Danish topic",
  "segments":["text before gap 1","between gap 1 and 2","...","text after gap 6"],
  "word_bank":["word1","word2","word3","word4","word5","word6","unused1","unused2","unused3","unused4"],
  "word_types":{"word1":"conjunction","word2":"adverb","word3":"verb","word4":"noun"},
  "answers":["word for gap1","word for gap2","word for gap3","word for gap4","word for gap5","word for gap6"],
  "explanations_ru":["why gap1 fits","... six explanations"],
  "focus":[
    {"phrase":"useful Danish word or short pattern connected to gap1","translation_ru":"Russian meaning","category":"short category"}
  ]
}
Exactly 7 non-empty segments, forming ONE coherent Danish everyday text when the six answers are inserted.
Exactly 10 distinct single-word choices in word_bank. Exactly 6 distinct answers; each answer appears in word_bank and is used once. Exactly 4 words are unused.
word_types must classify EVERY bank word with exactly one of: conjunction, adverb, negation, verb, pronoun, preposition, noun, adjective.
At rank C, the bank should normally resemble real mixed grammar/vocabulary tasks rather than a vocabulary list:
- at least 2 conjunctions/connectors;
- at least 2 items from adverb/negation;
- at least 1 verb;
- at least 1 content word from noun/adjective;
- the 6 correct answers must span at least 4 different word types.
Unused words should usually include same-type distractors (for example another conjunction/adverb/verb), not four unrelated nouns.
At B-S, make at least three unused words belong to types that also occur among the correct answers.
Exactly 6 Russian explanations and exactly 6 focus objects.
Every gap must be uniquely solvable from its local sentence/clause plus the global one-use-only rule.
Do not make capitalization reveal the answer. Put punctuation in segments, not in word_bank.
At C-S, avoid six obvious vocabulary blanks: primarily test function words, grammar and cohesion in context.
At B-S, several distractors should be grammatically similar, but there must still be one unique complete solution.
focus.phrase should be a useful reusable word or short chunk actually represented by the completed text, not a trivial noun unless the noun is the tested lexical item.
Max lengths: title 120, topic 100, segment 850, word 40, explanation 520, focus phrase 120, translation 180.
"""


def validate_word_gap(raw, rank="C"):
    if rank not in RANK_ORDER:
        raise ValueError("Ukendt rang.")
    if not isinstance(raw, dict):
        raise ValueError("Ожидается объект задания.")

    def text(value, limit):
        if not isinstance(value, str) or not value.strip() or len(value) > limit:
            raise ValueError("Пустой или слишком длинный текст.")
        return value.strip()

    segments = raw.get("segments")
    if not isinstance(segments, list) or len(segments) != 7:
        raise ValueError("Нужно семь фрагментов текста для шести пропусков.")
    segments = [text(value, 850) for value in segments]

    word_bank = raw.get("word_bank")
    if not isinstance(word_bank, list) or len(word_bank) != 10:
        raise ValueError("Нужно ровно десять слов.")
    word_bank = [text(value, 40) for value in word_bank]
    normalized_bank = [" ".join(value.casefold().split()) for value in word_bank]
    if any(" " in value.strip() for value in word_bank):
        raise ValueError("В банке должны быть только отдельные слова.")
    if len(set(normalized_bank)) != 10:
        raise ValueError("Слова в банке повторяются.")

    word_types = raw.get("word_types")
    if not isinstance(word_types, dict):
        raise ValueError("Нужны типы для всех слов.")
    allowed_types = {
        "conjunction", "adverb", "negation", "verb",
        "pronoun", "preposition", "noun", "adjective",
    }
    normalized_type_keys = {key.casefold(): value for key, value in word_types.items()}
    if set(normalized_type_keys) != set(normalized_bank):
        raise ValueError("Тип должен быть указан для каждого слова из банка.")
    clean_types = {}
    for word in word_bank:
        value = normalized_type_keys[word.casefold()]
        if value not in allowed_types:
            raise ValueError("Неизвестный тип слова.")
        clean_types[word] = value

    answers = raw.get("answers")
    if not isinstance(answers, list) or len(answers) != 6:
        raise ValueError("Нужно шесть ответов.")
    answers = [text(value, 40) for value in answers]
    if len({value.casefold() for value in answers}) != 6:
        raise ValueError("Каждое слово можно использовать только один раз.")
    lookup = {value.casefold(): value for value in word_bank}
    if any(value.casefold() not in lookup for value in answers):
        raise ValueError("Ответ отсутствует в банке слов.")
    answers = [lookup[value.casefold()] for value in answers]

    bank_types = [clean_types[word] for word in word_bank]
    answer_types = [clean_types[word] for word in answers]
    if rank in {"C", "B", "A", "S"}:
        if bank_types.count("conjunction") < 2:
            raise ValueError("На этом уровне нужны как минимум два союза/связки.")
        if sum(t in {"adverb", "negation"} for t in bank_types) < 2:
            raise ValueError("На этом уровне нужны наречия/отрицание.")
        if "verb" not in bank_types:
            raise ValueError("На этом уровне нужен хотя бы один глагол.")
        if not any(t in {"noun", "adjective"} for t in bank_types):
            raise ValueError("На этом уровне нужно хотя бы одно знаменательное слово.")
        if len(set(answer_types)) < 4:
            raise ValueError("Правильные ответы должны проверять разные типы слов.")
    if rank in {"B", "A", "S"}:
        unused = [word for word in word_bank if word not in answers]
        answer_type_set = set(answer_types)
        same_type_distractors = sum(
            clean_types[word] in answer_type_set for word in unused
        )
        if same_type_distractors < 3:
            raise ValueError("Слишком предсказуемые лишние слова.")

    explanations = raw.get("explanations_ru")
    if not isinstance(explanations, list) or len(explanations) != 6:
        raise ValueError("Нужно шесть объяснений.")
    explanations = [text(value, 520) for value in explanations]

    focus = raw.get("focus")
    if not isinstance(focus, list) or len(focus) != 6:
        raise ValueError("Нужно шесть фокусных элементов.")
    clean_focus = []
    completed = completed_text_from_parts(segments, answers).casefold()
    for item in focus:
        if not isinstance(item, dict):
            raise ValueError("Неверный фокусный элемент.")
        phrase = text(item.get("phrase"), 120)
        translation = text(item.get("translation_ru"), 180)
        category = text(item.get("category"), 48)
        # A short pattern may contain inflection around the answer, so only demand
        # that at least one meaningful token from it occurs in the completed text.
        tokens = [token.strip(".,!?;:()“”\"'").casefold() for token in phrase.split()]
        if not any(token and token in completed for token in tokens):
            raise ValueError("Фокусная фраза не связана с текстом.")
        clean_focus.append({
            "phrase": phrase,
            "translation_ru": translation,
            "category": category,
        })

    return {
        "title": text(raw.get("title"), 120),
        "topic": text(raw.get("topic"), 100),
        "rank": rank,
        "segments": segments,
        "word_bank": word_bank,
        "word_types": clean_types,
        "answers": answers,
        "explanations_ru": explanations,
        "focus": clean_focus,
    }


def completed_text_from_parts(segments, answers):
    pieces = [segments[0]]
    for index, answer in enumerate(answers):
        pieces.append(answer)
        pieces.append(segments[index + 1])
    return " ".join(piece.strip() for piece in pieces if piece.strip())


def completed_text(data):
    return completed_text_from_parts(data["segments"], data["answers"])


async def _json_call(system, prompt):
    response = await _get_client().chat.completions.create(
        model=_model(),
        messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.4,
        max_tokens=6500,
        timeout=75,
    )
    return json.loads(response.choices[0].message.content or "{}")


def _targets(rank, phrase_bank=None):
    if phrase_bank:
        return list(phrase_bank)[:8]
    max_rank = RANK_ORDER.index(rank)
    eligible = [
        (phrase, translation)
        for phrase_rank, phrase, translation, _ in FOCUS_BANK
        if RANK_ORDER.index(phrase_rank) <= max_rank
    ]
    if not eligible:
        return []
    count = 5 if rank in {"F", "E"} else 4 if rank in {"D", "C"} else 3
    return random.SystemRandom().sample(eligible, min(count, len(eligible)))


async def prepare_word_gap(topic, rank="C", recent_titles=(), phrase_bank=None):
    if rank not in RANK_ORDER:
        raise ValueError("Ukendt rang.")
    targets = _targets(rank, phrase_bank)
    previous = None
    last_error = None

    for attempt in range(3):
        stage = "generation"
        try:
            if rank in {"B", "A", "S"}:
                unpredictability = (
                    "Make the bank deliberately less predictable: include several distractors from the same grammatical "
                    "categories as correct words. Some gaps may admit two words superficially, but wider clause meaning and "
                    "the one-use-only constraint must yield one unique global assignment. "
                )
            else:
                unpredictability = (
                    "Keep the task natural and exam-like, with four plausible but clearly rejectable unused words. "
                )

            prompt = (
                "Create a NEW Danish word-bank gap exercise in the same structural style as DU3 Modul 3 local-cohesion reading: "
                "one coherent everyday text, six missing single words, ten choices, each word usable at most once, four unused. "
                "The bank must be a deliberate MIX of word types, not a random vocabulary list. At exam level C, prioritize "
                "connectors/conjunctions, adverbs/negation, verbs/auxiliaries and only a small number of content words. "
                + RANK_GUIDANCE[rank] + " " + unpredictability +
                "Useful structures may be inspired by this learning-priority list, especially earlier items, but do not force "
                "them and do not simply copy the list into the bank: "
                + "; ".join(phrase for phrase, _ in targets) + ". "
            )
            if previous is not None:
                prompt += "Repair the previous candidate using reviewer feedback; preserve the six-gap/ten-word structure. "

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
            data = validate_word_gap(raw, rank=rank)
            if data["title"].casefold() in {title.casefold() for title in recent_titles}:
                raise ValueError("Repeat of a recent title.")

            stage = "logic"
            review = await _json_call(
                (
                    "Independently solve a Danish six-gap word-bank task. Every bank word may be used at most once. "
                    'Return JSON only: {"valid":true,"answers":["w1","w2","w3","w4","w5","w6"],'
                    '"candidates":[["w1"],["w2"],["w3"],["w4"],["w5"],["w6"]],"reason":"..."}. '
                    "Test syntax, meaning, local cohesion and the global one-use constraint. valid=false if another complete "
                    "assignment is reasonably possible or any gap lacks a defensible answer."
                ),
                json.dumps({
                    "segments": data["segments"],
                    "word_bank": data["word_bank"],
                }, ensure_ascii=False),
            )
            expected = [answer.casefold() for answer in data["answers"]]
            solved = [str(answer).casefold() for answer in review.get("answers", [])]
            candidates = [
                [str(value).casefold() for value in group]
                for group in review.get("candidates", [])
                if isinstance(group, list)
            ]
            if (
                review.get("valid") is not True
                or solved != expected
                or candidates != [[answer] for answer in expected]
            ):
                raise ValueError(
                    "Logical review rejected candidate: "
                    + str(review.get("reason", ""))[:700]
                    + "; candidates=" + str(review.get("candidates"))[:240]
                )

            stage = "explanations"
            check = await _json_call(
                (
                    'Check six Russian explanations and six focus items against the Danish completed text and answer key. '
                    'Return JSON {"valid":true,"reason":""}. valid=false if an explanation is wrong, a focus item is misleading, '
                    'or a claimed grammar relation is unsupported.'
                ),
                json.dumps(data, ensure_ascii=False),
            )
            if check.get("valid") is not True:
                raise ValueError("Explanation review: " + str(check.get("reason", ""))[:700])
            return data

        except (ValueError, TypeError, KeyError) as error:
            last_error = error
            logger.warning("Opgave1 candidate rejected: stage=%s attempt=%d", stage, attempt + 1)

    raise ValueError("Opgave 1 kunne ikke kontrolleres.") from last_error

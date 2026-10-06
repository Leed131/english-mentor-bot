"""Validated word-bank gap exercises modelled on DU3 Modul 3 local-cohesion reading tasks."""
import json
import logging
import random
import re

from quiz_generator import _get_client, _model

logger = logging.getLogger(__name__)

RANK_ORDER = ("F", "E", "D", "C", "B", "A", "S")

RANK_GUIDANCE = {
    "F": (
        "Very easy A1. Six gaps. Use a balanced mix of common personal pronouns, simple conjunctions, "
        "negation, one easy verb and one easy content word. The local grammar should make answers clear."
    ),
    "E": (
        "Easy A1/A2. Prefer grammar words over vocabulary: personal/possessive pronouns, conjunctions, "
        "at/når, ikke/også, plus at most two verbs or nouns. Distractors may share a part of speech."
    ),
    "D": (
        "A2. Use pronoun case and possession (han/ham, hun/hende, de/dem, sin/sit/sine vs hans/hendes/deres), "
        "connectors and subordinate-clause starters, adverbs/negation, and at most two content words."
    ),
    "C": (
        "DU3 Modul 3 baseline. At least FOUR of the six answers must be grammar/cohesion words rather than content "
        "vocabulary. Strongly sample from: personal and possessive pronouns; men/og/for/fordi/selvom; at/når/da/mens; "
        "som/hvor/hvad/der; ikke/også/derfor; plus only one or two verb/adjective/noun items. Test word order and reference."
    ),
    "B": (
        "Strong B1. At least FIVE answers should be grammar/cohesion words. Use close same-class contrasts such as "
        "for vs fordi, men vs selvom, han vs ham, de vs dem, sin vs hendes/deres, som vs hvor/der, and at vs når/da. "
        "Meaning plus syntax must decide the answer."
    ),
    "A": (
        "B1+/B2. Mostly function/reference words with subtle same-class distractors. Some gaps should remain locally "
        "plausible until the learner checks clause type, antecedent, word order, or the one-use-only rule."
    ),
    "S": (
        "Extra challenge around B2. Almost all answers should test grammatical reference/cohesion rather than obvious "
        "vocabulary. Use natural close distractors and require precise pronoun reference, main/subordinate-clause word order, "
        "negation/adverb placement and global elimination while preserving one unique solution."
    ),
}

WORD_TYPE_RULES = """
The analysed training sheets show that this task primarily tests GRAMMAR WORDS IN CONTEXT, not random vocabulary.
Across a normal C-level task, distribute the six correct answers approximately like this:
- 1–2 personal/object pronouns: han, hun, de, vi, jeg, ham, hende, dem, jer.
- 1–2 possessive/reflexive possessives: sin, sit, sine, hans, hendes, deres, vores, min, din.
- 2–3 connectors / clause starters / relative words: og, men, for, fordi, selvom, at, når, da, mens, som, hvor, hvad, der.
- 0–2 adverbs/determiners: ikke, også, aldrig, allerede, derfor, hver.
- 0–2 inflected verbs or content words: har, tager, arbejder, holder, færdig, opgave, gæster, butik.
Do not mechanically satisfy every category in every task; keep the text natural. But at C-S grammar/reference words must dominate.
Important distinctions seen in source exercises:
- for + main-clause word order versus fordi + subordinate-clause word order;
- men + main clause versus selvom + subordinate clause;
- han/ham, hun/hende, de/dem;
- sin/sit/sine versus hans/hendes/deres according to the subject/owner;
- som/hvor/der/hvad according to reference and clause role;
- at/når/da/mens according to clause meaning;
- placement and meaning of ikke/også;
- a smaller number of verb/noun/adjective gaps to prevent pure rule matching.
Unused words should usually be plausible members of the SAME grammatical categories as the answers.
""".strip()


# Helpful reusable structures. These are learning priorities, not mandatory answers.
FOCUS_BANK = (
    ("F", "fordi", "потому что", "ledsætningskonjunktion"),
    ("F", "men", "но", "hovedsætningskonjunktion"),
    ("F", "og", "и", "hovedsætningskonjunktion"),
    ("F", "ikke", "не", "adverbium/negation"),
    ("F", "også", "тоже / также", "adverbium"),
    ("F", "han", "он", "personligt pronomen"),
    ("F", "hun", "она", "personligt pronomen"),
    ("F", "de", "они", "personligt pronomen"),
    ("E", "ham", "его / ему", "objektpronomen"),
    ("E", "hende", "её / ей", "objektpronomen"),
    ("E", "dem", "их / им", "objektpronomen"),
    ("E", "sin", "свой / своя", "refleksivt possessivt pronomen"),
    ("E", "sit", "своё", "refleksivt possessivt pronomen"),
    ("E", "sine", "свои", "refleksivt possessivt pronomen"),
    ("E", "hendes", "её", "possessivt pronomen"),
    ("E", "deres", "их", "possessivt pronomen"),
    ("E", "at", "что / чтобы", "ledsætningsindleder"),
    ("E", "når", "когда (обычно/в будущем)", "ledsætningsindleder"),
    ("E", "har travlt med at", "быть занятым тем, что…", "mønster"),
    ("E", "sin egen", "свой собственный / своя собственная", "mønster"),
    ("D", "for", "потому что / ведь", "hovedsætningskonjunktion"),
    ("D", "selvom", "хотя", "ledsætningskonjunktion"),
    ("D", "da", "когда (в прошлом)", "ledsætningsindleder"),
    ("D", "mens", "пока / в то время как", "ledsætningsindleder"),
    ("D", "som", "который / которая", "relativt pronomen"),
    ("D", "hvor", "где / в котором месте", "relativt/spørgeord"),
    ("D", "hvad", "что / то, что", "spørgeord"),
    ("D", "der", "который / там / формальное der", "relativt/formelt pronomen"),
    ("D", "derfor", "поэтому", "adverbium/forbinder"),
    ("D", "heller ikke", "тоже не", "negation"),
    ("D", "aldrig", "никогда", "adverbium"),
    ("D", "allerede", "уже", "adverbium"),
    ("C", "nemlig", "ведь / а именно", "adverbium/forbinder"),
    ("C", "på den måde", "таким образом", "mønster"),
    ("C", "siden", "с тех пор как / поскольку", "ledsætningsindleder"),
    ("C", "som regel", "как правило", "adverbium"),
    ("C", "til sidst", "в конце / наконец", "tidsadverbium"),
    ("B", "derimod", "напротив / зато", "adverbium/forbinder"),
    ("B", "alligevel", "всё же / несмотря на это", "adverbium"),
    ("B", "samtidig", "одновременно / в то же время", "adverbium"),
    ("A", "til gengæld", "зато / с другой стороны", "forbinder"),
    ("A", "efterhånden", "постепенно / со временем", "adverbium"),
    ("S", "ikke desto mindre", "тем не менее", "forbinder"),
)

SCHEMA = """Return JSON only:
{
  "title":"Danish title",
  "topic":"short Danish topic",
  "text_with_gaps":"One coherent Danish text containing exactly these six markers once each, in order: [[1]] [[2]] [[3]] [[4]] [[5]] [[6]]",
  "word_bank":["word1","word2","word3","word4","word5","word6","unused1","unused2","unused3","unused4"],
  "word_types":{"word1":"conjunction","word2":"adverb","word3":"verb","word4":"noun"},
  "answers":["word for gap1","word for gap2","word for gap3","word for gap4","word for gap5","word for gap6"],
  "explanations_ru":["why gap1 fits","... six explanations"],
  "focus":[
    {"phrase":"useful Danish word or short pattern connected to gap1","translation_ru":"Russian meaning","category":"short category"}
  ]
}
text_with_gaps must be ONE coherent Danish everyday text and must contain exactly six markers [[1]] through [[6]], each exactly once and in numerical order. Do not return a segments array for generated tasks.
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
focus.phrase should be a useful reusable word or short chunk actually represented by the completed text. focus.category must name the grammatical type, for example: personligt pronomen, objektpronomen, possessivt pronomen, refleksivt possessivt pronomen, hovedsætningskonjunktion, ledsætningskonjunktion, ledsætningsindleder, relativt pronomen, spørgeord, adverbium/negation, verbum, substantiv/adjektiv, or mønster.
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
    if isinstance(segments, list):
        if len(segments) != 7:
            raise ValueError("Нужно семь фрагментов текста для шести пропусков.")
        segments = [text(value, 850) for value in segments]
    else:
        template = raw.get("text_with_gaps")
        if not isinstance(template, str) or not template.strip():
            raise ValueError("Нужен цельный текст с шестью маркерами пропусков.")
        markers = re.findall(r"\[\[([1-6])\]\]", template)
        if markers != ["1", "2", "3", "4", "5", "6"]:
            raise ValueError("В тексте должны быть ровно маркеры [[1]] ... [[6]] по порядку.")
        pieces = re.split(r"\[\[[1-6]\]\]", template)
        if len(pieces) != 7:
            raise ValueError("Не удалось разделить текст на шесть пропусков.")
        # Leading/trailing text may be short, but every internal bridge must contain
        # enough context to make the exercise readable.
        if any(not piece.strip() for piece in pieces[1:6]):
            raise ValueError("Между пропусками должен быть текстовый контекст.")
        segments = [piece.strip() for piece in pieces]

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
    type_aliases = {
        "connector": "conjunction",
        "linker": "conjunction",
        "konjunktion": "conjunction",
        "adverbium": "adverb",
        "particle": "adverb",
        "auxiliary": "verb",
        "auxiliary verb": "verb",
        "modal": "verb",
        "modal verb": "verb",
        "substantiv": "noun",
        "noun phrase": "noun",
        "adjektiv": "adjective",
        "pronom": "pronoun",
        "determiner": "pronoun",
        "preposition phrase": "preposition",
    }
    normalized_type_keys = {key.casefold(): value for key, value in word_types.items()}
    if set(normalized_type_keys) != set(normalized_bank):
        raise ValueError("Тип должен быть указан для каждого слова из банка.")
    clean_types = {}
    for word in word_bank:
        raw_value = str(normalized_type_keys[word.casefold()]).strip().casefold()
        value = type_aliases.get(raw_value, raw_value)
        if value not in allowed_types:
            if "pronomen" in raw_value or "pronoun" in raw_value or "stedord" in raw_value or "possessiv" in raw_value:
                value = "pronoun"
            elif "konjunktion" in raw_value or "conjunction" in raw_value or "connector" in raw_value or "linker" in raw_value or "bindeord" in raw_value or "ledsætningsindleder" in raw_value:
                value = "conjunction"
            elif "adverb" in raw_value or "biord" in raw_value:
                value = "adverb"
            elif "negation" in raw_value or "negative" in raw_value or "nægt" in raw_value:
                value = "negation"
            elif "verbum" in raw_value or "verb" in raw_value or "udsagnsord" in raw_value or "hjælpeverbum" in raw_value or "auxiliary" in raw_value or "modal" in raw_value:
                value = "verb"
            elif "præposition" in raw_value or "preposition" in raw_value or "forholdsord" in raw_value:
                value = "preposition"
            elif "substantiv" in raw_value or "noun" in raw_value or "navneord" in raw_value:
                value = "noun"
            elif "adjektiv" in raw_value or "adjective" in raw_value or "tillægsord" in raw_value:
                value = "adjective"
            else:
                value = "noun"
        clean_types[word] = value

    answers = raw.get("answers")
    if not isinstance(answers, list) or len(answers) != 6:
        raise ValueError("Нужно шесть ответов.")
    answers = [text(value, 40) for value in answers]
    if len({value.casefold() for value in answers}) != 6:
        raise ValueError("Каждое слово можно использовать только один раз.")
    def infer_answer_type(word, index):
        category = ""
        focus_items = raw.get("focus")
        if isinstance(focus_items, list) and index < len(focus_items):
            item = focus_items[index]
            if isinstance(item, dict):
                category = str(item.get("category", "")).casefold()
        combined = category + " " + word.casefold()
        if any(key in combined for key in ("pronomen", "possessiv", "stedord")):
            return "pronoun"
        if any(key in combined for key in ("konjunktion", "ledsætningsindleder", "forbinder")):
            return "conjunction"
        if "negation" in combined or word.casefold() == "ikke":
            return "negation"
        if any(key in combined for key in ("adverb", "biord", "tidsadverb")):
            return "adverb"
        if any(key in combined for key in ("verbum", "udsagnsord")):
            return "verb"
        if any(key in combined for key in ("præposition", "forholdsord")):
            return "preposition"
        if any(key in combined for key in ("adjektiv", "tillægsord")):
            return "adjective"
        if any(key in combined for key in ("substantiv", "navneord")):
            return "noun"
        if word.casefold() in {"og", "men", "for", "fordi", "selvom", "at", "når", "da", "mens", "som", "hvis", "siden"}:
            return "conjunction"
        if word.casefold() in {"også", "meget", "aldrig", "allerede", "derfor", "nemlig", "alligevel", "samtidig", "derimod"}:
            return "adverb"
        if word.casefold() in {"han", "hun", "de", "ham", "hende", "dem", "sin", "sit", "sine", "hans", "hendes", "deres", "den", "det"}:
            return "pronoun"
        return "noun"

    # Repair a common model-format slip: the intended correct word is omitted
    # from the 10-word bank even though it is supplied in answers. Replace an
    # unused distractor with the missing answer, preserving ten unique words.
    lookup = {value.casefold(): value for value in word_bank}
    answer_keys = {value.casefold() for value in answers}
    for index, answer in enumerate(answers):
        key = answer.casefold()
        if key in lookup:
            continue
        if " " in answer:
            raise ValueError("Ответ для пропуска должен быть одним словом.")
        removable = next(
            (word for word in word_bank if word.casefold() not in answer_keys),
            None,
        )
        if removable is None:
            raise ValueError("Не удалось восстановить банк слов.")
        position = word_bank.index(removable)
        word_bank[position] = answer
        clean_types.pop(removable, None)
        raw_answer_type = normalized_type_keys.get(key)
        if raw_answer_type is not None:
            normalized = str(raw_answer_type).strip().casefold()
            answer_type = type_aliases.get(normalized, normalized)
            if answer_type not in allowed_types:
                answer_type = infer_answer_type(answer, index)
        else:
            answer_type = infer_answer_type(answer, index)
        clean_types[answer] = answer_type
        lookup = {value.casefold(): value for value in word_bank}

    if len({value.casefold() for value in word_bank}) != 10:
        raise ValueError("После восстановления банк слов содержит повторы.")
    answers = [lookup[value.casefold()] for value in answers]

    # Word-type balance is a generation target, not a reason to throw away an
    # otherwise coherent and uniquely solvable exercise. The independent logic
    # reviewer below remains the final correctness gate.

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
        # Metadata must not reject an otherwise good exercise. If the model
        # returns an abstract grammar label instead of a phrase from the text,
        # fall back to the actual answer for this gap.
        tokens = [token.strip(".,!?;:()“”\"'").casefold() for token in phrase.split()]
        if not any(token and token in completed for token in tokens):
            answer = answers[len(clean_focus)]
            known_translations = {p.casefold(): ru for _, p, ru, _ in FOCUS_BANK}
            phrase = answer
            translation = known_translations.get(answer.casefold(), translation)
            category = clean_types.get(answer, category)
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
                "Return the exercise text as ONE text_with_gaps string with exactly [[1]], [[2]], [[3]], [[4]], [[5]], [[6]] in that order. "
                "The bank must be a deliberate MIX of word types, not a random vocabulary list. At exam level C, prioritize "
                "connectors/conjunctions, adverbs/negation, verbs/auxiliaries and only a small number of content words. "
                + RANK_GUIDANCE[rank] + " " + unpredictability +
                WORD_TYPE_RULES + " "
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

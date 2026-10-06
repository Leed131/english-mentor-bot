"""Hand-reviewed word-bank gap exercises for Opgave 1 practice."""
import copy
import random

from opgave1_generator import validate_word_gap

EN_GAMMEL_DROEM = {
    "title": "En gammel drøm",
    "topic": "Arbejde og butik",
    "rank": "C",
    "segments": [
        (
            "Helle Paulsen har lige åbnet en butik med børnetøj. Det har hun drømt om, siden hun gik i lære. "
            "Så det er en gammel drøm, som nu er en realitet.\n\n"
            "Hun kender noget til børnetøj,"
        ),
        (
            "hun har arbejdet i en tøjbutik, der både har tøj til voksne og børn.\n\n"
            "Hun har"
        ),
        (
            "været mange år i en skobutik, og hun har kørt som sælger for et stort skofirma."
        ),
        (
            "i hendes butik er der kun tøj.\n\n"
            "Det er økotøj næsten det hele. Det betyder, at alt tøjet er lavet af økologisk bomuld, så der"
        ),
        (
            "er kemikalier i tøjet.\n\n"
            "Lige nu"
        ),
        (
            "hun travlt med at fylde sit lager. Hver mandag kører hun ud til forhandlere for at se deres showrooms "
            "og købe ind.\n\nHun synes, det er rigtig dejligt at have sin egen"
        ),
        ".",
    ],
    "word_bank": ["tøj", "butik", "men", "meget", "har", "ikke", "og", "arbejder", "også", "fordi"],
    "word_types": {
        "tøj": "noun",
        "butik": "noun",
        "men": "conjunction",
        "meget": "adverb",
        "har": "verb",
        "ikke": "negation",
        "og": "conjunction",
        "arbejder": "verb",
        "også": "adverb",
        "fordi": "conjunction",
    },
    "answers": ["fordi", "også", "men", "ikke", "har", "butik"],
    "explanations_ru": [
        "Здесь нужна причина: Хелле разбирается в детской одежде, потому что работала в магазине одежды. Derfor: fordi.",
        "После «Hun har» нужен наречный элемент перед «været»: она также много лет работала в обувном магазине. Поэтому også.",
        "Дальше идёт противопоставление: опыт связан с обувью, но в её собственном магазине продаётся только одежда. Поэтому men.",
        "Конструкция «der ikke er kemikalier» означает, что в одежде нет химикатов. Поэтому ikke.",
        "Устойчивое выражение «har travlt med at…» = быть занятым чем-то. Поэтому har.",
        "«have sin egen butik» = иметь свой собственный магазин. Поэтому butik.",
    ],
    "focus": [
        {"phrase": "fordi", "translation_ru": "потому что", "category": "forbinder"},
        {"phrase": "også", "translation_ru": "тоже / также", "category": "adverbium"},
        {"phrase": "men", "translation_ru": "но", "category": "forbinder"},
        {"phrase": "ikke", "translation_ru": "не", "category": "negation"},
        {"phrase": "har travlt med at", "translation_ru": "быть занятым тем, что…", "category": "mønster"},
        {"phrase": "sin egen butik", "translation_ru": "свой собственный магазин", "category": "mønster"},
    ],
}

NYT_FRITIDSJOB = {
    "title": "Et nyt fritidsjob",
    "topic": "Arbejde og hverdag",
    "rank": "C",
    "segments": [
        (
            "Noah er begyndt på et nyt fritidsjob i et supermarked. Han arbejder tre aftener om ugen. "
            "Han valgte jobbet,"
        ),
        (
            "det ligger tæt på hans skole. Han cykler derfor direkte derhen efter undervisningen.\n\n"
            "I begyndelsen kendte han"
        ),
        (
            "nogen af de andre medarbejdere, men nu taler han med dem hver dag. Han synes,"
        ),
        (
            "arbejdet er hyggeligt, selvom der tit er travlt.\n\n"
            "Noah"
        ),
        (
            "lært at fylde varer op og hjælpe kunderne. Han står"
        ),
        (
            "ved kassen, når en kollega holder pause. Lige nu sparer han penge op,"
        ),
        "han gerne vil købe en ny computer.",
    ],
    "word_bank": ["fordi", "ikke", "at", "har", "også", "men", "meget", "arbejder", "så", "butik"],
    "answers": ["fordi", "ikke", "at", "har", "også", "fordi"],
    # This reserve is intentionally not used: answers must be unique by format.
    "explanations_ru": ["x"] * 6,
    "focus": [{"phrase": "fordi", "translation_ru": "потому что", "category": "forbinder"}] * 6,
}

# Keep only validated unique-answer reserves.
RESERVES = [EN_GAMMEL_DROEM]


def reserve_opgave1(topic, rank="C", recent_titles=()):
    if rank != "C":
        return None
    normalized = topic.casefold()
    matches = []
    for raw in RESERVES:
        if raw["title"] in recent_titles:
            continue
        if any(key in normalized for key in ("arbejde", "butik", "tøj", "hverdag", "job")):
            matches.append(raw)
    if not matches:
        return None
    raw = copy.deepcopy(random.SystemRandom().choice(matches))
    return validate_word_gap(raw, rank="C")

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
        {"phrase": "fordi", "translation_ru": "потому что", "category": "ledsætningskonjunktion"},
        {"phrase": "også", "translation_ru": "тоже / также", "category": "adverbium"},
        {"phrase": "men", "translation_ru": "но", "category": "hovedsætningskonjunktion"},
        {"phrase": "ikke", "translation_ru": "не", "category": "adverbium/negation"},
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

FOERSTE_DAG_PAA_STUDIET = {
    "title": "Første dag på studiet",
    "topic": "Skole og uddannelse",
    "rank": "C",
    "segments": [
        "Maja er begyndt på en ny uddannelse. Hun var lidt nervøs,",
        "hun ikke kendte nogen i klassen. Læreren viste hende et lokale,",
        "de skulle have undervisning. Maja satte sig ved siden af Sara,",
        "også var ny. I pausen talte de sammen,",
        "bagefter gik de til kantinen. Efter pausen var Maja",
        "så nervøs længere. Nu har hun",
        "fået en ny ven på studiet.",
    ],
    "word_bank": ["fordi", "hvor", "som", "og", "ikke", "også", "men", "der", "har", "meget"],
    "word_types": {
        "fordi": "conjunction", "hvor": "pronoun", "som": "pronoun",
        "og": "conjunction", "ikke": "negation", "også": "adverb",
        "men": "conjunction", "der": "pronoun", "har": "verb", "meget": "adverb",
    },
    "answers": ["fordi", "hvor", "som", "og", "ikke", "også"],
    "explanations_ru": [
        "Здесь объясняется причина её нервозности: она никого не знала. Поэтому fordi.",
        "Речь идёт о месте, где будет проходить обучение. Поэтому hvor.",
        "Sara — человек, который тоже новенький. Поэтому относительное som.",
        "Два последовательных действия соединяются союзом og.",
        "Конструкция «ikke så nervøs længere» означает «уже не так нервничала».",
        "В конце добавляется ещё один результат: у неё также появился новый друг. Поэтому også.",
    ],
    "focus": [
        {"phrase": "fordi", "translation_ru": "потому что", "category": "ledsætningskonjunktion"},
        {"phrase": "hvor", "translation_ru": "где", "category": "relativt/spørgeord"},
        {"phrase": "som", "translation_ru": "который / которая", "category": "relativt pronomen"},
        {"phrase": "og", "translation_ru": "и", "category": "hovedsætningskonjunktion"},
        {"phrase": "ikke", "translation_ru": "не", "category": "adverbium/negation"},
        {"phrase": "også", "translation_ru": "также", "category": "adverbium"},
    ],
}

EN_SUNDERE_HVERDAG = {
    "title": "En sundere hverdag",
    "topic": "Sundhed og fritid",
    "rank": "C",
    "segments": [
        "Jonas vil bevæge sig mere,",
        "han sidder på kontor hele dagen. Han cykler nu til arbejde,",
        "det nogle gange regner. Om aftenen går han tur med sin nabo,",
        "bor i samme opgang. Før spiste han ofte fastfood,",
        "nu laver han mad hjemme. Han drikker",
        "sodavand hver dag. Han er",
        "begyndt at tage madpakke med.",
    ],
    "word_bank": ["fordi", "selvom", "som", "men", "ikke", "også", "og", "der", "har", "meget"],
    "word_types": {
        "fordi": "conjunction", "selvom": "conjunction", "som": "pronoun",
        "men": "conjunction", "ikke": "negation", "også": "adverb",
        "og": "conjunction", "der": "pronoun", "har": "verb", "meget": "adverb",
    },
    "answers": ["fordi", "selvom", "som", "men", "ikke", "også"],
    "explanations_ru": [
        "Он хочет больше двигаться, потому что весь день сидит в офисе. Поэтому fordi.",
        "Он едет на велосипеде, хотя иногда идёт дождь. Поэтому selvom.",
        "Нужна относительная связь с nabo: сосед, который живёт в том же подъезде. Поэтому som.",
        "Сравнивается прежняя и новая привычка в еде. Поэтому men.",
        "Он больше не пьёт газировку каждый день. Поэтому ikke.",
        "Добавляется ещё одна новая привычка: он также начал брать еду с собой. Поэтому også.",
    ],
    "focus": [
        {"phrase": "fordi", "translation_ru": "потому что", "category": "ledsætningskonjunktion"},
        {"phrase": "selvom", "translation_ru": "хотя", "category": "ledsætningskonjunktion"},
        {"phrase": "som", "translation_ru": "который / которая", "category": "relativt pronomen"},
        {"phrase": "men", "translation_ru": "но", "category": "hovedsætningskonjunktion"},
        {"phrase": "ikke", "translation_ru": "не", "category": "adverbium/negation"},
        {"phrase": "også", "translation_ru": "также", "category": "adverbium"},
    ],
}

NYE_NABOER = {
    "title": "Nye naboer",
    "topic": "Familie og bolig",
    "rank": "C",
    "segments": [
        "Sofia flyttede ind i en ny lejlighed sidste måned,",
        "hun kender allerede flere naboer. Naboen under hende hedder Peter,",
        "hjælper hende med affaldssortering. Hun spurgte ham,",
        "glascontaineren står. Han viste hende gården,",
        "hun ikke kendte området. Om aftenen er der",
        "meget støj. Sofia er",
        "glad for at bo der.",
    ],
    "word_bank": ["og", "som", "hvor", "fordi", "ikke", "derfor", "men", "også", "har", "meget"],
    "word_types": {
        "og": "conjunction", "som": "pronoun", "hvor": "pronoun",
        "fordi": "conjunction", "ikke": "negation", "derfor": "adverb",
        "men": "conjunction", "også": "adverb", "har": "verb", "meget": "adverb",
    },
    "answers": ["og", "som", "hvor", "fordi", "ikke", "derfor"],
    "explanations_ru": [
        "Здесь два факта о Софии соединяются союзом og.",
        "Peter — сосед, который помогает ей. Поэтому som.",
        "Она спрашивает, где находится контейнер для стекла. Поэтому hvor.",
        "Он показывает двор, потому что она не знала район. Поэтому fordi.",
        "Фраза «der ikke er meget støj» означает, что вечером не очень шумно.",
        "Из предыдущих положительных фактов следует вывод: поэтому Софии нравится там жить. Поэтому derfor.",
    ],
    "focus": [
        {"phrase": "og", "translation_ru": "и", "category": "hovedsætningskonjunktion"},
        {"phrase": "som", "translation_ru": "который / которая", "category": "relativt pronomen"},
        {"phrase": "hvor", "translation_ru": "где", "category": "spørgeord"},
        {"phrase": "fordi", "translation_ru": "потому что", "category": "ledsætningskonjunktion"},
        {"phrase": "ikke", "translation_ru": "не", "category": "adverbium/negation"},
        {"phrase": "derfor", "translation_ru": "поэтому", "category": "adverbium/forbinder"},
    ],
}

PAA_VEJ_TIL_ARBEJDE = {
    "title": "På vej til arbejde",
    "topic": "Transport og planer",
    "rank": "C",
    "segments": [
        "Emil tager normalt toget til arbejde,",
        "han bor langt fra kontoret. På stationen møder han en kollega,",
        "arbejder i samme afdeling. Toget er forsinket,",
        "de kan stadig nå det første møde. De skriver til chefen,",
        "de kommer lidt senere. Chefen er",
        "sur, og hun skriver",
        "til dem, at de bare skal tage det roligt.",
    ],
    "word_bank": ["fordi", "som", "men", "at", "ikke", "også", "og", "der", "har", "meget"],
    "word_types": {
        "fordi": "conjunction", "som": "pronoun", "men": "conjunction",
        "at": "conjunction", "ikke": "negation", "også": "adverb",
        "og": "conjunction", "der": "pronoun", "har": "verb", "meget": "adverb",
    },
    "answers": ["fordi", "som", "men", "at", "ikke", "også"],
    "explanations_ru": [
        "Причина поездки на поезде — он живёт далеко от офиса. Поэтому fordi.",
        "Нужна относительная связь: коллега, который работает в том же отделе. Поэтому som.",
        "Несмотря на задержку, они всё ещё успевают. Здесь противопоставление men.",
        "После «skriver til chefen» вводится содержание сообщения. Поэтому at.",
        "Начальница не сердится. Поэтому ikke.",
        "Она также пишет им ответ. Поэтому også.",
    ],
    "focus": [
        {"phrase": "fordi", "translation_ru": "потому что", "category": "ledsætningskonjunktion"},
        {"phrase": "som", "translation_ru": "который / которая", "category": "relativt pronomen"},
        {"phrase": "men", "translation_ru": "но", "category": "hovedsætningskonjunktion"},
        {"phrase": "at", "translation_ru": "что", "category": "ledsætningsindleder"},
        {"phrase": "ikke", "translation_ru": "не", "category": "adverbium/negation"},
        {"phrase": "også", "translation_ru": "также", "category": "adverbium"},
    ],
}

EN_HYGGELIG_WEEKEND = {
    "title": "En hyggelig weekend",
    "topic": "Familie og fritid",
    "rank": "C",
    "segments": [
        "Laura besøger sin søster,",
        "bor i Odense. De vil gå en tur,",
        "vejret er godt. Det regner om morgenen,",
        "senere bliver det tørt. De tager",
        "ud til en stor park. Laura har",
        "været der før. Hun vil",
        "gerne besøge et museum næste dag.",
    ],
    "word_bank": ["som", "hvis", "men", "derfor", "ikke", "også", "fordi", "og", "har", "meget"],
    "word_types": {
        "som": "pronoun", "hvis": "conjunction", "men": "conjunction",
        "derfor": "adverb", "ikke": "negation", "også": "adverb",
        "fordi": "conjunction", "og": "conjunction", "har": "verb", "meget": "adverb",
    },
    "answers": ["som", "hvis", "men", "derfor", "ikke", "også"],
    "explanations_ru": [
        "Сестра — человек, который живёт в Оденсе. Поэтому som.",
        "Прогулка зависит от условия: если погода хорошая. Поэтому hvis.",
        "Утром дождь, но позже становится сухо. Поэтому men.",
        "Поскольку погода улучшилась, они поэтому идут в парк. Поэтому derfor.",
        "Laura раньше там не была. Поэтому ikke.",
        "Она также хочет посетить музей. Поэтому også.",
    ],
    "focus": [
        {"phrase": "som", "translation_ru": "который / которая", "category": "relativt pronomen"},
        {"phrase": "hvis", "translation_ru": "если", "category": "ledsætningskonjunktion"},
        {"phrase": "men", "translation_ru": "но", "category": "hovedsætningskonjunktion"},
        {"phrase": "derfor", "translation_ru": "поэтому", "category": "adverbium/forbinder"},
        {"phrase": "ikke", "translation_ru": "не", "category": "adverbium/negation"},
        {"phrase": "også", "translation_ru": "также", "category": "adverbium"},
    ],
}

# Keep only validated unique-answer reserves.
RESERVES = [
    EN_GAMMEL_DROEM,
    FOERSTE_DAG_PAA_STUDIET,
    EN_SUNDERE_HVERDAG,
    NYE_NABOER,
    PAA_VEJ_TIL_ARBEJDE,
    EN_HYGGELIG_WEEKEND,
]


def reserve_opgave1(topic, rank="C", recent_titles=()):
    if rank != "C":
        return None
    normalized = topic.casefold()
    available = [raw for raw in RESERVES if raw["title"] not in recent_titles]
    if not available:
        return None

    topic_keywords = {
        "Arbejde og hverdag": ("arbejde", "job", "hverdag", "butik"),
        "Butik og indkøb": ("butik", "indkøb", "tøj"),
        "Skole og uddannelse": ("skole", "uddannelse", "stud"),
        "Sundhed og fritid": ("sundhed", "fritid", "sport"),
        "Familie og bolig": ("familie", "bolig", "nabo"),
        "Transport og planer": ("transport", "tog", "plan"),
    }
    keywords = ()
    for name, aliases in topic_keywords.items():
        if name.casefold() in normalized or any(alias in normalized for alias in aliases):
            keywords = aliases
            break

    matches = [
        raw for raw in available
        if keywords and any(alias in (raw["topic"] + " " + raw["title"]).casefold() for alias in keywords)
    ]
    raw = copy.deepcopy(random.SystemRandom().choice(matches or available))
    return validate_word_gap(raw, rank="C")

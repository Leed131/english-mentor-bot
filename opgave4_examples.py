"""Hand-reviewed DU3 Modul 3 Opgave 4 source exercise."""
import copy

from opgave4_generator import validate_text_match

JULEFROKOST = {
    "title": "Tre udlændinge fortæller om deres oplevelser med julefrokost i Danmark",
    "topic": "Jul og traditioner",
    "rank": "C",
    "profiles": [
        {
            "label": "A",
            "name": "Meng",
            "text": (
                "Min første julefrokost var på mit studiejob, og det var sådan en buffet, som lignede noget, man får til "
                "frokost i en kantine. Jeg husker, at der var forskellige sild, and og svinekød, og til sidst blev der "
                "serveret en ret flot risdessert. Sild er ikke noget, jeg selv køber, men jeg kan egentlig godt lide det. "
                "“Giv de fisk noget at svømme i,” sagde min sidemand, da jeg spiste sild, og skænkede snaps op til mig. "
                "Første gang var det meget sjovt, men jeg hørte joken rigtig mange gange den aften. Han syntes, at det blev "
                "mere og mere sjovt for hver gang, det blev sagt. Jeg ved godt, jeg lyder negativ lige nu, men hvor smager "
                "snaps bare dårligt. Jeg kunne ikke drikke ret meget af det. Vi har noget forfærdeligt brændevin hjemme i "
                "Kina, men den billige snaps fra Netto er endnu værre. Senere tog jeg over til en anden julefrokost, så det "
                "var en festlig aften."
            ),
        },
        {
            "label": "B",
            "name": "Hanna",
            "text": (
                "Jeg var lige kommet til Danmark for at arbejde, og derfor var min første julefrokost lidt påvirket af, at "
                "jeg var genert og opmærksom på ikke at gøre noget dumt overfor mine nye kollegaer. Jeg kan huske alle de "
                "her spil med kort og terninger, som skulle få folk til at drikke. Jeg husker også sangene, der har samme "
                "formål. Det er virkelig sat i system. Man kan ikke sammenligne en dansk julefrokost med en russisk. I mit "
                "hjemland er fejringer i forbindelse med julen som regel noget religiøst, og selvom vi russere også er "
                "kendt for at kunne drikke meget, vil jeg mene, at folk drikker endnu mere her i Danmark. Eller også var "
                "det bare den julefrokost, jeg var til. Det gode er, at man kan få lov at feste og drikke lige så meget, "
                "man vil, og når folk møder ind på arbejdet igen, er der ingen, der ser mærkeligt på hinanden eller skammer "
                "sig. Alt er bare, som det plejer at være. Det er meget cool."
            ),
        },
        {
            "label": "C",
            "name": "Ivan",
            "text": (
                "Min første julefrokost var med min kærestes familie. Jeg var på besøg fra Australien, og det var første "
                "gang, jeg skulle møde dem. Jeg var lidt nervøs og ville gerne gøre et godt indtryk, og alt gik fint, "
                "indtil en tallerken med sild landede foran mig. Det var karrysild, og jeg havde aldrig oplevet noget "
                "lignende. Alt var forkert ved den – smagen, konsistensen, udseendet, lugten. Jeg sad med munden fuld af "
                "sild, og der var ikke nogen vej udenom – jeg blev nødt til at spytte det hele ud i en serviet. Alt andet "
                "på bordet var lækkert. Den danske juleand er genial, og jeg er vild med jul i Danmark. Risalamande er en "
                "lækker dessert, og jeg elsker at kæmpe om at få en hel mandel, så jeg får mandelgaven. Min kærestes onkel "
                "sad desuden ved siden af mig og fortalte jokes, jeg ikke forstod, og hældte snaps i mit glas hele tiden. "
                "I Australien var jeg mest vant til sodavand til maden, så jeg blev så fuld, at jeg faktisk blev dårlig."
            ),
        },
    ],
    "questions": [
        {
            "question": "Hvem synes, sild smager godt?",
            "answer": "A",
            "explanation_ru": (
                "Meng говорит, что сам селёдку не покупает, но «jeg kan egentlig godt lide det» — в целом она ему нравится. "
                "Ivan, наоборот, настолько не любит каррисильд, что выплёвывает её."
            ),
        },
        {
            "question": "Hvem kan godt lide, at man har en leg til desserten?",
            "answer": "C",
            "explanation_ru": (
                "Ivan говорит о risalamande и что любит соревноваться за целый миндаль, чтобы получить mandelgaven. "
                "Это и есть игра/традиция, связанная с десертом."
            ),
        },
        {
            "question": "Hvem var til to julefrokoster samme aften?",
            "answer": "A",
            "explanation_ru": (
                "В конце текста Meng сказано: «Senere tog jeg over til en anden julefrokost» — позже он пошёл на другую "
                "рождественскую вечеринку в тот же вечер."
            ),
        },
        {
            "question": "Hvem drak for meget alkohol?",
            "answer": "C",
            "explanation_ru": (
                "Ivan рассказывает, что ему постоянно наливали snaps, и он «blev så fuld, at jeg faktisk blev dårlig» — "
                "настолько опьянел, что ему стало плохо."
            ),
        },
        {
            "question": "Hvem er vant til meget alkohol fra sit hjemland?",
            "answer": "B",
            "explanation_ru": (
                "Hanna говорит, что русские «er kendt for at kunne drikke meget». Это описывает привычный ей фон из родной страны."
            ),
        },
        {
            "question": "Hvem hørte den samme joke flere gange?",
            "answer": "A",
            "explanation_ru": (
                "Meng прямо говорит: «jeg hørte joken rigtig mange gange den aften». У Ivan тоже были шутки, но не сказано, "
                "что одна и та же шутка повторялась много раз."
            ),
        },
        {
            "question": (
                "Hvem kan godt lide, at kollegaerne opfører sig helt normalt tilbage på arbejdet efter en festlig julefrokost?"
            ),
            "answer": "B",
            "explanation_ru": (
                "Hanna считает хорошим, что после вечеринки коллеги возвращаются на работу и всё «som det plejer at være» — "
                "никто не смотрит странно и не стыдится."
            ),
        },
    ],
}


def reserve_opgave4(topic, rank="C", recent_titles=()):
    if rank != "C":
        return None
    normalized = topic.casefold()
    if not any(key in normalized for key in ("jul", "tradition", "fest", "arbejde")):
        return None
    if JULEFROKOST["title"] in recent_titles:
        return None
    return validate_text_match(copy.deepcopy(JULEFROKOST), rank="C")

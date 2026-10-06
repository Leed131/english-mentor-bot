"""Hand-reviewed DU3 Modul 3 Opgave 3 reserve exercises."""
import copy

from opgave3_generator import validate_text_gap

ADRIAN = {
    "title": "Adrians nye livsstil",
    "topic": "Sundhed og livsstil",
    "rank": "C",
    "paragraphs": [
        {
            "before": (
                "De sidste to år har Adrian arbejdet rigtig meget. Han har et job, som han er meget glad for, "
                "og selvom der tit er overarbejde, er det okay for Adrian. Så får han nemlig overarbejdsbetaling, "
                "og på den måde tjener han flere penge."
            ),
            "after": (
                "Han har blandt andet købt nogle lækre lædersofaer, et stort TV, en gamercomputer og noget tøj, "
                "men desværre er tøjet allerede blevet for småt, fordi han har taget 10 kg på."
            ),
            "options": {
                "A": "For han vil gerne have et nyt arbejde.",
                "B": "Han sparer alle pengene op.",
                "C": "Det er altid rart med lidt ekstra penge.",
                "D": "Men det er Adrian ligeglad med.",
            },
            "answer": "C",
            "explanation_ru": (
                "До пропуска говорится, что переработки дают Адриану больше денег. После пропуска перечисляются покупки. "
                "Поэтому «приятно иметь немного дополнительных денег» связывает обе части. Вариант B противоречит покупкам: "
                "он не откладывает все деньги."
            ),
        },
        {
            "before": (
                "Adrian er træt af, at han ikke får rørt sig nok. Han har ikke rigtig haft tid til at dyrke sport, "
                "siden han begyndte på sit nuværende job. Det er ikke så mærkeligt, at tøjet ikke passer, tænker Adrian. "
                "Han beslutter, at nu vil han tabe sig."
            ),
            "after": (
                "Han spillede nemlig også håndbold flere gange om ugen, da han var yngre, og han var meget vild med det. "
                "Han savner også sine gamle holdkammerater, og han ved, at nogle af dem stadig spiller i den gamle klub."
            ),
            "options": {
                "A": "Men Adrian synes, det er okay.",
                "B": "Derfor vil han i gang med at spille håndbold igen.",
                "C": "Derfor vil han ud at købe noget nyt tøj.",
                "D": "Men han er ikke så glad for at dyrke sport.",
            },
            "answer": "B",
            "explanation_ru": (
                "Адриан хочет похудеть, а дальше текст объясняет, что раньше он часто играл в гандбол и очень любил его. "
                "Поэтому логично, что он хочет снова начать играть. «nemlig» вводит объяснение этого решения."
            ),
        },
        {
            "before": (
                "Adrian ringer til sin gamle håndboldklub, hvor de fortæller ham, at han kan starte allerede ugen efter. "
                "Der er træning to gange om ugen fra kl. 17-19, og der er kamp i weekenden én gang om måneden."
            ),
            "after": (
                "Det er nemlig vigtigt for Adrian at komme i gang med at dyrke sport og få rørt sig, så han får det bedre "
                "fysisk og psykisk og taber sig lidt. Han håber, at hans chef kan forstå, at han ikke kan arbejde så meget "
                "over i fremtiden."
            ),
            "options": {
                "A": "Så han kan desværre ikke spille håndbold.",
                "B": "Så kan han ikke have så meget overarbejde.",
                "C": "For han kan ikke arbejde så meget.",
                "D": "Så må han arbejde noget mere.",
            },
            "answer": "B",
            "explanation_ru": (
                "Тренировки и матчи занимают время, поэтому Адриан уже не сможет иметь столько переработок. Следующее "
                "предложение объясняет, почему спорт важен, а последнее прямо говорит, что в будущем он не сможет так много "
                "работать сверхурочно."
            ),
        },
        {
            "before": (
                "Ugen efter finder Adrian sit gamle håndboldtøj frem. Han cykler til træning og føler sig allerede bedre "
                "tilpas, for han har savnet sine holdkammerater og glæder sig til at bevæge sig. Han synes, det er skønt at "
                "træne og få brugt sine muskler igen, selvom det også er hårdt, og i weekenden skal de spille kamp mod et andet hold."
            ),
            "after": (
                "For det bliver spændende at spille en rigtig kamp igen, især hvis de vinder."
            ),
            "options": {
                "A": "Det glæder han sig til.",
                "B": "Men Adrian vil ikke med, fordi han er nervøs.",
                "C": "Det har han heldigvis ikke tid til.",
                "D": "Derfor melder han sig syg på arbejdet.",
            },
            "answer": "A",
            "explanation_ru": (
                "Перед пропуском говорится о матче в выходные. После пропуска «For det bliver spændende…» объясняет, "
                "почему он этого ждёт. Поэтому подходит «Det glæder han sig til»."
            ),
        },
        {
            "before": "Et par dage efter spørger chefen, om han kan arbejde over.",
            "after": (
                "Så siger han til chefen, at han gerne vil tale med hende om overarbejde. De går ind på hendes kontor, "
                "hvor Adrian forklarer, at han er begyndt at spille håndbold for at leve sundere, og at han også skal spille "
                "i aften. Derfor er det svært for Adrian at tage så meget overarbejde, som han plejer. De aftaler, at Adrian "
                "i fremtiden højst skal arbejde over tre gange om måneden."
            ),
            "options": {
                "A": "Men Adrian siger, at han ikke har tid til at tale lige nu.",
                "B": "Og det vil Adrian rigtig gerne.",
                "C": "Adrian tænker sig om et kort øjeblik.",
                "D": "Adrian spørger, om han kan få fri i dag.",
            },
            "answer": "C",
            "explanation_ru": (
                "Начальница просит его переработать. Короткая пауза на размышление естественно ведёт к следующему действию: "
                "Адриан решает поговорить с ней о переработках. Вариант B не подходит, потому что дальше он хочет ограничить переработки."
            ),
        },
    ],
}


def reserve_opgave3(topic, rank="C", recent_titles=()):
    normalized = topic.casefold()
    if (
        "sundhed" not in normalized
        and "livsstil" not in normalized
        and "arbejde" not in normalized
    ):
        return None
    if ADRIAN["title"] in recent_titles:
        return None
    raw = copy.deepcopy(ADRIAN)
    raw["rank"] = rank
    return validate_text_gap(raw, rank=rank)

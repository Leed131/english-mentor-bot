from collections.abc import Mapping
from typing import Final

STUDY_SECTIONS: Final[tuple[str, ...]] = (
    "audio",
    "tests",
    "grammar",
    "writing",
    "verbs",
)

SECTION_LABELS: Final[dict[str, str]] = {
    "audio": "🎧 Аудио",
    "tests": "🧪 Тесты",
    "grammar": "📚 Грамматика",
    "writing": "✍️ Письмо",
    "verbs": "🔤 Глаголы",
}

DEFAULT_SECTION_TOTALS: Final[dict[str, int]] = {
    section: 10 for section in STUDY_SECTIONS
}

DEFAULT_SECTION_WEIGHTS: Final[dict[str, float]] = {
    section: 0.2 for section in STUDY_SECTIONS
}


def calculate_section_progress(completed_tasks: int, total_tasks: int) -> int:
    if total_tasks <= 0:
        return 0
    percentage = round((max(completed_tasks, 0) / total_tasks) * 100)
    return max(0, min(100, percentage))


def calculate_overall_progress(
    section_percentages: Mapping[str, int | float],
    weights: Mapping[str, int | float] | None = None,
) -> int:
    selected_weights = weights or DEFAULT_SECTION_WEIGHTS
    weighted_sum = 0.0
    total_weight = 0.0

    for section in STUDY_SECTIONS:
        weight = float(selected_weights.get(section, 0))
        if weight <= 0:
            continue
        value = max(0.0, min(100.0, float(section_percentages.get(section, 0))))
        weighted_sum += value * weight
        total_weight += weight

    if total_weight == 0:
        return 0
    return round(weighted_sum / total_weight)


def progress_bar(percentage: float, width: int = 10) -> str:
    bounded = max(0.0, min(100.0, float(percentage)))
    filled = round((bounded / 100) * width)
    return "█" * filled + "░" * (width - filled)


def format_progress_report(
    level: str,
    section_percentages: Mapping[str, int | float],
) -> str:
    overall = calculate_overall_progress(section_percentages)
    lines = [
        f"🇩🇰 Dansk — {level}",
        "",
        f"Прогресс плана {level}: {progress_bar(overall)} {overall}%",
        "",
    ]
    for section in STUDY_SECTIONS:
        value = round(float(section_percentages.get(section, 0)))
        lines.append(f"{SECTION_LABELS[section]}: {progress_bar(value)} {value}%")
    lines.extend(
        [
            "",
            (
                "Процент показывает прогресс внутри текущего учебного плана, а не "
                "долю всего датского языка, которую вы знаете."
            ),
        ]
    )
    return "\n".join(lines)

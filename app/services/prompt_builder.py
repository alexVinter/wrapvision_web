"""
Единая сборка final_prompt для стандартного сценария генерации.

Сборка текста и списка файлов зависит от двух независимых флагов: wrap_needed, wheels_needed.

Порядок изображений (не менять относительный порядок слотов):
  1 — фиксированный глобальный stand reference;
  2 — фото автомобиля пользователя;
  3 — фото-референс плёнки — только если wrap_needed = true;
  4 — фото-референс дисков — только если wheels_needed = true
      (путь в static для каталога или в uploads для загрузки).
"""

from __future__ import annotations

from pathlib import Path

_APP_DIR = Path(__file__).resolve().parent.parent
STAND_REFERENCE_IMAGE_PATH = _APP_DIR / "static" / "img" / "stand_reference.jpg"
"""Фиксированное изображение №1 — эталон итогового стенда (положите файл в static/img/)."""


def build_ordered_image_paths(
    car_image_path: Path,
    wrap_reference_path: Path | None,
    wheel_reference_path: Path | None,
    *,
    wrap_needed: bool,
    wheels_needed: bool,
) -> list[Path]:
    """
    Возвращает список путей в фиксированном порядке для мультимодального запроса.
    """
    ordered: list[Path] = [
        STAND_REFERENCE_IMAGE_PATH,
        car_image_path,
    ]
    if wrap_needed:
        if wrap_reference_path is None:
            raise ValueError("wrap_reference_path required when wrap_needed is true")
        ordered.append(wrap_reference_path)
    elif wrap_reference_path is not None:
        raise ValueError("wrap_reference_path must be omitted when wrap_needed is false")
    if wheels_needed:
        if wheel_reference_path is None:
            raise ValueError("wheel_reference_path required when wheels_needed is true")
        ordered.append(wheel_reference_path)
    elif wheel_reference_path is not None:
        raise ValueError("wheel_reference_path must be omitted when wheels_needed is false")
    return ordered


def _format_path_list(paths: list[Path]) -> str:
    return "\n".join(f"  {i + 1}. {p.as_posix()}" for i, p in enumerate(paths))


def _expected_path_count(*, wrap_needed: bool, wheels_needed: bool) -> int:
    return 2 + (1 if wrap_needed else 0) + (1 if wheels_needed else 0)


def _assemble_instruction_lines(*, wrap_needed: bool, wheels_needed: bool) -> list[str]:
    """Одна точка сборки текстовых инструкций по флагам (без дублирования крупных шаблонов)."""
    lines: list[str] = [
        "TASK: Car visualization for professional wrap / stand preview (Nano Banana API-ready).",
        "",
        "FIXED MULTIMODAL IMAGE ORDER - never reorder when attaching images to the API:",
        (
            "1) Global stand reference — copy ONLY framing, lighting, backdrop, floor, studio layout, pedestal, "
            "and empty negative space intended for placing a hero vehicle. Treat any incidental car silhouette in "
            "reference 1 as background noise: DO NOT use it as the main subject vehicle, DO NOT recolor its body "
            "to match wraps, DO NOT preserve its silhouette as the hero car."
        ),
        (
            "VEHICLE IDENTITY (applies below): The hero motor vehicle MUST be taken exclusively from reference 2 "
            "(exact body shell, proportions, windows, headlights, grille, door count, silhouette). Compose that "
            "vehicle INTO the scene template from reference 1, replacing any car that appears on the stand mockup."
        ),
    ]

    if wrap_needed:
        lines.extend(
            [
                "2) User vehicle — this is the ONLY source for the main car body and identity in the final image; place it in the stand from reference 1.",
                "3) Wrap / vinyl reference — CHANGE the visible body wrap/paint treatment to match color, gloss, and material from this image across appropriate body panels on the reference-2 vehicle only.",
            ]
        )
    else:
        lines.append(
            "2) User vehicle — DO NOT change body color, existing wrap film, gloss, material, or livery. "
            "Keep the exact visible body appearance from this image; do not invent a new wrap or recolor panels."
        )

    wheel_idx = 3 + (1 if wrap_needed else 0)
    if wheels_needed:
        lines.append(
            f"{wheel_idx}) Wheel reference — CHANGE only wheels / rims / tires to match design and finish from this image; "
            "keep all body surfaces consistent with the rules above."
        )

    lines.append("")
    if wrap_needed and wheels_needed:
        lines.append(
            "Output: one cohesive stand-style render following reference 1, applying the new wrap from reference 3 "
            f"and new wheels from reference {wheel_idx}, while respecting vehicle identity from reference 2."
        )
    elif wrap_needed:
        lines.append(
            "Output: one cohesive stand-style render following reference 1, applying the new wrap from reference 3 "
            "to the vehicle from reference 2; keep wheels as on reference 2 unless they must be minimally adjusted for realism."
        )
    elif wheels_needed:
        lines.append(
            f"Output: one cohesive stand-style render following reference 1, keeping the vehicle body exactly as in reference 2 "
            f"(no wrap or color change), with wheels replaced per reference {wheel_idx}."
        )
    else:
        lines.append(
            "Output: one cohesive stand-style render following reference 1 while preserving reference 2 exactly."
        )

    return lines


def build_final_prompt(
    *,
    wrap_needed: bool,
    wheels_needed: bool,
    ordered_image_paths: list[Path],
) -> str:
    """Собирает final_prompt в одном месте."""
    expected = _expected_path_count(wrap_needed=wrap_needed, wheels_needed=wheels_needed)
    if len(ordered_image_paths) != expected:
        raise ValueError(
            f"ordered_image_paths length {len(ordered_image_paths)} does not match "
            f"wrap_needed={wrap_needed} and wheels_needed={wheels_needed} (expected {expected} paths)"
        )

    body_lines = _assemble_instruction_lines(
        wrap_needed=wrap_needed, wheels_needed=wheels_needed
    )
    body = "\n".join(body_lines).strip()

    paths_block = "IMAGE FILES (same order as above):\n" + _format_path_list(
        ordered_image_paths
    )

    parts = [body, "", paths_block]

    return "\n".join(parts).strip()

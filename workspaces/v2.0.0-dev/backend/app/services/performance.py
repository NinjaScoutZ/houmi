from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PerformanceSettings:
    profile: str
    preview_width: int
    typesetting_candidates: int
    ocr_workers: int
    prefer_gpu: bool


PROFILES = {
    "eco": PerformanceSettings("eco", 800, 24, 1, False),
    "balanced": PerformanceSettings("balanced", 1200, 40, 2, True),
    "performance": PerformanceSettings("performance", 1800, 64, 4, True),
}


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        return max(minimum, min(maximum, int(value)))
    except (TypeError, ValueError):
        return default


def resolve_performance_settings(settings: dict | None) -> PerformanceSettings:
    settings = settings or {}
    profile = str(settings.get("performance_profile", "balanced")).lower()
    if profile in PROFILES:
        return PROFILES[profile]

    custom = settings.get("performance_custom")
    custom = custom if isinstance(custom, dict) else {}
    return PerformanceSettings(
        profile="custom",
        preview_width=_bounded_int(custom.get("preview_width"), 1200, 600, 2400),
        typesetting_candidates=_bounded_int(custom.get("typesetting_candidates"), 40, 12, 96),
        ocr_workers=_bounded_int(custom.get("ocr_workers"), 2, 1, 4),
        prefer_gpu=bool(custom.get("prefer_gpu", True)),
    )

"""Semantic roles are Font Templates.

Each text template may declare a Thai ``semantic_tag`` (e.g. ``ตัวละครพูด``).
AI translation can append ``{tag}`` at the end of a line; we strip it and set
``semantic_role = template_id``. Adding a new Font Template with a
``semantic_tag`` automatically registers a new semantic role — no separate
role registry.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Optional


def build_tag_map(templates: dict[str, dict[str, Any]] | None = None) -> dict[str, str]:
    """Return ``{Thai-label: template_id}`` from templates that declare *semantic_tag*.

    Built-in packs are always merged first so default AI tags keep working when a
    project only defines a subset of Font Templates. Project templates override
    the same *semantic_tag* label (last write wins).
    """
    from app.services.text_templates import _BUILTIN_TEMPLATES

    merged: dict[str, dict[str, Any]] = {
        str(k): dict(v) for k, v in _BUILTIN_TEMPLATES.items()
    }
    if templates:
        for k, v in templates.items():
            if isinstance(v, dict):
                merged[str(k)] = v
    mapping: dict[str, str] = {}
    for tid, tmpl in merged.items():
        tag = str(tmpl.get("semantic_tag") or "").strip()
        if tag:
            mapping[tag] = str(tid)
    return mapping


def build_role_labels(templates: dict[str, dict[str, Any]] | None = None) -> dict[str, str]:
    """``{template_id: human label}`` — prefers semantic_tag, then name, then id."""
    from app.services.text_templates import _BUILTIN_TEMPLATES

    merged: dict[str, dict[str, Any]] = {
        str(k): dict(v) for k, v in _BUILTIN_TEMPLATES.items()
    }
    if templates:
        for k, v in templates.items():
            if isinstance(v, dict):
                merged[str(k)] = v
    labels: dict[str, str] = {}
    for tid, tmpl in merged.items():
        if not isinstance(tmpl, dict):
            continue
        labels[str(tid)] = (
            str(tmpl.get("semantic_tag") or "").strip()
            or str(tmpl.get("name") or "").strip()
            or str(tid)
        )
    return labels


def get_role_label(
    role: str | None,
    templates: Mapping[str, dict[str, Any]] | None = None,
) -> str:
    if not role:
        return ""
    labels = build_role_labels(dict(templates) if templates else None)
    if role in labels:
        return labels[role]
    # Legacy abstract names → template labels
    legacy = {
        "dialogue": labels.get("bubble", "ตัวละครพูด"),
        "narration": labels.get("narration", "คำบรรยาย"),
        "thought": labels.get("thought", "คิดในใจ"),
        "system": labels.get("system", "ระบบพูด"),
        "emphasis": labels.get("emphasis", "ตะโกน"),
        "sfx": labels.get("sfx", "เสียงเอฟเฟกต์"),
    }
    return legacy.get(str(role), str(role))


class _RoleLabelsProxy(dict):
    """Backward-compatible ``SEMANTIC_ROLE_LABELS[role]``."""

    def __getitem__(self, key: str) -> str:  # type: ignore[override]
        return get_role_label(key)

    def get(self, key: str, default=None):  # type: ignore[override]
        label = get_role_label(key)
        return label if label else default


SEMANTIC_ROLE_LABELS = _RoleLabelsProxy()


def _compile_tag_regex(tag_map: dict[str, str]) -> re.Pattern[str] | None:
    if not tag_map:
        return None
    escaped = "|".join(re.escape(t) for t in sorted(tag_map, key=len, reverse=True))
    return re.compile(rf"\{{\s*({escaped})\s*\}}\s*$")


@dataclass(frozen=True)
class TranslationAnnotation:
    text: str
    # template_id — same identity as Font Template / semantic role
    semantic_role: Optional[str] = None
    semantic_tag: Optional[str] = None  # e.g. "{คิดในใจ}"
    semantic_label: Optional[str] = None  # e.g. "คิดในใจ"
    warning: Optional[str] = None


def parse_translation_annotation(
    value: str,
    tag_map: dict[str, str] | None = None,
    templates: Mapping[str, dict[str, Any]] | None = None,
) -> TranslationAnnotation:
    """Strip semantic tags at the *end* of a translation string.

    *tag_map* maps Thai labels → template IDs. When ``None``, built from
    *templates* (merged with builtins) or default built-ins alone.
    """
    if tag_map is None:
        tag_map = build_tag_map(dict(templates) if templates else None)
    regex = _compile_tag_regex(tag_map)
    cleaned = (value or "").rstrip()
    if not regex:
        return TranslationAnnotation(text=cleaned)

    matches: list[str] = []
    while True:
        match = regex.search(cleaned)
        if not match:
            break
        matches.append(match.group(1))
        cleaned = cleaned[: match.start()].rstrip()

    if not matches:
        return TranslationAnnotation(text=cleaned)

    label = matches[0]  # right-most / final tag is authoritative
    return TranslationAnnotation(
        text=cleaned,
        semantic_role=tag_map[label],
        semantic_tag=f"{{{label}}}",
        semantic_label=label,
        warning="พบป้ายประเภทซ้ำหลายป้าย ใช้ป้ายสุดท้าย" if len(matches) > 1 else None,
    )


_ANY_BRACE_TAG_RE = re.compile(r"\{[^{}]+\}\s*$")


def strip_translation_semantic_tags(value: str) -> str:
    """Presentation/layout safety net for legacy records that retained a tag."""
    cleaned = (value or "").rstrip()
    while _ANY_BRACE_TAG_RE.search(cleaned):
        cleaned = _ANY_BRACE_TAG_RE.sub("", cleaned).rstrip()
    return cleaned

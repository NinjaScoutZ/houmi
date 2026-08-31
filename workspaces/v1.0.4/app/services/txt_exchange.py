import re
import math
import unicodedata
from difflib import SequenceMatcher
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.models.all_models import Project, TextBlock
from app.services.layout_region import get_effective_layout_region, refresh_block_layout_regions
from app.services.typesetting import compute_block_typesetting
from app.services.semantic_tags import (
    TranslationAnnotation,
    build_tag_map,
    parse_translation_annotation,
)


HOUMI_LAYOUT_RE = re.compile(
    r"^\[\[(?:HOUMI_LAYOUT|SMART_BALLOON_SPATIAL)\s+shape=([a-z_]+)\s+"
    r"(?:aspect=[0-9.]+\s+w=\d+\s+h=\d+\s+)?"
    r"target_lines=(\d+)\s+max_lines=(\d+)"
    r"(?:\s+pattern=[A-Za-z-]+)?\]\]$"
)


def _parse_layout_hint(value: str) -> Optional[dict]:
    match = HOUMI_LAYOUT_RE.fullmatch(value.strip())
    if not match:
        from app.services.typesetting.smart_balloon_context import parse_smart_balloon_spatial_tag
        return parse_smart_balloon_spatial_tag(value)
    target = max(1, int(match.group(2)))
    maximum = max(target, int(match.group(3)))
    return {"shape": match.group(1), "target_lines": target, "max_lines": maximum}


def _format_layout_hint(hint: dict) -> str:
    if "ai_tag" in hint:
        return hint["ai_tag"]
    return (
        f"[[HOUMI_LAYOUT shape={hint['shape']} "
        f"target_lines={hint['target_lines']} max_lines={hint['max_lines']}]]"
    )


def _without_line_breaks(value: str) -> str:
    return (value or "").replace("\r\n", "\n").replace("\r", "\n").replace("\n", "")


def _canonical_ai_layout_text(existing: str, preferred: str) -> str:
    """Recover the exact pre-break translation when the imported text matches it."""
    existing_text = parse_translation_annotation(existing or "").text
    if existing_text and re.sub(r"\s+", "", existing_text) == re.sub(r"\s+", "", preferred):
        return _without_line_breaks(existing_text)
    return _without_line_breaks(preferred)


def _apply_semantic_template(block: TextBlock, template_id: Optional[str], settings: dict) -> Optional[str]:
    """Apply the template identified by the semantic tag directly."""
    from app.services.text_templates import apply_default_text_template, apply_template_by_id

    if not template_id:
        apply_default_text_template(block, settings)
        return None

    if apply_template_by_id(block, template_id, settings):
        return template_id

    apply_default_text_template(block, settings)
    return None


@dataclass(frozen=True)
class ImportRecord:
    translation: str
    line_number: int
    source_text: Optional[str] = None
    block_id: Optional[str] = None
    bubble_index: Optional[int] = None
    layout_hint: Optional[dict] = None


def _ordered_blocks(project: Project) -> list[TextBlock]:
    return [
        block
        for page in sorted(project.pages, key=lambda item: item.page_number)
        for block in sorted(page.text_blocks, key=lambda item: item.block_index)
    ]


def _normalize_source(value: str) -> str:
    return "".join(value.replace("\ufeff", "").split())


def _find_source_match(
    source_text: str,
    blocks: list[TextBlock],
    used_block_ids: set[str],
) -> tuple[Optional[TextBlock], float]:
    normalized = _normalize_source(source_text)
    if not normalized:
        return None, 0.0

    candidates = [block for block in blocks if block.id not in used_block_ids]
    exact = [block for block in candidates if _normalize_source(block.source_text or "") == normalized]
    if exact:
        return exact[0], 1.0

    scored = sorted(
        [
            (
                SequenceMatcher(
                    None,
                    normalized,
                    _normalize_source(block.source_text or ""),
                    autojunk=False,
                ).ratio(),
                block,
            )
            for block in candidates
            if block.source_text
        ],
        key=lambda item: item[0],
    )
    if not scored:
        return None, 0.0
    best_score, best_block = scored[-1]
    second_score = scored[-2][0] if len(scored) > 1 else 0.0
    if best_score >= 0.72 and (best_score - second_score >= 0.06 or best_score >= 0.90):
        return best_block, best_score
    return None, best_score


def export_to_txt(project_id: str, db: Session, mode: str = "ocr") -> str:
    """Export a stable, human-editable OCR/translation exchange document."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError("Project not found")
    if mode not in {"ocr", "translation", "both", "ai_layout"}:
        raise ValueError(f"Unsupported TXT export mode: {mode}")

    lines: list[str] = []
    if mode == "ai_layout":
        for block in _ordered_blocks(project):
            source_text = (block.source_text or "").replace("\r", " ").replace("\n", " ")
            lines.append(source_text)
            lines.append(_format_layout_hint(_layout_hint_for_block(block, project.settings or {})))
            annotation = parse_translation_annotation(block.translation or "")
            if annotation.text:
                # This mode is the input for the user's line-break + semantic
                # role prompt. Give the model one untouched Thai paragraph so
                # it, rather than a prior local layout, chooses every break and
                # the final role tag. A line break is converted to one ordinary
                # space only to keep words separated; no content is rewritten.
                lines.append(annotation.text.replace("\r\n", " ").replace("\n", " "))
            # Intentionally omit an existing semantic tag. The hand-off prompt
            # is responsible for classifying it afresh and returns one tag as
            # the final line, which the importer will store.
            lines.append("")
        return "\n".join(lines)

    if mode == "ocr":
        for block in _ordered_blocks(project):
            source_text = (block.source_text or "").replace("\r", " ").replace("\n", " ").strip()
            lines.append(f"//{source_text}")
        return "\n".join(lines)

    for bubble_index, block in enumerate(_ordered_blocks(project), start=1):
        lines.append(f"# Bubble {bubble_index}")
        if mode in {"ocr", "both"}:
            source_text = (block.source_text or "").replace("\r", " ").replace("\n", " ")
            lines.append(f"[คำต้นฉบับ]: {source_text}")
        if mode in {"translation", "both"}:
            # Never re-export an import-only semantic annotation as dialogue.
            lines.append(f"[คำแปลไทย]: {parse_translation_annotation(block.translation or '').text}")
        lines.append("")
    return "\n".join(lines)


def _parse_labeled(lines: list[str]) -> list[ImportRecord]:
    records: list[ImportRecord] = []
    current_id: Optional[str] = None
    current_bubble: Optional[int] = None
    source_lines: list[str] = []
    translation_lines: list[str] = []
    layout_hint: Optional[dict] = None
    phase: Optional[str] = None
    start_line = 1

    def finish() -> None:
        nonlocal current_id, current_bubble, source_lines, translation_lines, layout_hint, phase, start_line
        if current_id is not None or current_bubble is not None:
            records.append(
                ImportRecord(
                    translation="\n".join(translation_lines).strip(),
                    source_text="\n".join(source_lines).strip() or None,
                    block_id=current_id,
                    bubble_index=current_bubble,
                    layout_hint=layout_hint,
                    line_number=start_line,
                )
            )
        current_id = None
        current_bubble = None
        source_lines = []
        translation_lines = []
        layout_hint = None
        phase = None

    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("# ID:"):
            finish()
            current_id = stripped.split(":", 1)[1].strip()
            start_line = line_number
        elif re.match(r"^#\s*Bubble\s+\d+\s*:?.*$", stripped, flags=re.IGNORECASE):
            finish()
            match = re.search(r"\d+", stripped)
            current_bubble = int(match.group()) if match else None
            start_line = line_number
        elif stripped.startswith("[คำต้นฉบับ]:"):
            phase = "source"
            source_lines = [line.split(":", 1)[1].strip()]
        elif stripped.startswith("[คำแปลไทย]:") or stripped.startswith("[คำแปล]:"):
            phase = "translation"
            translation_lines = [line.split(":", 1)[1].strip()]
        elif _parse_layout_hint(stripped) is not None:
            layout_hint = _parse_layout_hint(stripped)
        elif current_id is not None or current_bubble is not None:
            if not stripped or stripped.startswith("#"):
                continue
            if phase == "translation":
                # A physical newline in the translation is an AI/manual line-break
                # preference. Keep it; a final {semantic tag} is stripped later.
                translation_lines.append(line)
            elif phase == "source":
                # OCR-only exports are commonly translated by adding the Thai line
                # directly below the labelled source line.
                phase = "translation"
                translation_lines.append(line)

    finish()
    return records


def _parse_tsv(lines: list[str]) -> list[ImportRecord]:
    records: list[ImportRecord] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        columns = line.rstrip("\r\n").split("\t")
        if len(columns) >= 4:
            records.append(
                ImportRecord(
                    block_id=columns[1].strip(),
                    source_text=columns[2].strip() or None,
                    translation="\t".join(columns[3:]).replace("\\n", "\n").strip(),
                    line_number=line_number,
                )
            )
        elif len(columns) == 2:
            records.append(
                ImportRecord(
                    source_text=columns[0].strip() or None,
                    translation=columns[1].replace("\\n", "\n").strip(),
                    bubble_index=len(records) + 1,
                    line_number=line_number,
                )
            )
        else:
            raise ValueError(f"Line {line_number}: expected 2 or 4 TSV columns")
    return records


def _parse_alternating(lines: list[str]) -> list[ImportRecord]:
    paragraphs: list[tuple[int, list[str]]] = []
    current: list[str] = []
    start_line = 1
    for line_number, line in enumerate(lines + [""], start=1):
        if line.strip():
            if not current:
                start_line = line_number
            current.append(line.strip())
        elif current:
            paragraphs.append((start_line, current))
            current = []

    if paragraphs and all(len(parts) == 1 for _, parts in paragraphs):
        flattened = [(line_number, parts[0]) for line_number, parts in paragraphs]
        if len(flattened) % 2:
            raise ValueError("Plain text import must contain source/translation pairs")
        paragraphs = [
            (flattened[index][0], [flattened[index][1], flattened[index + 1][1]])
            for index in range(0, len(flattened), 2)
        ]

    records: list[ImportRecord] = []
    for line_number, parts in paragraphs:
        if len(parts) < 2:
            raise ValueError(
                f"Line {line_number}: each paragraph must contain source text followed by translation"
            )
        layout_hint = _parse_layout_hint(parts[1]) if len(parts) >= 2 else None
        translation_start = 2 if layout_hint is not None else 1
        records.append(
            ImportRecord(
                source_text=parts[0],
                translation="\n".join(parts[translation_start:]).strip(),
                bubble_index=len(records) + 1,
                line_number=line_number,
                layout_hint=layout_hint,
            )
        )
    return records


def _parse_slash_slash(lines: list[str]) -> list[ImportRecord]:
    def _is_thai(text: str) -> bool:
        return bool(re.search(r"[\u0e00-\u0e7f]", text or ""))

    # Separate non-empty lines into paragraph blocks (separated by blank lines)
    paragraphs: list[tuple[int, list[tuple[int, str]]]] = []
    current_p: list[tuple[int, str]] = []
    p_start_line = 1

    for idx, line in enumerate(lines + [""], start=1):
        if line.strip():
            if not current_p:
                p_start_line = idx
            current_p.append((idx, line))
        elif current_p:
            paragraphs.append((p_start_line, current_p))
            current_p = []

    records: list[ImportRecord] = []

    for p_start, p_lines in paragraphs:
        all_slash = all(item[1].strip().startswith("//") for item in p_lines)

        # Case A: Paragraph has exactly 2 lines (e.g. //ENGLISH_SOURCE \n //THAI_TRANSLATION)
        if len(p_lines) == 2:
            l1_raw = p_lines[0][1].strip()
            l2_raw = p_lines[1][1].strip()
            s1 = l1_raw[2:].strip() if l1_raw.startswith("//") else l1_raw
            s2 = l2_raw[2:].strip() if l2_raw.startswith("//") else l2_raw
            records.append(
                ImportRecord(
                    source_text=s1,
                    translation=s2,
                    bubble_index=len(records) + 1,
                    line_number=p_start,
                )
            )
            continue

        # Case B: Paragraph has 3 lines with a layout hint in middle
        if len(p_lines) == 3 and _parse_layout_hint(p_lines[1][1].strip()) is not None:
            l1_raw = p_lines[0][1].strip()
            l3_raw = p_lines[2][1].strip()
            s1 = l1_raw[2:].strip() if l1_raw.startswith("//") else l1_raw
            s3 = l3_raw[2:].strip() if l3_raw.startswith("//") else l3_raw
            records.append(
                ImportRecord(
                    source_text=s1,
                    translation=s3,
                    bubble_index=len(records) + 1,
                    line_number=p_start,
                    layout_hint=_parse_layout_hint(p_lines[1][1].strip()),
                )
            )
            continue

        # Case C: Continuous // pairs without blank lines (alternating source non-Thai // and translation Thai //)
        if len(p_lines) > 2 and all_slash:
            is_alternating_lang = True
            for i in range(0, len(p_lines), 2):
                if i + 1 < len(p_lines):
                    t1 = p_lines[i][1].strip()[2:].strip()
                    t2 = p_lines[i + 1][1].strip()[2:].strip()
                    if _is_thai(t1) or not _is_thai(t2):
                        is_alternating_lang = False
                        break
                else:
                    is_alternating_lang = False

            if is_alternating_lang:
                for i in range(0, len(p_lines), 2):
                    if i + 1 < len(p_lines):
                        s1 = p_lines[i][1].strip()[2:].strip()
                        s2 = p_lines[i + 1][1].strip()[2:].strip()
                        records.append(
                            ImportRecord(
                                source_text=s1,
                                translation=s2,
                                bubble_index=len(records) + 1,
                                line_number=p_lines[i][0],
                            )
                        )
                continue

        # Case D: Fallback line-by-line accumulator for OCR-only // or mixed lines
        curr_src: Optional[str] = None
        curr_trans: list[str] = []
        curr_start = p_start
        hint: Optional[dict] = None

        for l_num, l_raw in p_lines:
            stripped = l_raw.strip()
            if _parse_layout_hint(stripped) is not None:
                hint = _parse_layout_hint(stripped)
            elif stripped.startswith("//"):
                clean = stripped[2:].strip()
                if curr_src is not None and not curr_trans and _is_thai(clean) and not _is_thai(curr_src):
                    curr_trans.append(clean)
                else:
                    if curr_src is not None or curr_trans:
                        records.append(
                            ImportRecord(
                                source_text=curr_src,
                                translation="\n".join(curr_trans).strip(),
                                bubble_index=len(records) + 1,
                                line_number=curr_start,
                                layout_hint=hint,
                            )
                        )
                    curr_src = clean
                    curr_trans = []
                    curr_start = l_num
                    hint = None
            else:
                if curr_src is not None:
                    curr_trans.append(stripped)
                else:
                    curr_trans.append(stripped)

        if curr_src is not None or curr_trans:
            records.append(
                ImportRecord(
                    source_text=curr_src,
                    translation="\n".join(curr_trans).strip(),
                    bubble_index=len(records) + 1,
                    line_number=curr_start,
                    layout_hint=hint,
                )
            )

    return records


def parse_translation_txt(txt_content: str) -> tuple[str, list[ImportRecord]]:
    lines = txt_content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    meaningful = [line for line in lines if line.strip()]
    if not meaningful:
        raise ValueError("Translation file is empty")
    if any(
        line.strip().startswith(("# Bubble", "# ID:", "[คำต้นฉบับ]:", "[คำแปลไทย]:", "[คำแปล]:"))
        for line in meaningful
    ):
        return "bubble", _parse_labeled(lines)
    if any(line.strip().startswith("//") for line in meaningful):
        return "slash_slash", _parse_slash_slash(lines)
    if any("\t" in line for line in meaningful):
        return "tsv", _parse_tsv(lines)
    return "alternating", _parse_alternating(lines)


def validate_txt_preview(project_id: str, txt_content: str, db: Session) -> dict:
    """Validate translation file without importing. Returns a preview of what would happen."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError("Project not found")

    ordered_blocks = _ordered_blocks(project)
    block_map = {block.id: block for block in ordered_blocks}
    try:
        detected_format, records = parse_translation_txt(txt_content)
    except ValueError as exc:
        return {
            "success": False,
            "format": "unknown",
            "preview_records": [],
            "summary": {"ok": 0, "warning": 0, "error": 1, "total": 0},
            "errors": [str(exc)],
        }

    preview_records: list[dict] = []
    used_block_ids: set[str] = set()

    tag_map = build_tag_map((project.settings or {}).get("text_templates") or None)
    for sequential_index, record in enumerate(records, start=1):
        annotation = parse_translation_annotation(record.translation, tag_map)
        entry: dict = {
            "line_number": record.line_number,
            "source_text": record.source_text or "",
            "translation": annotation.text,
            "raw_translation": record.translation,
            "semantic_role": annotation.semantic_role,
            "semantic_role_label": annotation.semantic_label,
            "semantic_tag": annotation.semantic_tag,
            "status": "ok",
            "message": "",
            "will_import": True,
            "block_index": None,
            "layout_hint": record.layout_hint,
            "line_break_source": "ai_preferred" if "\n" in annotation.text else "single_line",
        }

        block: Optional[TextBlock] = None
        if record.block_id:
            block = block_map.get(record.block_id)
            if block is None:
                entry["status"] = "error"
                entry["message"] = f"Block ID '{record.block_id}' ไม่พบในโปรเจกต์"
                entry["will_import"] = False
                preview_records.append(entry)
                continue
        elif record.source_text:
            block, match_score = _find_source_match(record.source_text, ordered_blocks, used_block_ids)
            if block is None:
                entry["status"] = "warning"
                entry["message"] = f"ไม่พบคำต้นฉบับที่ตรงกัน (best match {match_score:.0%})"
                entry["will_import"] = False
                preview_records.append(entry)
                continue
        else:
            bubble_index = record.bubble_index or sequential_index
            if not 1 <= bubble_index <= len(ordered_blocks):
                entry["status"] = "error"
                entry["message"] = f"Bubble {bubble_index} อยู่นอกขอบเขต (1-{len(ordered_blocks)})"
                entry["will_import"] = False
                preview_records.append(entry)
                continue
            block = ordered_blocks[bubble_index - 1]

        if block.id in used_block_ids:
            entry["status"] = "error"
            entry["message"] = "ซ้ำกับ Bubble อื่นที่ import ไปแล้ว"
            entry["will_import"] = False
            preview_records.append(entry)
            continue
        used_block_ids.add(block.id)
        entry["block_index"] = ordered_blocks.index(block) + 1

        if record.source_text and _normalize_source(record.source_text) != _normalize_source(block.source_text or ""):
            entry["status"] = "warning"
            file_src = record.source_text.strip()
            db_src = (block.source_text or "").strip()
            file_disp = (file_src[:12] + "...") if len(file_src) > 12 else file_src
            db_disp = (db_src[:12] + "...") if len(db_src) > 12 else db_src
            entry["message"] = f"คำต้นฉบับไม่ตรงกับ Bubble {ordered_blocks.index(block) + 1} (ไฟล์: '{file_disp}' | ระบบ: '{db_disp}')"

        if annotation.warning and entry["status"] == "ok":
            entry["status"] = "warning"
            entry["message"] = annotation.warning

        if not annotation.text.strip():
            entry["status"] = "skip"
            entry["message"] = "คำแปลว่างเปล่า"
            entry["will_import"] = False
            preview_records.append(entry)
            continue

        target_lang = str(project.target_lang or "").lower()
        if target_lang.startswith("th") and not re.search(r"[\u0e00-\u0e7f]", annotation.text):
            entry["status"] = "warning"
            entry["message"] = "คำแปลไม่มีอักษรไทย"
            entry["will_import"] = False

        preview_records.append(entry)

    ok_count = sum(1 for r in preview_records if r["status"] == "ok")
    warn_count = sum(1 for r in preview_records if r["status"] == "warning")
    error_count = sum(1 for r in preview_records if r["status"] == "error")
    skip_count = sum(1 for r in preview_records if r["status"] == "skip")
    importable_count = sum(1 for r in preview_records if r["will_import"])

    return {
        "success": True,
        "format": detected_format,
        "preview_records": preview_records,
        "summary": {
            "ok": ok_count,
            "warning": warn_count,
            "error": error_count,
            "skip": skip_count,
            "total": len(preview_records),
            "importable": importable_count,
        },
    }


def validate_and_import_txt(project_id: str, txt_content: str, db: Session, exclude_lines: set[int] = None) -> dict:
    """Validate the entire file, then atomically import user-authored translations."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError("Project not found")

    ordered_blocks = _ordered_blocks(project)
    block_map = {block.id: block for block in ordered_blocks}
    try:
        detected_format, records = parse_translation_txt(txt_content)
    except ValueError as exc:
        return {
            "success": False,
            "updated_count": 0,
            "skipped_empty_count": 0,
            "format": "unknown",
            "errors": [str(exc)],
            "warnings": [],
        }

    errors: list[str] = []
    warnings: list[str] = []
    updates: list[tuple[TextBlock, TranslationAnnotation, str, ImportRecord]] = []
    used_block_ids: set[str] = set()
    skipped_empty = 0
    skipped_unmatched = 0

    tag_map = build_tag_map(
        (project.settings or {}).get("text_templates") or None
    )

    for sequential_index, record in enumerate(records, start=1):
        annotation = parse_translation_annotation(record.translation, tag_map)
        if exclude_lines and record.line_number in exclude_lines:
            skipped_empty += 1
            continue

        block: Optional[TextBlock] = None
        if record.block_id:
            block = block_map.get(record.block_id)
            if block is None:
                skipped_unmatched += 1
                warnings.append(f"Line {record.line_number}: block ID '{record.block_id}' was not found; skipped")
                continue
        elif record.source_text:
            block, match_score = _find_source_match(record.source_text, ordered_blocks, used_block_ids)
            if block is None:
                skipped_unmatched += 1
                warnings.append(
                    f"Line {record.line_number}: no confident source match (best {match_score:.0%}); skipped"
                )
                continue
        else:
            bubble_index = record.bubble_index or sequential_index
            if not 1 <= bubble_index <= len(ordered_blocks):
                skipped_unmatched += 1
                warnings.append(
                    f"Line {record.line_number}: Bubble {bubble_index} is outside project range 1-{len(ordered_blocks)}; skipped"
                )
                continue
            block = ordered_blocks[bubble_index - 1]

        if block.id in used_block_ids:
            skipped_unmatched += 1
            warnings.append(f"Line {record.line_number}: Bubble target is duplicated; skipped")
            continue
        used_block_ids.add(block.id)

        if record.source_text and _normalize_source(record.source_text) != _normalize_source(block.source_text or ""):
            message = f"Line {record.line_number}: source text does not match Bubble {ordered_blocks.index(block) + 1}"
            if detected_format in {"bubble", "alternating", "tsv"}:
                warnings.append(message)
            else:
                errors.append(message)
                continue

        if not annotation.text.strip():
            skipped_empty += 1
            continue
        if str(project.target_lang or "").lower().startswith("th") and not re.search(r"[\u0e00-\u0e7f]", annotation.text):
            skipped_unmatched += 1
            warnings.append(f"Line {record.line_number}: translation has no Thai text; skipped")
            continue
        if annotation.warning:
            warnings.append(f"Line {record.line_number}: {annotation.warning}")
        updates.append((block, annotation, record.translation.strip(), record))

    if not records:
        errors.append("No translation records were found")
    if not updates and not errors and skipped_unmatched == 0:
        errors.append("No non-empty translations were found")
    if errors:
        db.rollback()
        return {
            "success": False,
            "updated_count": 0,
            "skipped_empty_count": skipped_empty,
            "format": detected_format,
            "errors": errors,
            "warnings": warnings,
        }

    try:
        from sqlalchemy.orm.attributes import flag_modified

        refresh_block_layout_regions([block for block, _, _, _ in updates])
        for block, annotation, raw_translation, record in updates:
            canonical_layout_text = _canonical_ai_layout_text(
                block.translation or "", annotation.text
            )
            block.translation = annotation.text
            metadata = dict(block.extra_metadata or {})
            preferred_lines = [line for line in annotation.text.splitlines() if line.strip()]
            if len(preferred_lines) > 1:
                metadata["line_break_source"] = "ai_preferred"
                metadata["ai_preferred_lines"] = preferred_lines
                metadata["ai_layout_text"] = canonical_layout_text
            else:
                metadata.pop("line_break_source", None)
                metadata.pop("ai_preferred_lines", None)
                metadata.pop("ai_layout_text", None)
            if record.layout_hint:
                metadata["ai_layout_hint"] = dict(record.layout_hint)
            else:
                metadata.pop("ai_layout_hint", None)
            if annotation.semantic_role:
                metadata.update({
                    "semantic_role": annotation.semantic_role,
                    "semantic_role_label": annotation.semantic_label,
                    "semantic_role_source": "ai_translation_import_tag",
                    "semantic_role_tag": annotation.semantic_tag,
                    "semantic_role_confidence": 1.0,
                    "semantic_role_raw_translation": raw_translation,
                })
            else:
                for key in (
                    "semantic_role",
                    "semantic_role_label",
                    "semantic_role_source",
                    "semantic_role_tag",
                    "semantic_role_confidence",
                    "semantic_role_raw_translation",
                    "semantic_role_template_id",
                ):
                    metadata.pop(key, None)
            block.extra_metadata = metadata
            applied_template = _apply_semantic_template(
                block, annotation.semantic_role, project.settings or {}
            )
            metadata = dict(block.extra_metadata or {})
            if annotation.semantic_role:
                metadata["semantic_role_template_id"] = applied_template
            block.extra_metadata = metadata
            spec = compute_block_typesetting(block)
            from app.services.typesetting import persist_typesetting_spec
            persist_typesetting_spec(block, spec, reset_suggestion=True)
            flag_modified(block, "extra_metadata")
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "success": True,
        "updated_count": len(updates),
        "skipped_empty_count": skipped_empty,
        "skipped_unmatched_count": skipped_unmatched,
        "format": detected_format,
        "errors": [],
        "warnings": warnings,
    }


def _layout_hint_for_block(block: TextBlock, settings: dict) -> dict:
    """Build a compact, deterministic geometry hint for an external AI."""
    from app.services.typesetting.smart_balloon_context import build_smart_balloon_spatial_context
    return build_smart_balloon_spatial_context(block, settings)

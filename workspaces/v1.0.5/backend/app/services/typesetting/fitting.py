import math
import os
import re
from functools import lru_cache
from pathlib import Path
from PIL import ImageFont
from app.services.font_registry import font_registry
from app.services.typesetting.scoring import score_layout
from app.services.typesetting.tracking import measure_text_with_tracking
from app.services.typesetting.contour_fitting import LineWidthProvider


@lru_cache(maxsize=512)
def _load_font(font_path: str, size: int):
    """Pillow font parsing is expensive; reuse handles across block recomputes."""
    return ImageFont.truetype(font_path, size)


def join_tokens(tokens: list[str]) -> str:
    """
    Joins tokens together naturally, avoiding spaces between CJK/Thai characters while
    preserving spaces between Latin words.
    """
    if not tokens:
        return ""
    # Match CJK characters and Thai characters
    no_space_pattern = re.compile(
        r"[\u4e00-\u9fff\u3040-\u30ff\u31f0-\u31ff\u30a0-\u30ff\uff00-\uffef\u0e00-\u0e7f]"
    )
    result = []
    for i, tok in enumerate(tokens):
        if i == 0:
            result.append(tok)
            continue

        prev_tok = tokens[i - 1]

        if tok.isspace():
            if result and not result[-1].endswith(" "):
                result.append(" ")
        elif prev_tok.isspace():
            result.append(tok)
        # If BOTH tokens are CJK/Thai, no space unless the author supplied one.
        elif no_space_pattern.search(prev_tok) and no_space_pattern.search(tok):
            result.append(tok)
        elif tok.startswith(tuple(".,!?:;)）]】”’")):
            result.append(tok)
        elif prev_tok.endswith(tuple("([{（【“‘")):
            result.append(tok)
        else:
            result.append(" " + tok)

    return "".join(result)


def get_token_source_positions(normalized_text: str, tokens: list[str]) -> list[int]:
    positions = []
    current_idx = 0
    for tok in tokens:
        if tok != "\n" and not tok.isspace():
            while (
                current_idx < len(normalized_text)
                and normalized_text[current_idx].isspace()
                and normalized_text[current_idx] != "\n"
            ):
                current_idx += 1
        positions.append(current_idx)
        current_idx += len(tok)
    return positions


def _measure_width(
    font: ImageFont.FreeTypeFont,
    text: str,
    font_size: float,
    tracking: float = 0.0,
) -> float:
    """
    Measure line width. tracking uses Fabric/Photoshop convention:
    thousandths of an em (charSpacing).
    """
    return measure_text_with_tracking(font, text, font_size, tracking)


def _join_type(prev_tok: str, next_tok: str) -> str:
    no_space_pattern = re.compile(
        r"[\u4e00-\u9fff\u3040-\u30ff\u31f0-\u31ff\u30a0-\u30ff\uff00-\uffef\u0e00-\u0e7f]"
    )
    if no_space_pattern.search(prev_tok) and no_space_pattern.search(next_tok):
        return "cjk_thai"
    if next_tok.startswith(tuple(".,!?:;)）]】”’")):
        return "cjk_thai"
    if prev_tok.endswith(tuple("([{（【“‘")):
        return "cjk_thai"
    return "space"


def _line_allowed_width(
    line_index: int,
    num_lines: int,
    line_height: float,
    line_spacing: float,
    block_w: float,
    block_h: float,
    balloon_type: str,
    ellipse_safety_factor: float,
    rect_safety_factor: float,
    line_width_provider: LineWidthProvider | None = None,
) -> float:
    """Allowed width for a line center inside a contour, ellipse, or rectangle."""
    if line_width_provider is not None:
        return max(
            0.0,
            float(
                line_width_provider(
                    line_index,
                    num_lines,
                    line_height,
                    line_spacing,
                    block_w,
                    block_h,
                )
            ),
        )
    total_height = num_lines * line_height + max(0, num_lines - 1) * line_spacing
    half_h = block_h / 2.0
    line_center_from_top = line_index * (line_height + line_spacing) + line_height / 2.0
    y = line_center_from_top - total_height / 2.0

    if balloon_type == "bubble":
        if half_h <= 0:
            return 0.0
        normalized_y = abs(y) / half_h
        if normalized_y >= 1.0:
            return 0.0
        return block_w * math.sqrt(max(0.0, 1.0 - normalized_y**2)) * ellipse_safety_factor
    return block_w * rect_safety_factor


def _evaluate_lines(
    lines: list[str],
    font: ImageFont.FreeTypeFont,
    font_size: float,
    block_w: float,
    block_h: float,
    balloon_type: str,
    line_height_ratio: float,
    ellipse_safety_factor: float,
    rect_safety_factor: float,
    tracking: float = 0.0,
    line_width_provider: LineWidthProvider | None = None,
) -> tuple[list[float], float, bool, float]:
    line_height = font_size * line_height_ratio
    line_spacing = 0.0
    line_widths = [_measure_width(font, line, font_size, tracking) for line in lines]
    total_height = len(lines) * line_height + max(0, len(lines) - 1) * line_spacing
    overflow = False
    overflow_score = 0.0
    half_h = block_h / 2.0

    if total_height > block_h * 0.98:
        overflow = True
        overflow_score += total_height - block_h * 0.98

    for i, line_w in enumerate(line_widths):
        line_center_from_top = i * (line_height + line_spacing) + line_height / 2.0
        y = line_center_from_top - total_height / 2.0

        if line_width_provider is not None:
            allowed_w = _line_allowed_width(
                i,
                len(lines),
                line_height,
                line_spacing,
                block_w,
                block_h,
                balloon_type,
                ellipse_safety_factor,
                rect_safety_factor,
                line_width_provider,
            )
        elif balloon_type == "bubble":
            normalized_y = abs(y) / half_h if half_h > 0 else 1.0
            if normalized_y >= 1.0:
                overflow = True
                overflow_score += (abs(y) - half_h) * 5.0
                allowed_w = 0.0
            else:
                allowed_w = block_w * math.sqrt(max(0.0, 1.0 - normalized_y**2)) * ellipse_safety_factor
        else:
            allowed_w = block_w * rect_safety_factor

        if line_w > allowed_w:
            overflow = True
            overflow_score += line_w - allowed_w

    return line_widths, total_height, overflow, overflow_score


def wrap_tokens_to_lines(
    tokens: list[str],
    font: ImageFont.FreeTypeFont,
    block_w: float,
    block_h: float,
    balloon_type: str,
    line_height_ratio: float = 1.2,
    tokens_positions: list[int] = None,
    tracking: float = 0.0,
    line_width_provider: LineWidthProvider | None = None,
) -> tuple[list[str], list[float], float, bool, float, list[dict]]:
    """
    Greedy wrap (legacy path / baseline). Prefer generate_line_candidates + rank
    for production candidate search.
    Returns: (lines, line_widths, total_height, overflow, overflow_score, break_provenance)
    """
    font_size = font.size
    line_height = font_size * line_height_ratio
    line_spacing = 0.0

    lines = []
    line_widths = []
    current_line_token_indices = []
    line_token_indices = []
    breaks = []

    ellipse_safety_factor = 0.88
    rect_safety_factor = 0.95

    # Conservative base width for greedy packing (ellipse mid-band)
    base_limit = block_w * (ellipse_safety_factor if balloon_type == "bubble" else rect_safety_factor)

    for idx, token in enumerate(tokens):
        if token == "\n":
            if current_line_token_indices:
                lines.append(join_tokens([tokens[j] for j in current_line_token_indices]).strip())
                line_token_indices.append(current_line_token_indices)
                current_line_token_indices = []
            else:
                lines.append("")
                line_token_indices.append([])
            breaks.append({"break_kind": "authored", "join_type": "none", "token_index": idx})
            continue

        current_line_token_indices.append(idx)
        current_str = join_tokens([tokens[j] for j in current_line_token_indices])
        w = _measure_width(font, current_str, font_size, tracking)

        if w > base_limit and len(current_line_token_indices) > 1:
            current_line_token_indices.pop()
            lines.append(join_tokens([tokens[j] for j in current_line_token_indices]).strip())
            line_token_indices.append(current_line_token_indices)

            last_tok_of_prev = tokens[current_line_token_indices[-1]]
            join_type = _join_type(last_tok_of_prev, token)
            breaks.append({"break_kind": "automatic", "join_type": join_type, "token_index": idx})
            current_line_token_indices = [idx]

    if current_line_token_indices:
        lines.append(join_tokens([tokens[j] for j in current_line_token_indices]).strip())
        line_token_indices.append(current_line_token_indices)

    line_widths, total_height, overflow, overflow_score = _evaluate_lines(
        lines,
        font,
        font_size,
        block_w,
        block_h,
        balloon_type,
        line_height_ratio,
        ellipse_safety_factor,
        rect_safety_factor,
        tracking=tracking,
        line_width_provider=line_width_provider,
    )

    break_provenance = []
    current_char_offset = 0
    for i in range(len(lines) - 1):
        current_char_offset += len(lines[i])
        brk = breaks[i] if i < len(breaks) else {
            "break_kind": "automatic",
            "join_type": "space",
            "token_index": 0,
        }
        token_index = brk["token_index"]
        if tokens_positions and token_index < len(tokens_positions):
            source_offset = tokens_positions[token_index]
        else:
            source_offset = 0
        break_provenance.append(
            {
                "line_index": i,
                "char_offset": current_char_offset,
                "source_offset": source_offset,
                "break_kind": brk["break_kind"],
                "join_type": brk["join_type"],
            }
        )
        current_char_offset += 1

    return lines, line_widths, total_height, overflow, overflow_score, break_provenance


def _split_token_runs(tokens: list[str]) -> list[list[str]]:
    """Split tokens on authored newlines into independent runs."""
    runs: list[list[str]] = []
    current: list[str] = []
    for tok in tokens:
        if tok == "\n":
            runs.append(current)
            current = []
        else:
            current.append(tok)
    runs.append(current)
    return runs


def _beam_wrap_run(
    run_tokens: list[str],
    font: ImageFont.FreeTypeFont,
    font_size: float,
    base_limit: float,
    beam_width: int,
    tracking: float = 0.0,
) -> list[list[list[int]]]:
    """
    Beam search over break positions within one authored run.
    Returns list of candidates; each candidate is list of lines; each line is token indices
    into run_tokens.
    """
    if not run_tokens:
        return [[[]]]

    # State: (token_index_consumed, lines_so_far, current_line_indices)
    # lines_so_far: list of list[int]
    beam: list[tuple[list[list[int]], list[int]]] = [([], [])]

    for t_idx, token in enumerate(run_tokens):
        next_beam: list[tuple[list[list[int]], list[int], float]] = []

        for lines_so_far, cur_line in beam:
            # Option A: append token to current line (if fits or line empty)
            trial = cur_line + [t_idx]
            trial_str = join_tokens([run_tokens[j] for j in trial]).strip()
            trial_w = _measure_width(font, trial_str, font_size, tracking)

            can_append = (not cur_line) or (trial_w <= base_limit)
            if can_append:
                # score preference: fuller lines
                fill = trial_w / base_limit if base_limit > 0 else 0.0
                next_beam.append((lines_so_far, trial, fill))

            # Option B: break before this token (start new line), if current line non-empty
            if cur_line:
                new_lines = lines_so_far + [cur_line]
                new_cur = [t_idx]
                new_str = join_tokens([run_tokens[j] for j in new_cur]).strip()
                new_w = _measure_width(font, new_str, font_size, tracking)
                # Allow even if single token exceeds limit (will mark overflow later)
                fill = new_w / base_limit if base_limit > 0 else 0.0
                # Prefer breaking when previous line was reasonably full
                prev_str = join_tokens([run_tokens[j] for j in cur_line]).strip()
                prev_w = _measure_width(font, prev_str, font_size, tracking)
                prev_fill = prev_w / base_limit if base_limit > 0 else 0.0
                next_beam.append((new_lines, new_cur, prev_fill + fill * 0.1))

        if not next_beam:
            # Force place token (should not happen often)
            next_beam = [([], [t_idx], 0.0)]

        # Keep a mix of top-fill candidates and early-break candidates for line shape diversity
        next_beam.sort(key=lambda s: s[2], reverse=True)
        half_beam = max(1, beam_width // 2)
        top_fill = next_beam[:half_beam]
        # Sort remaining by lowest non-zero fill (early break)
        remaining = [s for s in next_beam[half_beam:] if s[2] > 0.05]
        remaining.sort(key=lambda s: s[2])
        diverse = remaining[:beam_width - half_beam]
        
        trimmed = top_fill + diverse
        if len(trimmed) < beam_width and len(next_beam) > len(trimmed):
            # Fill remaining budget if needed
            seen = set(id(x) for x in trimmed)
            for item in next_beam:
                if id(item) not in seen:
                    trimmed.append(item)
                    seen.add(id(item))
                    if len(trimmed) >= beam_width:
                        break
        beam = [(lines, cur) for lines, cur, _ in trimmed]

    # Finalize
    results: list[list[list[int]]] = []
    seen = set()
    for lines_so_far, cur_line in beam:
        final_lines = list(lines_so_far)
        if cur_line:
            final_lines.append(cur_line)
        elif not final_lines:
            final_lines = [[]]
        key = tuple(tuple(line) for line in final_lines)
        if key not in seen:
            seen.add(key)
            results.append(final_lines)
    return results


def generate_line_candidates(
    tokens: list[str],
    font: ImageFont.FreeTypeFont,
    block_w: float,
    block_h: float,
    balloon_type: str,
    line_height_ratio: float = 1.2,
    tokens_positions: list[int] | None = None,
    beam_width: int = 8,
    max_candidates: int = 24,
    tracking: float = 0.0,
    line_width_provider: LineWidthProvider | None = None,
) -> list[dict]:
    """
    Generate multiple hard-constraint-aware line-break candidates via beam search.
    Always includes the greedy baseline. Invalid (overflow) candidates are kept but flagged
    so the ranker can prefer feasible ones.
    """
    font_size = float(font.size)
    ellipse_safety_factor = 0.88
    rect_safety_factor = 0.95
    base_limit = block_w * (ellipse_safety_factor if balloon_type == "bubble" else rect_safety_factor)
    beam_width = max(2, min(16, int(beam_width)))
    max_candidates = max(4, min(48, int(max_candidates)))

    runs = _split_token_runs(tokens)
    
    limits_to_try = [base_limit]
    if line_width_provider is not None:
        limits_to_try.extend([base_limit * 0.85, base_limit * 0.70, base_limit * 0.55, base_limit * 0.40])

    # Per-run beam candidates (list of line-index lists into that run)
    per_run_options: list[list[list[list[int]]]] = []
    for run in runs:
        opts_for_run = []
        seen_run_plans = set()
        for limit in limits_to_try:
            beam_opts = _beam_wrap_run(run, font, font_size, limit, beam_width, tracking=tracking)
            for opt in beam_opts:
                plan_key = tuple(tuple(l) for l in opt)
                if plan_key not in seen_run_plans:
                    seen_run_plans.add(plan_key)
                    opts_for_run.append(opt)
        per_run_options.append(opts_for_run if opts_for_run else [[[]]])

    # Cartesian product limited — greedy combine: pick top options per run
    # Start with single empty combination
    combos: list[list[list[list[int]]]] = [[]]
    for run_opts in per_run_options:
        new_combos = []
        for combo in combos:
            # allow more candidates per run since we injected variations
            limit = max_candidates
            for opt in run_opts[:limit]:
                new_combos.append(combo + [opt])
                if len(new_combos) >= max_candidates * 2:
                    break
            if len(new_combos) >= max_candidates * 2:
                break
        combos = new_combos or combos

    candidates: list[dict] = []
    seen_line_keys = set()

    def _materialize(run_line_plans: list[list[list[int]]]) -> dict | None:
        """Convert per-run line index plans into global lines + provenance."""
        lines: list[str] = []
        breaks: list[dict] = []
        t_idx = 0
        for r_i, run in enumerate(runs):
            plan = run_line_plans[r_i] if r_i < len(run_line_plans) else [list(range(len(run)))]
            run_global: list[int] = []
            while t_idx < len(tokens) and tokens[t_idx] == "\n":
                if lines:
                    breaks.append(
                        {
                            "break_kind": "authored",
                            "join_type": "none",
                            "token_index": t_idx,
                        }
                    )
                t_idx += 1
            for _ in run:
                if t_idx < len(tokens) and tokens[t_idx] != "\n":
                    run_global.append(t_idx)
                    t_idx += 1

            for li, line_local in enumerate(plan):
                if not line_local and not run:
                    lines.append("")
                    continue
                global_idxs = [run_global[j] for j in line_local if j < len(run_global)]
                if not global_idxs and run:
                    continue
                line_text = join_tokens([tokens[j] for j in global_idxs]).strip()
                if li > 0 and global_idxs and plan[li - 1]:
                    prev_last = run_global[plan[li - 1][-1]]
                    breaks.append(
                        {
                            "break_kind": "automatic",
                            "join_type": _join_type(tokens[prev_last], tokens[global_idxs[0]]),
                            "token_index": global_idxs[0],
                        }
                    )
                lines.append(line_text)

        if not lines:
            lines = [""]

        key = tuple(lines)
        if key in seen_line_keys:
            return None
        seen_line_keys.add(key)

        line_widths, total_height, overflow, overflow_score = _evaluate_lines(
            lines,
            font,
            font_size,
            block_w,
            block_h,
            balloon_type,
            line_height_ratio,
            ellipse_safety_factor,
            rect_safety_factor,
            tracking=tracking,
            line_width_provider=line_width_provider,
        )

        break_provenance = []
        current_char_offset = 0
        for i in range(len(lines) - 1):
            current_char_offset += len(lines[i])
            brk = (
                breaks[i]
                if i < len(breaks)
                else {"break_kind": "automatic", "join_type": "space", "token_index": 0}
            )
            token_index = brk.get("token_index", 0)
            if tokens_positions and token_index < len(tokens_positions):
                source_offset = tokens_positions[token_index]
            else:
                source_offset = 0
            break_provenance.append(
                {
                    "line_index": i,
                    "char_offset": current_char_offset,
                    "source_offset": source_offset,
                    "break_kind": brk.get("break_kind", "automatic"),
                    "join_type": brk.get("join_type", "space"),
                }
            )
            current_char_offset += 1

        return {
            "explicit_lines": lines,
            "line_widths": line_widths,
            "total_height": total_height,
            "overflow": overflow,
            "overflow_score": overflow_score,
            "break_provenance": break_provenance,
            "generator": "beam",
        }

    # Authored/AI newlines are a layout contract. Do not insert additional
    # automatic wraps inside those lines; fitting must reduce the font size (or
    # report overflow) instead of changing the requested line composition.
    if any(token == "\n" for token in tokens):
        authored_plan = [[list(range(len(run)))] for run in runs]
        authored = _materialize(authored_plan)
        if authored is not None:
            authored["generator"] = "authored"
            return [authored]

    for combo in combos:
        item = _materialize(combo)
        if item is not None:
            candidates.append(item)
        if len(candidates) >= max_candidates:
            break

    # Always include greedy baseline
    g_lines, g_widths, g_h, g_over, g_os, g_prov = wrap_tokens_to_lines(
        tokens,
        font,
        block_w,
        block_h,
        balloon_type,
        line_height_ratio,
        tokens_positions,
        tracking=tracking,
        line_width_provider=line_width_provider,
    )
    g_key = tuple(g_lines)
    if g_key not in seen_line_keys:
        candidates.append(
            {
                "explicit_lines": g_lines,
                "line_widths": g_widths,
                "total_height": g_h,
                "overflow": g_over,
                "overflow_score": g_os,
                "break_provenance": g_prov,
                "generator": "greedy",
            }
        )

    # Contour-aware greedy: try wrapping with per-line allowed widths
    # from the contour profile for various target line counts
    if line_width_provider is not None:
        line_height = font_size * line_height_ratio
        for target_n in range(3, 7):
            total_height_est = target_n * line_height
            if total_height_est > block_h * 0.98:
                continue
            # Get per-line allowed widths from contour
            per_line_widths = []
            for li in range(target_n):
                aw = line_width_provider(li, target_n, line_height, 0.0, block_w, block_h)
                per_line_widths.append(aw)
            if min(per_line_widths) < font_size * 0.5:
                continue

            # Greedy fill using contour widths
            c_lines: list[str] = []
            current_line_tokens: list[str] = []
            current_w = 0.0
            li = 0
            for tok in tokens:
                if tok == "\n":
                    c_lines.append(join_tokens(current_line_tokens).strip())
                    current_line_tokens = []
                    current_w = 0.0
                    li = min(li + 1, target_n - 1)
                    continue
                tok_w = _measure_width(font, join_tokens(current_line_tokens + [tok]).strip(), font_size, tracking)
                allowed = per_line_widths[li] if li < len(per_line_widths) else block_w
                if current_line_tokens and tok_w > allowed and li < target_n - 1:
                    c_lines.append(join_tokens(current_line_tokens).strip())
                    current_line_tokens = [tok]
                    current_w = _measure_width(font, tok, font_size, tracking)
                    li = min(li + 1, target_n - 1)
                else:
                    current_line_tokens.append(tok)
                    current_w = tok_w
            if current_line_tokens:
                c_lines.append(join_tokens(current_line_tokens).strip())

            c_lines = [l for l in c_lines if l]
            if not c_lines:
                continue
            c_key = tuple(c_lines)
            if c_key in seen_line_keys:
                continue
            seen_line_keys.add(c_key)

            # Evaluate this candidate
            c_widths = [_measure_width(font, line, font_size, tracking) for line in c_lines]
            c_total_h = len(c_lines) * line_height
            c_overflow, c_overflow_score = False, 0.0
            if c_total_h > block_h * 0.98:
                c_overflow = True
                c_overflow_score += c_total_h - block_h * 0.98
            for ci, cw in enumerate(c_widths):
                aw = line_width_provider(ci, len(c_lines), line_height, 0.0, block_w, block_h)
                if cw > aw:
                    c_overflow = True
                    c_overflow_score += cw - aw

            candidates.append(
                {
                    "explicit_lines": c_lines,
                    "line_widths": c_widths,
                    "total_height": c_total_h,
                    "overflow": c_overflow,
                    "overflow_score": c_overflow_score,
                    "break_provenance": [],
                    "generator": "contour_greedy",
                }
            )

    if not candidates:
        candidates.append(
            {
                "explicit_lines": [""],
                "line_widths": [0.0],
                "total_height": 0.0,
                "overflow": False,
                "overflow_score": 0.0,
                "break_provenance": [],
                "generator": "empty",
            }
        )
    return candidates


def rank_line_candidates(
    candidates: list[dict],
    font_size: float,
    block_w: float,
    block_h: float,
    balloon_type: str,
    preferred_lines: list[str] | None = None,
    target_line_count: int | None = None,
    maximum_line_count: int | None = None,
) -> dict:
    """Decision Ranker (rules): pick best feasible candidate, then best overflow."""
    def break_offsets(lines: list[str]) -> list[int]:
        offsets: list[int] = []
        consumed = 0
        for line in lines[:-1]:
            consumed += len(re.sub(r"\s+", "", line))
            offsets.append(consumed)
        return offsets

    preferred_offsets = break_offsets(preferred_lines or [])
    effective_target = target_line_count or (len(preferred_lines) if preferred_lines else None)
    best_score = -999999.0
    best = None
    for cand in candidates:
        line_count_excess = (
            max(0, len(cand["explicit_lines"]) - int(maximum_line_count))
            if maximum_line_count
            else 0
        )
        effective_overflow = bool(cand["overflow"] or line_count_excess)
        effective_overflow_score = float(cand["overflow_score"]) + (line_count_excess * 1000.0)
        score = score_layout(
            font_size,
            cand["explicit_lines"],
            cand["line_widths"],
            cand["total_height"],
            effective_overflow,
            effective_overflow_score,
            block_w,
            block_h,
            balloon_type,
        )
        # Slight preference for beam (more balanced) over pure greedy when tied
        if cand.get("generator") == "beam":
            score += 5.0
        if effective_target:
            score -= abs(len(cand["explicit_lines"]) - int(effective_target)) * 18.0
        if preferred_offsets:
            candidate_offsets = break_offsets(cand["explicit_lines"])
            if candidate_offsets:
                distance = sum(min(abs(offset - candidate) for candidate in candidate_offsets) for offset in preferred_offsets)
                score -= min(48.0, float(distance) * 1.5)
                if distance == 0 and len(candidate_offsets) == len(preferred_offsets):
                    score += 12.0
        cand = {
            **cand,
            "overflow": effective_overflow,
            "overflow_score": effective_overflow_score,
            "line_count_excess": line_count_excess,
            "quality_score": score,
        }
        replaces_overflow = best is not None and best["overflow"] and not cand["overflow"]
        same_fit = best is None or best["overflow"] == cand["overflow"]
        if best is None or replaces_overflow or (same_fit and score > best_score):
            best_score = score
            best = cand
    return best


def compute_best_layout(
    tokens: list[str],
    font_name: str,
    bold: bool,
    italic: bool,
    block_w: float,
    block_h: float,
    balloon_type: str,
    requested_font_size: float = 16.0,
    minimum_font_size: float | None = None,
    candidate_budget: int = 40,
    line_height_ratio: float = 1.2,
    normalized_text: str = "",
    lock_font_size: bool = False,
    beam_width: int = 6,
    line_candidate_budget: int = 16,
    tracking: float = 0.0,
    preferred_lines: list[str] | None = None,
    target_line_count: int | None = None,
    maximum_line_count: int | None = None,
    line_width_provider: LineWidthProvider | None = None,
) -> dict:
    """
    Evaluates font sizes × line-break candidates; returns best layout dict.
    """
    resolved_entry = font_registry.resolve_font(font_name, bold=bold, italic=italic)

    best_score = -999999.0
    best_layout = None

    max_size = int(requested_font_size) if (requested_font_size is not None and requested_font_size > 0) else 100
    if minimum_font_size is not None and minimum_font_size > 0:
        pref_min = max(6, int(math.ceil(minimum_font_size)))
        # min_font_size is a preferred quality threshold in Auto mode. Search
        # down to the engine safety floor so fitting wins over text overflow.
        min_size = 6
        max_size = max(max_size, pref_min)
    elif max_size < 10:
        min_size = 6
        max_size = max(6, max_size)
    else:
        min_size = 6

    tokens_positions = get_token_source_positions(normalized_text, tokens) if normalized_text else None

    if not lock_font_size:
        # Cap max_size by block height so text size never inflates to absurd sizes (e.g. 216pt in 100px box)
        box_height_cap = max(12, int(round(block_h * 0.98)))
        max_size = min(max_size, box_height_cap)
        min_size = min(min_size, max_size)

    if lock_font_size:
        locked_size = max(6, int(round(requested_font_size)))
        candidate_sizes = [locked_size]
    else:
        span = max_size - min_size
        candidate_budget = max(12, min(96, int(candidate_budget)))
        step = max(1, math.ceil(span / candidate_budget))
        candidate_sizes = list(range(min_size, max_size + 1, step))
        if not candidate_sizes or candidate_sizes[-1] != max_size:
            candidate_sizes.append(max_size)
        # Ensure fine-grained coverage near the top of the range (last 30%)
        # so the engine doesn't skip over valid sizes due to large step sizes
        fine_start = max(min_size, int(max_size * 0.7))
        for s in range(fine_start, max_size + 1, max(1, step // 2) if step > 2 else 2):
            if s not in candidate_sizes:
                candidate_sizes.append(s)
        candidate_sizes.sort()

    line_candidates_evaluated = 0

    for size in candidate_sizes:
        try:
            font = _load_font(str(resolved_entry.file_path), int(size))
        except Exception:
            font = ImageFont.load_default()

        line_cands = generate_line_candidates(
            tokens,
            font,
            block_w,
            block_h,
            balloon_type,
            line_height_ratio,
            tokens_positions,
            beam_width=beam_width,
            max_candidates=line_candidate_budget,
            tracking=tracking,
            line_width_provider=line_width_provider,
        )
        line_candidates_evaluated += len(line_cands)
        ranked = rank_line_candidates(
            line_cands,
            float(size),
            block_w,
            block_h,
            balloon_type,
            preferred_lines=preferred_lines,
            target_line_count=target_line_count,
            maximum_line_count=maximum_line_count,
        )
        if ranked is None:
            continue

        score = float(ranked["quality_score"])
        overflow = bool(ranked["overflow"])
        replaces_overflow = best_layout is not None and best_layout["overflow"] and not overflow
        both_no_overflow = best_layout is not None and not best_layout["overflow"] and not overflow
        both_overflow = best_layout is not None and best_layout["overflow"] and overflow

        should_replace = (
            best_layout is None
            or replaces_overflow
            or (both_no_overflow and score > best_score)
            or (both_overflow and (
                ranked["overflow_score"] < best_layout["overflow_score"] - 0.5
                or (abs(ranked["overflow_score"] - best_layout["overflow_score"]) <= 0.5 and score > best_score)
            ))
        )
        if should_replace:
            best_score = score
            best_layout = {
                "font_size": float(size),
                "explicit_lines": ranked["explicit_lines"],
                "break_provenance": ranked.get("break_provenance", []),
                "line_widths": ranked["line_widths"],
                "total_height": ranked["total_height"],
                "overflow": overflow,
                "overflow_score": ranked["overflow_score"],
                "resolved_entry": resolved_entry,
                "quality_score": score,
                "line_generator": ranked.get("generator", "beam"),
                "line_candidate_count": len(line_cands),
                "line_count_excess": int(ranked.get("line_count_excess", 0)),
            }

    if best_layout is None:
        best_layout = {
            "font_size": float(candidate_sizes[0] if candidate_sizes else 12),
            "explicit_lines": [""],
            "break_provenance": [],
            "line_widths": [0.0],
            "total_height": 0.0,
            "overflow": True,
            "overflow_score": 9999.0,
            "resolved_entry": resolved_entry,
            "quality_score": -99999.0,
            "line_generator": "empty",
            "line_candidate_count": 0,
            "line_count_excess": 0,
        }

    best_layout["candidate_count"] = len(candidate_sizes)
    best_layout["line_candidates_evaluated"] = line_candidates_evaluated
    return best_layout

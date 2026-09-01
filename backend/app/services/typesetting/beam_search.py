"""
Houmi Studio - Multi-Script Line-Breaking Beam Search Optimizer
Computes globally optimal paragraph line breaks inside speech balloon contours.
Minimizes raggedness variance, orphan penalties, and balloon contour collisions.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from typing import List, Tuple, Optional, Callable


@dataclass
class LineBreakState:
    token_index: int
    lines: List[str]
    total_penalty: float
    line_widths: List[float]

    def __lt__(self, other: LineBreakState) -> bool:
        return self.total_penalty < other.total_penalty


class TypesettingBeamSearchOptimizer:
    """
    Beam search line-breaking optimizer for Thai, Latin, Japanese, and Korean scripts.
    """

    def __init__(
        self,
        beam_width: int = 5,
        raggedness_weight: float = 1.0,
        orphan_penalty: float = 50.0,
        overflow_penalty: float = 500.0,
    ):
        self.beam_width = beam_width
        self.raggedness_weight = raggedness_weight
        self.orphan_penalty = orphan_penalty
        self.overflow_penalty = overflow_penalty

    def optimize_line_breaks(
        self,
        tokens: List[str],
        allowed_widths: List[float],
        measure_text_fn: Callable[[str], float],
        ideal_target_width: Optional[float] = None,
    ) -> List[str]:
        if not tokens:
            return []

        n_tokens = len(tokens)
        max_lines = max(len(allowed_widths), n_tokens)
        default_w = allowed_widths[-1] if allowed_widths else 200.0

        initial_state = LineBreakState(
            token_index=0,
            lines=[],
            total_penalty=0.0,
            line_widths=[],
        )
        beam: List[LineBreakState] = [initial_state]

        for line_idx in range(max_lines):
            next_beam: List[LineBreakState] = []
            allowed_w = allowed_widths[line_idx] if line_idx < len(allowed_widths) else default_w

            for state in beam:
                start_tok = state.token_index
                if start_tok >= n_tokens:
                    next_beam.append(state)
                    continue

                for end_tok in range(start_tok + 1, n_tokens + 1):
                    chunk_tokens = tokens[start_tok:end_tok]
                    
                    if any(ord(c) >= 0x0E00 and ord(c) <= 0x0E7F for c in chunk_tokens[0]):
                        candidate_line = "".join(chunk_tokens)
                    else:
                        candidate_line = " ".join(chunk_tokens)

                    line_w = measure_text_fn(candidate_line)
                    is_last_line = (end_tok == n_tokens)
                    line_penalty = 0.0

                    if line_w > allowed_w:
                        excess = line_w - allowed_w
                        line_penalty += self.overflow_penalty * (excess / max(1.0, allowed_w)) ** 2

                    diff = allowed_w - line_w
                    if diff > 0 and not is_last_line:
                        line_penalty += self.raggedness_weight * (diff / max(1.0, allowed_w)) ** 2

                    if is_last_line and (end_tok - start_tok == 1) and len(tokens) > 3:
                        line_penalty += self.orphan_penalty

                    new_lines = list(state.lines) + [candidate_line]
                    new_widths = list(state.line_widths) + [line_w]
                    new_state = LineBreakState(
                        token_index=end_tok,
                        lines=new_lines,
                        total_penalty=state.total_penalty + line_penalty,
                        line_widths=new_widths,
                    )
                    next_beam.append(new_state)

                    if line_w > allowed_w * 1.6:
                        break

            next_beam.sort(key=lambda s: s.total_penalty)
            beam = next_beam[: self.beam_width]

            if all(s.token_index >= n_tokens for s in beam):
                break

        completed_states = [s for s in beam if s.token_index >= n_tokens]
        if completed_states:
            completed_states.sort(key=lambda s: s.total_penalty)
            return completed_states[0].lines

        beam.sort(key=lambda s: s.total_penalty)
        return beam[0].lines

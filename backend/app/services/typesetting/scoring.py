import math

def score_layout(
    font_size: float,
    lines: list[str],
    line_widths: list[float],
    total_height: float,
    overflow: bool,
    overflow_score: float,
    block_w: float,
    block_h: float,
    balloon_type: str
) -> float:
    """
    Computes a layout quality score.
    Higher score is better.
    """
    if not lines:
        return -99999.0
        
    # 1. Font Size preference (encourage larger fonts with balanced weight)
    score = font_size * 25.0
    
    # 2. Severe penalty for overflow
    if overflow:
        score -= (10000.0 + overflow_score * 100.0)
        
    # 3. Shape profile evaluation
    n = len(line_widths)
    if n > 1 and max(line_widths) > 0:
        max_w = max(line_widths)
        if balloon_type in ("bubble", "ellipse", "oval"):
            # For round/oval speech bubbles, prefer an elliptical/convex curve
            ideal_ratios = [math.sin(math.pi * (i + 0.5) / n) for i in range(n)]
            max_ideal = max(ideal_ratios)
            ideal_ratios = [r / max_ideal for r in ideal_ratios]
            
            actual_ratios = [w / max_w for w in line_widths]
            shape_diff = sum(abs(a - r) for a, r in zip(actual_ratios, ideal_ratios)) / n
            score -= shape_diff * 350.0
        else:
            # For rectangular/box balloons, encourage uniform line widths
            avg_w = sum(line_widths) / n
            variance = sum((w - avg_w) ** 2 for w in line_widths) / n
            if avg_w > 0:
                balance_cv = (variance ** 0.5) / avg_w
                score -= balance_cv * 300.0
        
    # 4. Short last line penalty (avoid single orphaned short words on the last line)
    if len(line_widths) > 1:
        prev_avg = sum(line_widths[:-1]) / (len(line_widths) - 1)
        if prev_avg > 0:
            last_ratio = line_widths[-1] / prev_avg
            if last_ratio < 0.30:
                score -= 300.0
                
    # 5. Aspect ratio safety penalty
    text_w = max(line_widths) if line_widths else 1.0
    if balloon_type in ("bubble", "ellipse", "oval"):
        target_ratio = block_w / block_h if block_h > 0 else 1.0
        actual_ratio = text_w / total_height if total_height > 0 else 1.0
        ratio_diff = abs(actual_ratio - target_ratio)
        score -= (ratio_diff * 50.0)

    return score

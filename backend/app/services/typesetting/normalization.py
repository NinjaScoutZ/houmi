import re

def normalize_text(text: str) -> str:
    """
    Normalizes text by cleaning up redundant spaces/tabs, preserving manual newlines.
    Ensures combining marks and characters are intact.
    """
    if not text:
        return ""
    # Split by explicit newlines to preserve manual breaks
    lines = text.splitlines()
    normalized_lines = []
    for line in lines:
        # Replace multiple spacing characters with a single space, and strip edges
        cleaned = re.sub(r'\s+', ' ', line).strip()
        normalized_lines.append(cleaned)
    return "\n".join(normalized_lines).strip()

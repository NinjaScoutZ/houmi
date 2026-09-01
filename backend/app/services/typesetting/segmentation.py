import os
import re
from pathlib import Path
from typing import Iterable, Sequence

try:
    from pythainlp.tokenize import Tokenizer, word_tokenize as thai_word_tokenize
    from pythainlp.util import Trie
    from pythainlp.corpus.common import thai_words
except ImportError:  # pragma: no cover - compatibility for minimal deployments
    Tokenizer = None
    thai_word_tokenize = None
    Trie = None
    thai_words = None

# Thai combining marks pattern (PHINTHU, MAI HAN-AKAT, SARA I/II/UE/UEE/U/UU, MAI TAIKHU, Tones, and THANTHAKHAT)
THAI_COMBINING_MARKS = r"[\u0e31\u0e34-\u0e3a\u0e47-\u0e4e]"

# Path to persistent manga & novel slang dictionary
SLANG_DATA_PATH = Path("e:/houmi/data/manga_novel_slang.txt")

# Global singleton Trie and Tokenizer cache
_BASE_THAI_TRIE: "Trie | None" = None
_GLOBAL_TOKENIZER: "Tokenizer | None" = None
_CUSTOM_CACHE_KEY: str = ""
_LAST_SLANG_MTIME: float = 0.0


def _load_slang_words() -> set[str]:
    """Load persistent manga and novel slang terms."""
    global _LAST_SLANG_MTIME
    words: set[str] = set()
    if SLANG_DATA_PATH.exists():
        try:
            _LAST_SLANG_MTIME = SLANG_DATA_PATH.stat().st_mtime
            with open(SLANG_DATA_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    w = line.strip()
                    if w and not w.startswith("#"):
                        words.add(w)
        except Exception:
            pass
    return words


def _get_base_thai_trie() -> "Trie | None":
    """Build or retrieve cached base Trie merging PyThaiNLP dictionary + manga slang."""
    global _BASE_THAI_TRIE, _GLOBAL_TOKENIZER, _LAST_SLANG_MTIME
    current_mtime = SLANG_DATA_PATH.stat().st_mtime if SLANG_DATA_PATH.exists() else 0.0
    if _BASE_THAI_TRIE is not None and current_mtime <= _LAST_SLANG_MTIME:
        return _BASE_THAI_TRIE

    if Trie is None or thai_words is None:
        return None

    try:
        all_words = set(thai_words())
        all_words.update(_load_slang_words())
        _BASE_THAI_TRIE = Trie(all_words)
        if Tokenizer is not None:
            _GLOBAL_TOKENIZER = Tokenizer(custom_dict=_BASE_THAI_TRIE, engine="newmm")
        return _BASE_THAI_TRIE
    except Exception:
        return None


def get_thai_tokenizer(project_dictionary: Sequence[str] | None = None) -> "Tokenizer | None":
    """Return a Tokenizer equipped with base words + manga slang + project dictionary."""
    global _CUSTOM_CACHE_KEY, _GLOBAL_TOKENIZER
    base_trie = _get_base_thai_trie()
    if base_trie is None or Tokenizer is None:
        return None

    if not project_dictionary:
        return _GLOBAL_TOKENIZER

    norm_dict = normalize_project_dictionary(project_dictionary)
    if not norm_dict:
        return _GLOBAL_TOKENIZER

    cache_key = "|".join(norm_dict)
    if cache_key == _CUSTOM_CACHE_KEY and _GLOBAL_TOKENIZER is not None:
        return _GLOBAL_TOKENIZER

    try:
        all_words = set(thai_words())
        all_words.update(_load_slang_words())
        all_words.update(norm_dict)
        custom_trie = Trie(all_words)
        tok = Tokenizer(custom_dict=custom_trie, engine="newmm")
        _CUSTOM_CACHE_KEY = cache_key
        return tok
    except Exception:
        return _GLOBAL_TOKENIZER

# Regex to match tokens:
# 1. Latin/English Alphanumeric word: [a-zA-Z0-9_]+
# 2. CJK Character: [\u4e00-\u9fff\u3040-\u30ff\u31f0-\u31ff\u30a0-\u30ff\uff00-\uffef]
# 3. Thai grapheme cluster: [^\u0e31\u0e34-\u0e3a\u0e47-\u0e4e\s][\u0e31\u0e34-\u0e3a\u0e47-\u0e4e]*
# 4. Any other non-whitespace character (including punctuation, emojis)
TOKEN_REGEX = re.compile(
    r"("
    r"[a-zA-Z0-9_]+"
    r"|[ \t]+"
    r"|[\u4e00-\u9fff\u3040-\u30ff\u31f0-\u31ff\u30a0-\u30ff\uff00-\uffef]"
    r"|[^\u0e31\u0e34-\u0e3a\u0e47-\u0e4e\s][\u0e31\u0e34-\u0e3a\u0e47-\u0e4e]*"
    r"|\S"
    r")"
)

THAI_TOKEN_REGEX = re.compile(r"^[\u0e00-\u0e7f]+$")


def has_thai_word_segmenter() -> bool:
    return thai_word_tokenize is not None or Tokenizer is not None


def normalize_project_dictionary(entries: Iterable[str] | None) -> list[str]:
    """
    Normalize project dictionary terms: strip, drop empties, longest-first unique.
    Longest-first so multi-syllable proper names win over shorter substrings.
    Terms shorter than 2 characters are excluded.
    """
    if not entries:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for raw in entries:
        term = str(raw or "").strip()
        if not term or len(term) < 2 or term in seen:
            continue
        seen.add(term)
        out.append(term)
    out.sort(key=lambda t: (-len(t), t))
    return out


def _protect_dictionary_spans(text: str, dictionary: Sequence[str]) -> tuple[str, dict[str, str]]:
    """
    Replace dictionary hits with Latin placeholders that TOKEN_REGEX keeps as
    a single [a-zA-Z0-9_]+ token so Thai/newmm cannot split proper names.
    """
    if not dictionary or not text:
        return text, {}
    mapping: dict[str, str] = {}
    protected = text
    for i, term in enumerate(dictionary):
        if not term or term not in protected:
            continue
        # Must match TOKEN_REGEX latin word class as one unit
        key = f"HOUMIDICT{i:04d}X"
        mapping[key] = term
        protected = protected.replace(term, key)
    return protected, mapping


def _restore_dictionary_tokens(tokens: list[str], mapping: dict[str, str]) -> list[str]:
    if not mapping:
        return tokens
    restored: list[str] = []
    for tok in tokens:
        if tok in mapping:
            restored.append(mapping[tok])
            continue
        replaced = tok
        for key, term in mapping.items():
            if key in replaced:
                replaced = replaced.replace(key, term)
        restored.append(replaced)
    return restored


def _merge_thai_words(raw_tokens: list[str], tokenizer: "Tokenizer | None" = None) -> list[str]:
    """Merge grapheme tokens into Thai words using Trie tokenizer when available."""
    merged: list[str] = []
    thai_run: list[str] = []

    def flush() -> None:
        if thai_run:
            chunk = "".join(thai_run)
            if tokenizer is not None:
                tokens = tokenizer.word_tokenize(chunk)
            elif thai_word_tokenize is not None:
                tokens = thai_word_tokenize(chunk, engine="newmm")
            else:
                tokens = [chunk]

            merged.extend(
                token
                for token in tokens
                if token and not token.isspace()
            )
            thai_run.clear()

    for token in raw_tokens:
        if THAI_TOKEN_REGEX.fullmatch(token):
            thai_run.append(token)
        else:
            flush()
            merged.append(" " if token.isspace() else token)
    flush()
    return merged


def segment_text(text: str, project_dictionary: Sequence[str] | None = None) -> list[str]:
    """
    Segments normalized text into breakable candidate tokens using global rules.
    Manual newlines are preserved by splitting first, segmenting each part,
    and inserting a special '\\n' token in between.

    Applies:
    1. Custom compound words from Global Settings & Project Dictionary.
    2. Punctuation gluing.
    3. Backward clitic gluing (e.g. 'นะ', 'ล่ะ', 'รึ', 'สิ').
    4. Forward particle gluing (e.g. 'ก็', 'จะ', 'ยัง', 'มิ', 'ไม่').
    """
    if not text:
        return []

    # Import rules dynamically to support real-time user updates without server restarts
    try:
        from app.services.typesetting.rules_manager import get_typesetting_rules
        rules = get_typesetting_rules()
    except Exception:
        rules = {}

    forward_glue = set(rules.get("forward_glue_particles", [
        "ก็", "จะ", "จึง", "ยัง", "มิ", "ไม่", "ได้", "คง", "ย่อม", "ต้อง", "ขอ", "โปรด", "อย่า", "หาก", "ถ้า", "ดั่ง", "ประหนึ่ง", "จึ่ง", "ค่อย"
    ]))
    backward_glue = set(rules.get("backward_glue_particles", [
        "นะ", "ล่ะ", "รึ", "หรือ", "สิ", "จัง", "จ้ะ", "จ๋า", "เลย", "ด้วย", "กัน", "เอง", "ไหม", "มั้ย", "ครับ", "ค่ะ", "คะ", "หรอก", "เถอะ", "น่า", "หวา", "ว่ะ", "ละ", "เนี่ย", "นู่น", "นี่"
    ]))
    custom_compounds = list(rules.get("custom_compound_words", []))
    unbreakable_phrases = list(rules.get("unbreakable_phrases", []))

    all_dict = list(project_dictionary or []) + custom_compounds + unbreakable_phrases
    dictionary = normalize_project_dictionary(all_dict)
    paragraphs = text.split("\n")
    final_tokens = []

    OPENING_PUNCTUATION = set("([{“‘（【")
    CLOSING_PUNCTUATION = set(")]}”’,.!?:;。、，？！）】")

    for i, para in enumerate(paragraphs):
        if i > 0:
            final_tokens.append("\n")
        if not para:
            continue

        protected, mapping = _protect_dictionary_spans(para, dictionary)
        tok_engine = get_thai_tokenizer(dictionary)
        raw_tokens = _merge_thai_words(TOKEN_REGEX.findall(protected), tokenizer=tok_engine)
        raw_tokens = _restore_dictionary_tokens(raw_tokens, mapping)

        # Merge isolated 1-char Thai prefix letters (e.g. ['อ', 'วา...'] -> 'อวา...')
        cleaned_raw = []
        for t in raw_tokens:
            if (
                cleaned_raw
                and len(cleaned_raw[-1]) == 1
                and '\u0e00' <= cleaned_raw[-1] <= '\u0e7f'
                and not cleaned_raw[-1].isspace()
                and not t.isspace()
            ):
                cleaned_raw[-1] += t
            else:
                cleaned_raw.append(t)

        # 1. Punctuation gluing
        punct_glued = []
        for tok in cleaned_raw:
            if tok.isspace():
                if punct_glued and not punct_glued[-1].isspace():
                    punct_glued.append(" ")
                continue
            if not punct_glued:
                punct_glued.append(tok)
                continue

            prev_tok = punct_glued[-1]

            # Glue closing punctuation to preceding token
            if tok in CLOSING_PUNCTUATION and not prev_tok.isspace():
                punct_glued[-1] = prev_tok + tok
            # Glue token to preceding opening punctuation
            elif prev_tok in OPENING_PUNCTUATION:
                punct_glued[-1] = prev_tok + tok
            else:
                # Two-Tier Hierarchical Sub-Tokenization for Long Thai Compounds (len >= 10)
                # Prevents massive tokens from blowing out balloon widths and forcing extreme font downscaling
                if len(tok) >= 10 and re.search(r'[\u0E00-\u0E7F]', tok):
                    sub_parts = []
                    # Leading vowel regex pattern: binds เ, แ, โ, ใ, ไ to consonant
                    syllable_pat = r'(?:[เแโใไ]?[ก-ฮ][\u0E30-\u0E39\u0E47-\u0E4E]*)+'
                    raw_sub = re.findall(syllable_pat, tok)
                    if len(raw_sub) >= 2 and sum(len(s) for s in raw_sub) == len(tok):
                        # Group small 2-3 char syllables into 4-8 char chunks
                        curr_chunk = ""
                        for s in raw_sub:
                            if curr_chunk and len(curr_chunk) + len(s) > 8:
                                sub_parts.append(curr_chunk)
                                curr_chunk = s
                            else:
                                curr_chunk += s
                        if curr_chunk:
                            sub_parts.append(curr_chunk)
                        punct_glued.extend(sub_parts)
                    else:
                        punct_glued.append(tok)
                else:
                    punct_glued.append(tok)

        # 2. Backward particle gluing (e.g. 'อะไร' + 'นะ!?' -> 'อะไรนะ!?')
        # Guard against particle-chaining and giant token bloat:
        # Only glue backward particle if previous token is short (<= 4 chars) and total length <= 8 chars.
        back_glued = []
        for tok in punct_glued:
            core = tok.rstrip(")]}”’,.!?:;。、，？！）】 \t")
            if (
                back_glued
                and core in backward_glue
                and not back_glued[-1].isspace()
                and len(back_glued[-1]) <= 4
                and (len(back_glued[-1]) + len(tok) <= 8)
            ):
                back_glued[-1] += tok
            else:
                back_glued.append(tok)

        # 3. Forward particle gluing (e.g. 'ก็' + 'มี' -> 'ก็มี', 'จะ' + 'ไป' -> 'จะไป')
        forward_glued = []
        idx = 0
        while idx < len(back_glued):
            cur = back_glued[idx]
            if cur.strip() in forward_glue and idx + 1 < len(back_glued):
                next_tok = back_glued[idx + 1]
                if next_tok.isspace() and idx + 2 < len(back_glued):
                    forward_glued.append(cur + " " + back_glued[idx + 2])
                    idx += 3
                else:
                    forward_glued.append(cur + next_tok)
                    idx += 2
            else:
                forward_glued.append(cur)
                idx += 1

        final_tokens.extend(forward_glued)

    return final_tokens

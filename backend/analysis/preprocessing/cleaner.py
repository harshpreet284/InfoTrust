import re
import unicodedata
from typing import Optional

MIN_CLAIM_LENGTH: int = 10
MAX_CLAIM_LENGTH: int = 2000

DISALLOWED_FORMAT_CHARS = frozenset([
    "\u200B",  # Zero-Width Space (ZWSP)
    "\u2060",  # Word Joiner
    "\uFEFF",  # Byte Order Mark (BOM)
    "\u00AD",  # Soft Hyphen (SHY)
    "\u200E",  # Left-to-Right Mark (LRM)
    "\u200F",  # Right-to-Left Mark (RLM)
    "\u202A",  # Left-to-Right Embedding
    "\u202B",  # Right-to-Left Embedding
    "\u202C",  # Pop Directional Formatting
    "\u202D",  # Left-to-Right Override
    "\u202E",  # Right-to-Left Override
    "\u2066",  # Left-to-Right Isolate
    "\u2067",  # Right-to-Left Isolate
    "\u2068",  # First Strong Isolate
    "\u2069",  # Pop Directional Isolate
])

RE_JOINER_RUNS = re.compile(r"[\u200C\u200D]+")
RE_WHITESPACE = re.compile(r"\s+")


class ClaimPreprocessingError(ValueError):
    """Raised when claim text fails validation during preprocessing."""
    pass


def _is_ascii_alnum(c: Optional[str]) -> bool:
    return c is not None and (("a" <= c <= "z") or ("A" <= c <= "Z") or ("0" <= c <= "9"))


def _is_base_emoji(c: Optional[str]) -> bool:
    if c is None:
        return False
    code = ord(c)
    # Emoji / symbols blocks (excluding variation selectors)
    if (
        (0x1F000 <= code <= 0x1FAFF)
        or (0x2600 <= code <= 0x27BF)
        or (0x2300 <= code <= 0x23FF)
        or (0x2B50 <= code <= 0x2B55)
    ):
        return True
    return unicodedata.category(c) in ("So", "Sk")


def _is_non_latin_letter(c: Optional[str]) -> bool:
    if c is None or _is_ascii_alnum(c):
        return False
    return unicodedata.category(c) in ("Lo", "Lm", "Ll", "Lu", "Lt")


def _is_valid_emoji_zwj_context(text: str, start: int, end: int) -> bool:
    """
    Validates that a ZWJ run connects legitimate emoji components.
    A variation selector (U+FE0E or U+FE0F) is allowed preceding the ZWJ
    only if it is attached to a preceding base emoji component.
    A variation selector cannot independently qualify as an emoji component
    nor follow a ZWJ.
    """
    if start <= 0 or end >= len(text):
        return False

    next_c = text[end]
    if not _is_base_emoji(next_c):
        return False

    prev_c = text[start - 1]
    if _is_base_emoji(prev_c):
        return True

    # Check for variation selector attached to a preceding base emoji component
    if ord(prev_c) in (0xFE0E, 0xFE0F):
        if start >= 2 and _is_base_emoji(text[start - 2]):
            return True

    return False


def _sanitize_joiners(text: str) -> str:
    parts = []
    last_idx = 0
    for match in RE_JOINER_RUNS.finditer(text):
        start, end = match.span()
        parts.append(text[last_idx:start])
        last_idx = end

        run = match.group(0)

        # 1. First priority: supported compound emoji sequence
        # Run must consist only of ZWJ (\u200D) in a valid emoji sequence
        if set(run) == {"\u200D"} and _is_valid_emoji_zwj_context(text, start, end):
            parts.append("\u200D")
            continue

        prev_c = text[start - 1] if start > 0 else None
        next_c = text[end] if end < len(text) else None

        # Cannot form any valid sequence at string boundaries
        if prev_c is None or next_c is None:
            continue

        # 2. Second priority: valid non-Latin orthographic word
        # Run must consist only of ZWNJ (\u200C) between non-Latin letters (e.g. Persian/Arabic/Indic)
        if set(run) == {"\u200C"} and _is_non_latin_letter(prev_c) and _is_non_latin_letter(next_c):
            parts.append("\u200C")
            continue

        # 3. All remaining joiner runs are dropped:
        # - Detached variation selectors adjacent to ZWJ
        # - ASCII alphanumeric evasion (v\u200daccine, p\u200cfizer, COVID\u200cواکسن)
        # - Malformed mixed runs (\u200C\u200D, \u200D\u200C)
        # - Isolated joiners adjacent to whitespace or punctuation

    parts.append(text[last_idx:])
    return "".join(parts)


def preprocess_claim_text(text: str) -> str:
    """
    Normalizes, sanitizes, and validates claim text for the AI analysis pipeline.

    Applies:
    1. Type checking (str only).
    2. Unicode normalization (NFKC).
    3. Removal of specifically identified invisible format characters, BiDi controls,
       dangerous control characters (Cc except \t, \n, \r), and surrogate code points.
    4. Deterministic joiner sanitization (preserves ZWJ in compound emojis and ZWNJ
       in non-Latin scripts; removes joiners adjacent to ASCII letters/digits or boundaries).
    5. Normalization of repeated whitespace and trimming of outer margins.
    6. Minimum (10) and maximum (2000) length verification in Python string code points.

    Args:
        text: Raw claim text submitted by user or loaded from database.

    Returns:
        Cleaned, normalized, and validated claim text ready for model inference.

    Raises:
        TypeError: If text is not a string.
        ClaimPreprocessingError: If cleaned text is empty, < 10, or > 2000 code points.
    """
    if not isinstance(text, str):
        raise TypeError(f"Claim text must be a string, got {type(text).__name__}")

    text = unicodedata.normalize("NFKC", text)

    filtered = []
    for c in text:
        if c in DISALLOWED_FORMAT_CHARS:
            continue
        cat = unicodedata.category(c)
        if cat == "Cc" and c not in ("\t", "\n", "\r"):
            continue
        if cat == "Cs":
            continue
        filtered.append(c)
    text = "".join(filtered)

    text = _sanitize_joiners(text)
    text = RE_WHITESPACE.sub(" ", text).strip()

    if not text:
        raise ClaimPreprocessingError("Claim text cannot be empty.")

    length = len(text)
    if length < MIN_CLAIM_LENGTH:
        raise ClaimPreprocessingError(
            f"Claim text too short ({length} characters). Minimum length is {MIN_CLAIM_LENGTH} characters."
        )
    if length > MAX_CLAIM_LENGTH:
        raise ClaimPreprocessingError(
            f"Claim text too long ({length} characters). Maximum length is {MAX_CLAIM_LENGTH} characters."
        )

    return text

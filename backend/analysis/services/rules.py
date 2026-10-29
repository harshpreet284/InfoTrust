"""
Rule-based Validation Layer Service (AI-008).
Applies deterministic heuristics to evaluate claim credibility signals and rule scores
for the InfoTrust Hybrid Credibility Engine.
"""

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

# ---------------------------------------------------------------------------
# Domain Exceptions
# ---------------------------------------------------------------------------


class RuleEngineError(RuntimeError):
    """Base exception for all operational and domain failures in RuleEngineService."""

    pass


class RuleConfigError(RuleEngineError, ValueError):
    """Raised when rule engine configuration (e.g. penalty_per_flag) is invalid."""

    pass


class RuleInputError(RuleEngineError, ValueError):
    """Raised when input text provided to RuleEngineService fails validation."""

    pass


# ---------------------------------------------------------------------------
# Constants & Heuristic Dictionaries
# ---------------------------------------------------------------------------

DEFAULT_PENALTY_PER_FLAG: float = 0.05

VALID_RULE_FLAGS: tuple[str, ...] = (
    "excessive_capitalization",
    "duplicate_punctuation",
    "clickbait_phrases",
    "sensational_language",
    "short_or_vague_claim",
    "spam_patterns",
)

FLAG_OBSERVATIONS: dict[str, str] = {
    "excessive_capitalization": (
        "Excessive capitalization detected (high uppercase ratio or repeated all-caps words)."
    ),
    "duplicate_punctuation": "Duplicate or excessive punctuation marks detected.",
    "clickbait_phrases": "Clickbait phrasing detected.",
    "sensational_language": "Sensational or alarmist language detected.",
    "short_or_vague_claim": "Claim text is very short or vague (four or fewer words).",
    "spam_patterns": "Spam patterns, promotional language, or external links detected.",
}

# Recognized organizational/scientific acronyms to prevent false-positive shouting detection
COMMON_ACRONYMS: frozenset[str] = frozenset(
    {
        "NASA",
        "WHO",
        "CDC",
        "FDA",
        "FBI",
        "CIA",
        "UN",
        "EU",
        "NATO",
        "NIH",
        "COVID",
        "COVID19",
        "USA",
        "UK",
        "US",
        "AI",
        "EPA",
        "DOD",
        "DOJ",
        "SEC",
        "FTC",
        "FCC",
        "IRS",
        "GOP",
        "DNC",
        "IMF",
        "WTO",
        "AP",
        "AFP",
        "BBC",
        "CNN",
    }
)

# Clickbait phrases (case-insensitive)
CLICKBAIT_PHRASES: tuple[str, ...] = (
    "you won't believe",
    "you wont believe",
    "what happened next",
    "this one trick",
    "one weird trick",
    "one simple trick",
    "they don't want you to know",
    "they dont want you to know",
    "will blow your mind",
    "blows your mind",
    "will surprise you",
    "see what happens",
    "watch what happens",
    "what happens when",
    "before it gets taken down",
    "before it is taken down",
    "before it's deleted",
    "before its deleted",
    "doctors hate this",
    "doctors hate him",
    "doctors hate her",
    "the reason why will shock you",
    "shocking reason why",
)

# Sensational keywords and phrases (case-insensitive)
SENSATIONAL_PHRASES: tuple[str, ...] = (
    "secret cure",
    "miracle cure",
    "shocking truth",
    "bombshell",
    "mainstream media won't tell you",
    "mainstream media wont tell you",
    "media is hiding",
    "government is hiding",
    "government hides",
    "wake up sheeple",
    "conspiracy exposed",
    "hidden truth",
    "smoking gun",
    "unbelievable secret",
    "total hoax",
    "100% cure",
    "100% proven cure",
    "censored by big pharma",
    "deep state plot",
)

# Commercial / unsolicited spam marketing phrases (case-insensitive)
SPAM_PHRASES: tuple[str, ...] = (
    "click here",
    "buy now",
    "order now",
    "cash prize",
    "make money fast",
    "100% free",
    "completely free",
    "free gift",
    "act now",
    "limited time offer",
    "earn $$$",
    "earn cash",
    "risk free",
    "risk-free",
    "subscribe now",
    "claim your prize",
    "call now",
)

# Precompiled regular expressions for deterministic heuristic matching
DUPLICATE_PUNCTUATION_PATTERN: re.Pattern = re.compile(r"[!?]{2,}|\.{4,}|[,;]{2,}")
SENSATIONAL_PREFIX_PATTERN: re.Pattern = re.compile(
    r"^\s*(breaking(?:\s+news)?|urgent|alert|exposed)\b", re.IGNORECASE
)
CLICKBAIT_NUMBER_PATTERN: re.Pattern = re.compile(
    r"\bnumber\s+\d+\s+will\s+(shock|amaze|surprise)\b", re.IGNORECASE
)
SPAM_URL_PATTERN: re.Pattern = re.compile(
    r"(https?://\S+|www\.\S+|bit\.ly/\S+|tinyurl\.com/\S+|t\.co/\S+)", re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Domain Data Contracts
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RuleValidationResult:
    """
    Immutable domain output produced by AI-008 (Rule Engine).
    Encapsulates rule-based heuristic flags, credibility penalty, rule score, and observations.
    """

    flags: Mapping[str, bool]
    triggered_count: int
    credibility_penalty: float  # Finite float in [0.0, 1.0]
    rule_score: float  # Finite float in [0.0, 1.0], equals 1.0 - credibility_penalty
    observations: tuple[str, ...]

    def __post_init__(self) -> None:
        # Validate flags mapping
        if isinstance(self.flags, bool) or not isinstance(self.flags, Mapping):
            raise TypeError(
                f"flags must be a dictionary or mapping, got {type(self.flags).__name__}."
            )

        expected_keys = set(VALID_RULE_FLAGS)
        actual_keys = set(self.flags.keys())
        if actual_keys != expected_keys:
            raise RuleInputError(
                f"flags dict must contain exactly the keys: {sorted(expected_keys)}, got: {sorted(actual_keys)}."
            )

        for key, val in self.flags.items():
            if not isinstance(val, bool):
                raise TypeError(
                    f"Flag value for '{key}' must be a boolean, got {type(val).__name__}."
                )

        # Validate triggered_count
        if isinstance(self.triggered_count, bool) or not isinstance(
            self.triggered_count, int
        ):
            raise TypeError(
                f"triggered_count must be an integer, got {type(self.triggered_count).__name__}."
            )
        actual_triggered = sum(1 for val in self.flags.values() if val is True)
        if self.triggered_count != actual_triggered:
            raise RuleEngineError(
                f"triggered_count ({self.triggered_count}) does not match count of True flags ({actual_triggered})."
            )

        # Validate credibility_penalty
        if isinstance(self.credibility_penalty, bool) or not isinstance(
            self.credibility_penalty, (int, float)
        ):
            raise TypeError(
                f"credibility_penalty must be a numeric float, got {type(self.credibility_penalty).__name__}."
            )
        penalty_float = float(self.credibility_penalty)
        if not math.isfinite(penalty_float) or not (0.0 <= penalty_float <= 1.0):
            raise RuleEngineError(
                f"credibility_penalty must be a finite number in range [0.0, 1.0], got {self.credibility_penalty!r}."
            )

        # Validate rule_score
        if isinstance(self.rule_score, bool) or not isinstance(
            self.rule_score, (int, float)
        ):
            raise TypeError(
                f"rule_score must be a numeric float, got {type(self.rule_score).__name__}."
            )
        score_float = float(self.rule_score)
        if not math.isfinite(score_float) or not (0.0 <= score_float <= 1.0):
            raise RuleEngineError(
                f"rule_score must be a finite number in range [0.0, 1.0], got {self.rule_score!r}."
            )

        # Verify mathematical identity: rule_score == 1.0 - credibility_penalty
        if not math.isclose(score_float, 1.0 - penalty_float, abs_tol=1e-5):
            raise RuleEngineError(
                f"rule_score ({score_float}) must equal 1.0 - credibility_penalty ({1.0 - penalty_float})."
            )

        # Validate observations
        if isinstance(self.observations, bool) or not isinstance(
            self.observations, (tuple, list)
        ):
            raise TypeError(
                f"observations must be a sequence of strings, got {type(self.observations).__name__}."
            )
        for obs in self.observations:
            if not isinstance(obs, str):
                raise TypeError(
                    f"Observation item must be a string, got {type(obs).__name__}."
                )

        # Store defensive copies and canonical types on frozen instance
        object.__setattr__(self, "flags", MappingProxyType(dict(self.flags)))
        object.__setattr__(self, "triggered_count", int(self.triggered_count))
        object.__setattr__(self, "credibility_penalty", penalty_float)
        object.__setattr__(self, "rule_score", score_float)
        object.__setattr__(self, "observations", tuple(self.observations))

    @property
    def has_flags(self) -> bool:
        """Derived indicator: True if one or more heuristic flags were triggered."""
        return self.triggered_count > 0

    @property
    def credibility_penalty_percentage(self) -> int:
        """Display helper only: rounded integer percentage in [0, 100]."""
        return int(round(self.credibility_penalty * 100))

    @property
    def rule_score_percentage(self) -> int:
        """Display helper only: rounded integer percentage in [0, 100]."""
        return int(round(self.rule_score * 100))

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-compatible dictionary for inspection, persistence, or logging."""
        return {
            "flags": dict(self.flags),
            "triggered_count": self.triggered_count,
            "credibility_penalty": self.credibility_penalty,
            "rule_score": self.rule_score,
            "observations": list(self.observations),
            "has_flags": self.has_flags,
            "credibility_penalty_percentage": self.credibility_penalty_percentage,
            "rule_score_percentage": self.rule_score_percentage,
        }

    @classmethod
    def empty(cls) -> "RuleValidationResult":
        """Factory for canonical clean result with zero flags triggered."""
        clean_flags = {key: False for key in VALID_RULE_FLAGS}
        return cls(
            flags=clean_flags,
            triggered_count=0,
            credibility_penalty=0.0,
            rule_score=1.0,
            observations=(),
        )


# ---------------------------------------------------------------------------
# Rule Engine Service
# ---------------------------------------------------------------------------


class RuleEngineService:
    """
    Applies deterministic heuristics to evaluate claim text credibility signals.
    Provides pure calculations without external dependencies, LLMs, or network calls.
    """

    def __init__(self, penalty_per_flag: float = DEFAULT_PENALTY_PER_FLAG) -> None:
        """
        Initialize the Rule Engine Service with configurable penalty per triggered flag.

        Args:
            penalty_per_flag: Numeric penalty applied per triggered heuristic flag (default: 0.05).
        """
        if isinstance(penalty_per_flag, bool) or not isinstance(
            penalty_per_flag, (int, float)
        ):
            raise TypeError(
                f"penalty_per_flag must be a numeric float, got {type(penalty_per_flag).__name__}."
            )
        penalty_val = float(penalty_per_flag)
        if not math.isfinite(penalty_val) or not (0.0 <= penalty_val <= 1.0):
            raise RuleConfigError(
                f"penalty_per_flag must be a finite float in [0.0, 1.0], got {penalty_per_flag!r}."
            )
        self.penalty_per_flag: float = penalty_val

    def evaluate(self, claim_text: str) -> RuleValidationResult:
        """
        Evaluate claim text against all heuristic credibility rules.

        Args:
            claim_text: Raw or preprocessed claim string to evaluate.

        Returns:
            RuleValidationResult containing flags, score, penalty, and observations.

        Raises:
            TypeError: If claim_text is not a string.
            RuleInputError: If claim_text is empty or whitespace-only.
        """
        if not isinstance(claim_text, str):
            raise TypeError(
                f"claim_text must be a string, got {type(claim_text).__name__}."
            )

        cleaned_text = claim_text.strip()
        if not cleaned_text:
            raise RuleInputError("claim_text must not be empty or whitespace only.")

        # Evaluate individual heuristic rules
        flags: dict[str, bool] = {
            "excessive_capitalization": self._check_excessive_capitalization(
                cleaned_text
            ),
            "duplicate_punctuation": self._check_duplicate_punctuation(cleaned_text),
            "clickbait_phrases": self._check_clickbait_phrases(cleaned_text),
            "sensational_language": self._check_sensational_language(cleaned_text),
            "short_or_vague_claim": self._check_short_or_vague_claim(cleaned_text),
            "spam_patterns": self._check_spam_patterns(cleaned_text),
        }

        triggered_count = sum(1 for val in flags.values() if val is True)
        raw_penalty = triggered_count * self.penalty_per_flag
        clamped_penalty = round(min(1.0, max(0.0, raw_penalty)), 4)
        calculated_score = round(max(0.0, min(1.0, 1.0 - clamped_penalty)), 4)

        # Build generic, privacy-safe observations for triggered flags
        observations: list[str] = [
            FLAG_OBSERVATIONS[flag_key]
            for flag_key in VALID_RULE_FLAGS
            if flags.get(flag_key) is True
        ]

        return RuleValidationResult(
            flags=flags,
            triggered_count=triggered_count,
            credibility_penalty=clamped_penalty,
            rule_score=calculated_score,
            observations=tuple(observations),
        )

    # -----------------------------------------------------------------------
    # Heuristic Rule Implementations
    # -----------------------------------------------------------------------

    def _check_excessive_capitalization(self, text: str) -> bool:
        """
        Detects excessive shouting or capitalization.
        Triggers if non-acronym uppercase ratio >= 0.40 (with at least 10 letters)
        OR if 3 or more consecutive shouting all-caps words appear.
        """
        words = re.findall(r"\b[A-Za-z0-9_-]+\b", text)

        # Check for 3 or more consecutive shouting all-caps words
        max_consecutive_shouting = 0
        current_consecutive = 0
        for w in words:
            clean_w = re.sub(r"[^A-Za-z]", "", w)
            if (
                len(clean_w) >= 2
                and clean_w.isupper()
                and clean_w not in COMMON_ACRONYMS
            ):
                current_consecutive += 1
                if current_consecutive > max_consecutive_shouting:
                    max_consecutive_shouting = current_consecutive
            else:
                current_consecutive = 0

        if max_consecutive_shouting >= 3:
            return True

        # Check uppercase letter ratio, discounting common acronyms
        alpha_chars = [c for c in text if c.isalpha()]
        total_alpha = len(alpha_chars)
        if total_alpha >= 10:
            acronym_letters_count = sum(
                len(re.sub(r"[^A-Za-z]", "", w))
                for w in words
                if re.sub(r"[^A-Za-z]", "", w).upper() in COMMON_ACRONYMS
            )
            upper_count = sum(1 for c in alpha_chars if c.isupper())
            non_acronym_upper = max(0, upper_count - acronym_letters_count)
            non_acronym_total = max(1, total_alpha - acronym_letters_count)

            if (
                upper_count / total_alpha >= 0.40
                and non_acronym_upper / non_acronym_total >= 0.40
            ):
                return True

        return False

    def _check_duplicate_punctuation(self, text: str) -> bool:
        """
        Detects repeated punctuation runs (e.g. '!!', '???', '!?!', '....', ',,').
        Allows standard single punctuation and standard 3-dot ellipsis ('...').
        """
        return DUPLICATE_PUNCTUATION_PATTERN.search(text) is not None

    def _check_clickbait_phrases(self, text: str) -> bool:
        """
        Detects common clickbait phrases and patterns.
        """
        lower_text = text.lower()
        if any(phrase in lower_text for phrase in CLICKBAIT_PHRASES):
            return True
        if CLICKBAIT_NUMBER_PATTERN.search(lower_text) is not None:
            return True
        return False

    def _check_sensational_language(self, text: str) -> bool:
        """
        Detects sensational language or alarmist breaking headline prefixes.
        """
        lower_text = text.lower()
        if SENSATIONAL_PREFIX_PATTERN.search(text) is not None:
            return True
        if any(phrase in lower_text for phrase in SENSATIONAL_PHRASES):
            return True
        return False

    def _check_short_or_vague_claim(self, text: str) -> bool:
        """
        Detects claims that are too brief or vague to evaluate meaningfully.
        Triggers if tokenized claim contains 4 or fewer whitespace-separated words.
        """
        tokens = text.split()
        return len(tokens) <= 4

    def _check_spam_patterns(self, text: str) -> bool:
        """
        Detects unsolicited promotional language, marketing links, or spam patterns.
        """
        if SPAM_URL_PATTERN.search(text) is not None:
            return True
        lower_text = text.lower()
        if any(phrase in lower_text for phrase in SPAM_PHRASES):
            return True
        return False

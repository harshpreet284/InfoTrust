"""
Hybrid Credibility Engine Service (AI-009).
Aggregates heterogeneous signals from fine-tuned model inference (AI-004),
external fact-checking evidence (AI-005), narrative activity metadata (AI-006),
and rule-based validation heuristics (AI-008) into a unified, evidence-based
credibility assessment score and component manifest.
"""

import math
import re
import urllib.parse
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, Optional

from django.conf import settings

from analysis.inference.adapter import ModelOutput
from analysis.models import ModelPrediction
from analysis.services.fact_check import FactCheckEvidenceItem, FactCheckResult
from analysis.services.narrative import NarrativeActivity
from analysis.services.rules import RuleValidationResult

# ---------------------------------------------------------------------------
# Domain Exceptions
# ---------------------------------------------------------------------------


class HybridEngineError(RuntimeError):
    """Base exception for all operational and domain failures in HybridCredibilityEngine."""

    pass


class HybridConfigError(HybridEngineError, ValueError):
    """Raised when hybrid engine configuration (e.g. weights) is invalid."""

    pass


class HybridInputError(HybridEngineError, ValueError):
    """Raised when input provided to HybridCredibilityEngine fails contract validation."""

    pass


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SignalStatus(str, Enum):
    """Status of an individual component signal evaluated by the hybrid engine."""

    AVAILABLE = "AVAILABLE"
    NO_EVIDENCE = "NO_EVIDENCE"
    FAILED = "FAILED"
    UNSCORABLE = "UNSCORABLE"


class HybridAnalysisStatus(str, Enum):
    """Overall outcome status of the hybrid credibility aggregation pipeline."""

    COMPLETED = "COMPLETED"
    PARTIAL_FAILURE = "PARTIAL_FAILURE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_WEIGHT_MODEL: float = 0.35
DEFAULT_WEIGHT_FACT_CHECK: float = 0.40
DEFAULT_WEIGHT_NARRATIVE: float = 0.15
DEFAULT_WEIGHT_RULE_ENGINE: float = 0.10

COMPONENT_MODEL: str = "model"
COMPONENT_FACT_CHECK: str = "fact_check"
COMPONENT_NARRATIVE: str = "narrative"
COMPONENT_RULE_ENGINE: str = "rule_engine"

ALL_COMPONENTS: tuple[str, ...] = (
    COMPONENT_MODEL,
    COMPONENT_FACT_CHECK,
    COMPONENT_NARRATIVE,
    COMPONENT_RULE_ENGINE,
)

PRIMARY_TRUTH_COMPONENTS: frozenset[str] = frozenset(
    {COMPONENT_MODEL, COMPONENT_FACT_CHECK}
)

VALID_CONFIDENCE_LEVELS: frozenset[str] = frozenset({"HIGH", "MEDIUM", "LOW", "NONE"})


# ---------------------------------------------------------------------------
# Fact-Check Rating Normalization
# ---------------------------------------------------------------------------


def normalize_fact_check_rating(rating: Optional[str]) -> Optional[float]:
    """
    Deterministically maps external fact-check publisher rating strings to a
    normalized credibility float in [0.0, 1.0], or returns None if unscorable.

    Mapping Rules:
    - Negations checked first ("not true" -> 0.0, "not false" -> 1.0)
    - "mostly true" / "largely true" -> 0.80
    - "partially true" / "half true" -> 0.50
    - "mostly false" / "partially false" -> 0.20
    - "false", "pants on fire", "four pinocchios" -> 0.0
    - "true", "correct", "verified", "confirmed" -> 1.0
    - Ambiguous, contradictory, or unsupported ratings -> None (UNSCORABLE)
    """
    if rating is None or not isinstance(rating, str):
        return None

    cleaned = re.sub(r"[^\w\s-]", " ", rating.strip().lower())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return None

    # 1. Multi-word Negations
    if re.search(r"\bnot\s+(true|correct|accurate|verified|confirmed)\b", cleaned):
        return 0.0
    if re.search(r"\bnot\s+(false|incorrect|inaccurate)\b", cleaned):
        return 1.0

    # 2. Bounded phrases for 0.80 ("mostly true")
    if re.search(
        r"\b(mostly\s+true|largely\s+true|primarily\s+true|mostly\s+accurate|largely\s+accurate|mostly\s+correct)\b",
        cleaned,
    ):
        return 0.80

    # 3. Bounded phrases for 0.20 ("mostly false" / "partially false")
    if re.search(
        r"\b(mostly\s+false|largely\s+false|partially\s+false|partly\s+false|mostly\s+incorrect|largely\s+incorrect|mostly\s+inaccurate|largely\s+inaccurate)\b",
        cleaned,
    ):
        return 0.20

    # 4. Bounded phrases for 0.50 ("partially true" / "half true")
    if re.search(
        r"\b(half\s+true|partially\s+true|partly\s+true|half-true|somewhat\s+true|in-between|mixture|mixed|partially\s+accurate|partly\s+accurate|partially\s+correct|partly\s+correct)\b",
        cleaned,
    ):
        return 0.50

    # 5. Idiomatic phrases for 0.0 ("pants on fire", pinocchios)
    if re.search(
        r"\b(pants\s+on\s+fire|(?:four|4|three|3)\s+pinocchios)\b",
        cleaned,
    ):
        return 0.0

    # 6. Check for contradictory root tokens without clear qualifier
    # e.g., contains both "true" and "false" like "true that it was false"
    has_true_token = bool(re.search(r"\b(true|correct|accurate)\b", cleaned))
    has_false_token = bool(
        re.search(r"\b(false|incorrect|inaccurate|fake|misleading)\b", cleaned)
    )
    if has_true_token and has_false_token:
        return None

    # 7. Single token anchors
    if re.search(
        r"\b(false|incorrect|inaccurate|debunked|fake|fabricated|untrue|misleading|wrong|hoax)\b",
        cleaned,
    ):
        return 0.0

    if re.search(r"\b(true|correct|accurate|verified|confirmed)\b", cleaned):
        return 1.0

    # 8. Unmatched / Ambiguous / Unsupported descriptive ratings -> UNSCORABLE
    return None


# ---------------------------------------------------------------------------
# Data Contracts
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScoredFactCheckItem:
    """
    Individual external fact-check item with its normalized numeric rating.
    Preserves original publisher name and raw rating string for explainability.
    """

    publisher: str
    raw_rating: str
    normalized_score: Optional[float]
    is_scorable: bool
    url: str

    def __post_init__(self) -> None:
        if isinstance(self.publisher, bool) or not isinstance(self.publisher, str):
            raise TypeError("publisher must be a string")
        if isinstance(self.raw_rating, bool) or not isinstance(self.raw_rating, str):
            raise TypeError("raw_rating must be a string")
        if isinstance(self.url, bool) or not isinstance(self.url, str):
            raise TypeError("url must be a string")

        if self.is_scorable:
            if isinstance(self.normalized_score, bool) or not isinstance(
                self.normalized_score, (int, float)
            ):
                raise TypeError(
                    "normalized_score must be a float when is_scorable is True"
                )
            if not math.isfinite(self.normalized_score):
                raise ValueError("normalized_score must be finite")
            if not (0.0 <= float(self.normalized_score) <= 1.0):
                raise ValueError("normalized_score must be between 0.0 and 1.0")
        else:
            if self.normalized_score is not None:
                raise ValueError(
                    "normalized_score must be None when is_scorable is False"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "publisher": self.publisher,
            "raw_rating": self.raw_rating,
            "normalized_score": (
                float(self.normalized_score)
                if self.normalized_score is not None
                else None
            ),
            "is_scorable": self.is_scorable,
            "url": self.url,
        }


@dataclass(frozen=True)
class ComponentSignal:
    """Detailed manifest record for an individual component's participation."""

    name: str
    status: SignalStatus
    raw_score: Optional[float]
    configured_weight: float
    effective_weight: float
    weighted_contribution: float
    error_message: Optional[str] = None

    def __post_init__(self) -> None:
        if self.name not in ALL_COMPONENTS:
            raise ValueError(f"Unknown component name: {self.name}")
        if not isinstance(self.status, SignalStatus):
            raise TypeError("status must be an instance of SignalStatus")
        if self.raw_score is not None:
            if isinstance(self.raw_score, bool) or not isinstance(
                self.raw_score, (int, float)
            ):
                raise TypeError("raw_score must be a float or None")
            if not math.isfinite(self.raw_score) or not (
                0.0 <= float(self.raw_score) <= 1.0
            ):
                raise ValueError("raw_score must be a finite float in [0.0, 1.0]")
        if isinstance(self.configured_weight, bool) or not isinstance(
            self.configured_weight, (int, float)
        ):
            raise TypeError("configured_weight must be a float")
        if not math.isfinite(self.configured_weight) or not (
            0.0 <= float(self.configured_weight) <= 1.0
        ):
            raise ValueError("configured_weight must be in [0.0, 1.0]")
        if isinstance(self.effective_weight, bool) or not isinstance(
            self.effective_weight, (int, float)
        ):
            raise TypeError("effective_weight must be a float")
        if not math.isfinite(self.effective_weight) or not (
            0.0 <= float(self.effective_weight) <= 1.0
        ):
            raise ValueError("effective_weight must be in [0.0, 1.0]")
        if isinstance(self.weighted_contribution, bool) or not isinstance(
            self.weighted_contribution, (int, float)
        ):
            raise TypeError("weighted_contribution must be a float")
        if not math.isfinite(self.weighted_contribution):
            raise ValueError("weighted_contribution must be finite")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "raw_score": (
                float(self.raw_score) if self.raw_score is not None else None
            ),
            "configured_weight": float(self.configured_weight),
            "effective_weight": float(self.effective_weight),
            "weighted_contribution": float(self.weighted_contribution),
            "error_message": self.error_message,
        }


@dataclass(frozen=True)
class HybridCredibilityResult:
    """
    Immutable domain output produced by AI-009 (Hybrid Credibility Engine).
    Encapsulates final credibility score, component weights, contributions,
    statuses, failure logs, and explainability context.
    """

    credibility_score: Optional[float]
    overall_status: HybridAnalysisStatus
    confidence_level: str
    coverage_ratio: float
    component_scores: Mapping[str, Optional[float]]
    effective_weights: Mapping[str, float]
    weighted_contributions: Mapping[str, float]
    signal_statuses: Mapping[str, SignalStatus]
    failed_components: tuple[str, ...]
    error_details: Mapping[str, str]
    fact_check_conflict: bool
    narrative_context: Optional[Mapping[str, Any]] = None

    def __post_init__(self) -> None:
        # Enforce defensive copies and read-only proxy wrappers
        object.__setattr__(
            self,
            "component_scores",
            MappingProxyType(dict(self.component_scores)),
        )
        object.__setattr__(
            self,
            "effective_weights",
            MappingProxyType({k: float(v) for k, v in self.effective_weights.items()}),
        )
        object.__setattr__(
            self,
            "weighted_contributions",
            MappingProxyType(
                {k: float(v) for k, v in self.weighted_contributions.items()}
            ),
        )
        object.__setattr__(
            self,
            "signal_statuses",
            MappingProxyType(dict(self.signal_statuses)),
        )
        object.__setattr__(
            self,
            "failed_components",
            tuple(sorted(self.failed_components)),
        )
        object.__setattr__(
            self,
            "error_details",
            MappingProxyType(dict(self.error_details)),
        )
        if self.narrative_context is not None:
            object.__setattr__(
                self,
                "narrative_context",
                MappingProxyType(dict(self.narrative_context)),
            )

        # Invariant validations
        if not isinstance(self.overall_status, HybridAnalysisStatus):
            raise TypeError(
                f"overall_status must be HybridAnalysisStatus, got {type(self.overall_status).__name__}"
            )

        if self.confidence_level not in VALID_CONFIDENCE_LEVELS:
            raise ValueError(
                f"confidence_level must be one of {sorted(VALID_CONFIDENCE_LEVELS)}, got {self.confidence_level}"
            )

        if isinstance(self.coverage_ratio, bool) or not isinstance(
            self.coverage_ratio, (int, float)
        ):
            raise TypeError("coverage_ratio must be a float")
        if not math.isfinite(self.coverage_ratio) or not (
            0.0 <= float(self.coverage_ratio) <= 1.0
        ):
            raise ValueError(
                f"coverage_ratio must be between 0.0 and 1.0, got {self.coverage_ratio}"
            )

        if isinstance(self.fact_check_conflict, bool) is False:
            raise TypeError("fact_check_conflict must be a strict boolean")

        # Invariants regarding credibility_score
        if self.credibility_score is None:
            if self.overall_status != HybridAnalysisStatus.INSUFFICIENT_EVIDENCE:
                raise ValueError(
                    "overall_status must be INSUFFICIENT_EVIDENCE when credibility_score is None"
                )
            if self.confidence_level != "NONE":
                raise ValueError(
                    "confidence_level must be 'NONE' when credibility_score is None"
                )
        else:
            if isinstance(self.credibility_score, bool) or not isinstance(
                self.credibility_score, (int, float)
            ):
                raise TypeError("credibility_score must be a float or None")
            if not math.isfinite(self.credibility_score):
                raise ValueError("credibility_score must be a finite float")
            if not (0.0 <= float(self.credibility_score) <= 100.0):
                raise ValueError(
                    f"credibility_score must be in [0.0, 100.0], got {self.credibility_score}"
                )
            if self.overall_status not in (
                HybridAnalysisStatus.COMPLETED,
                HybridAnalysisStatus.PARTIAL_FAILURE,
            ):
                raise ValueError(
                    "overall_status must be COMPLETED or PARTIAL_FAILURE when credibility_score is present"
                )
            if self.confidence_level not in {"HIGH", "MEDIUM", "LOW"}:
                raise ValueError(
                    f"confidence_level must be HIGH, MEDIUM, or LOW when credibility_score is present, got {self.confidence_level}"
                )

        # Validate failed_components consistency
        actual_failed = tuple(
            sorted(
                k
                for k, status in self.signal_statuses.items()
                if status == SignalStatus.FAILED
            )
        )
        if self.failed_components != actual_failed:
            raise ValueError(
                f"failed_components {self.failed_components} does not match failed signals {actual_failed}"
            )

    def to_dict(self) -> dict[str, Any]:
        """Returns an independent, mutable, JSON-serializable dictionary representation."""
        return {
            "credibility_score": (
                float(self.credibility_score)
                if self.credibility_score is not None
                else None
            ),
            "overall_status": self.overall_status.value,
            "confidence_level": self.confidence_level,
            "coverage_ratio": float(self.coverage_ratio),
            "component_scores": {
                k: float(v) if v is not None else None
                for k, v in self.component_scores.items()
            },
            "effective_weights": {
                k: float(v) for k, v in self.effective_weights.items()
            },
            "weighted_contributions": {
                k: float(v) for k, v in self.weighted_contributions.items()
            },
            "signal_statuses": {
                k: v.value if isinstance(v, SignalStatus) else str(v)
                for k, v in self.signal_statuses.items()
            },
            "failed_components": list(self.failed_components),
            "error_details": dict(self.error_details),
            "fact_check_conflict": self.fact_check_conflict,
            "narrative_context": (
                dict(self.narrative_context)
                if self.narrative_context is not None
                else None
            ),
        }


# ---------------------------------------------------------------------------
# Hybrid Credibility Engine Service
# ---------------------------------------------------------------------------


class HybridCredibilityEngine:
    """
    Coordinates multi-signal credibility aggregation across ML inference,
    fact-checking evidence, rule-based heuristics, and narrative activity.
    """

    def __init__(
        self,
        model_weight: Optional[float] = None,
        fact_check_weight: Optional[float] = None,
        narrative_weight: Optional[float] = None,
        rule_engine_weight: Optional[float] = None,
    ) -> None:
        """
        Initializes the hybrid credibility engine with configurable weights.
        Weights default to Django settings if available, else module defaults.
        """
        w_m = (
            model_weight
            if model_weight is not None
            else getattr(settings, "HYBRID_WEIGHT_MODEL", DEFAULT_WEIGHT_MODEL)
        )
        w_f = (
            fact_check_weight
            if fact_check_weight is not None
            else getattr(
                settings, "HYBRID_WEIGHT_FACT_CHECK", DEFAULT_WEIGHT_FACT_CHECK
            )
        )
        w_n = (
            narrative_weight
            if narrative_weight is not None
            else getattr(settings, "HYBRID_WEIGHT_NARRATIVE", DEFAULT_WEIGHT_NARRATIVE)
        )
        w_r = (
            rule_engine_weight
            if rule_engine_weight is not None
            else getattr(
                settings,
                "HYBRID_WEIGHT_RULE_ENGINE",
                DEFAULT_WEIGHT_RULE_ENGINE,
            )
        )

        weights = {
            COMPONENT_MODEL: w_m,
            COMPONENT_FACT_CHECK: w_f,
            COMPONENT_NARRATIVE: w_n,
            COMPONENT_RULE_ENGINE: w_r,
        }

        for comp, w in weights.items():
            if isinstance(w, bool) or not isinstance(w, (int, float)):
                raise HybridConfigError(
                    f"Weight for '{comp}' must be a numeric float, got {type(w).__name__}"
                )
            if not math.isfinite(w):
                raise HybridConfigError(
                    f"Weight for '{comp}' must be a finite float, got {w}"
                )
            if not (0.0 <= float(w) <= 1.0):
                raise HybridConfigError(
                    f"Weight for '{comp}' must be between 0.0 and 1.0, got {w}"
                )

        total_weight = sum(float(w) for w in weights.values())
        if abs(total_weight - 1.0) > 1e-4:
            raise HybridConfigError(
                f"Component weights must sum to 1.0 (got {total_weight:.4f})"
            )

        self._configured_weights: dict[str, float] = {
            comp: float(weights[comp]) for comp in ALL_COMPONENTS
        }

    @property
    def configured_weights(self) -> Mapping[str, float]:
        """Returns a read-only mapping of configured component weights."""
        return MappingProxyType(dict(self._configured_weights))

    def normalize_fact_checks(
        self,
        fact_check_result: FactCheckResult,
    ) -> tuple[tuple[ScoredFactCheckItem, ...], Optional[float], bool, SignalStatus]:
        """
        Normalizes fact check evidence items by:
        1. Deduplicating publisher domains (keeping latest review)
        2. Normalizing publisher rating strings
        3. Detecting review conflict (rating variance >= 0.50)
        4. Computing mean normalized score of scorable reviews
        """
        if not isinstance(fact_check_result, FactCheckResult):
            raise HybridInputError(
                f"fact_check_result must be a FactCheckResult instance, got {type(fact_check_result).__name__}"
            )

        if fact_check_result.matches == 0 or not fact_check_result.sources:
            return (), None, False, SignalStatus.NO_EVIDENCE

        # Group sources by publisher domain heuristic
        grouped: dict[str, list[FactCheckEvidenceItem]] = {}
        for item in fact_check_result.sources:
            if not isinstance(item, FactCheckEvidenceItem):
                continue
            parsed = urllib.parse.urlparse(item.url)
            domain = parsed.netloc.lower()
            if domain.startswith("www."):
                domain = domain[4:]
            key = domain if domain else item.publisher.strip().lower()
            grouped.setdefault(key, []).append(item)

        # Deduplicate: pick latest review per domain
        deduplicated: list[FactCheckEvidenceItem] = []
        for key in sorted(grouped.keys()):
            items = grouped[key]

            def _sort_key(ev: FactCheckEvidenceItem) -> tuple[int, str]:
                if ev.review_date and ev.review_date.strip():
                    return (1, ev.review_date.strip())
                return (0, "")

            # Sort descending: item with date > item without date; newer date > older
            sorted_items = sorted(items, key=_sort_key, reverse=True)
            deduplicated.append(sorted_items[0])

        scored_items: list[ScoredFactCheckItem] = []
        scorable_scores: list[float] = []

        for item in deduplicated:
            norm_score = normalize_fact_check_rating(item.rating)
            is_scorable = norm_score is not None
            scored_item = ScoredFactCheckItem(
                publisher=item.publisher,
                raw_rating=item.rating,
                normalized_score=norm_score,
                is_scorable=is_scorable,
                url=item.url,
            )
            scored_items.append(scored_item)
            if is_scorable:
                scorable_scores.append(norm_score)

        if not scorable_scores:
            return (
                tuple(scored_items),
                None,
                False,
                SignalStatus.UNSCORABLE,
            )

        conflict_detected = False
        if len(scorable_scores) >= 2:
            spread = max(scorable_scores) - min(scorable_scores)
            if spread >= 0.50:
                conflict_detected = True

        avg_score = sum(scorable_scores) / len(scorable_scores)
        return (
            tuple(scored_items),
            avg_score,
            conflict_detected,
            SignalStatus.AVAILABLE,
        )

    def aggregate(
        self,
        *,
        model_output: Optional[ModelOutput] = None,
        fact_check_result: Optional[FactCheckResult] = None,
        rule_validation_result: Optional[RuleValidationResult] = None,
        narrative_activity: Optional[NarrativeActivity] = None,
        model_error: Optional[Any] = None,
        fact_check_error: Optional[Any] = None,
        rule_error: Optional[Any] = None,
        narrative_error: Optional[Any] = None,
    ) -> HybridCredibilityResult:
        """
        Aggregates available signals according to the approved AI-009 policy.

        Constraints:
        - Narrative is retained at its configured weight (0.15) but marked UNSCORABLE
          for truth aggregation (Interim Option 3).
        - At least one primary truth signal (model or fact_check) must be usable
          to calculate a numeric credibility_score; otherwise INSUFFICIENT_EVIDENCE.
        - Raw aggregation calculates full-precision weighted sum and rounds final
          credibility_score only once to 1 decimal place.
        """
        # Type validations on input objects
        if model_output is not None and not isinstance(model_output, ModelOutput):
            raise HybridInputError(
                f"model_output must be a ModelOutput instance, got {type(model_output).__name__}"
            )
        if fact_check_result is not None and not isinstance(
            fact_check_result, FactCheckResult
        ):
            raise HybridInputError(
                f"fact_check_result must be a FactCheckResult instance, got {type(fact_check_result).__name__}"
            )
        if rule_validation_result is not None and not isinstance(
            rule_validation_result, RuleValidationResult
        ):
            raise HybridInputError(
                f"rule_validation_result must be a RuleValidationResult instance, got {type(rule_validation_result).__name__}"
            )
        if narrative_activity is not None and not isinstance(
            narrative_activity, NarrativeActivity
        ):
            raise HybridInputError(
                f"narrative_activity must be a NarrativeActivity instance, got {type(narrative_activity).__name__}"
            )

        signal_statuses: dict[str, SignalStatus] = {}
        raw_scores: dict[str, Optional[float]] = {}
        error_details: dict[str, str] = {}
        fact_check_conflict = False
        narrative_context: Optional[dict[str, Any]] = None

        # -------------------------------------------------------------------
        # 1. Evaluate Model Signal
        # -------------------------------------------------------------------
        if model_error is not None:
            signal_statuses[COMPONENT_MODEL] = SignalStatus.FAILED
            raw_scores[COMPONENT_MODEL] = None
            error_details[COMPONENT_MODEL] = str(model_error)
        elif model_output is not None:
            if model_output.prediction == ModelPrediction.CREDIBLE:
                raw_scores[COMPONENT_MODEL] = float(model_output.confidence)
            elif model_output.prediction == ModelPrediction.MISINFORMATION:
                raw_scores[COMPONENT_MODEL] = 1.0 - float(model_output.confidence)
            else:
                raise HybridInputError(
                    f"Unexpected model prediction: {model_output.prediction}"
                )
            signal_statuses[COMPONENT_MODEL] = SignalStatus.AVAILABLE
        else:
            signal_statuses[COMPONENT_MODEL] = SignalStatus.NO_EVIDENCE
            raw_scores[COMPONENT_MODEL] = None

        # -------------------------------------------------------------------
        # 2. Evaluate Fact-Check Signal
        # -------------------------------------------------------------------
        if fact_check_error is not None:
            signal_statuses[COMPONENT_FACT_CHECK] = SignalStatus.FAILED
            raw_scores[COMPONENT_FACT_CHECK] = None
            error_details[COMPONENT_FACT_CHECK] = str(fact_check_error)
        elif fact_check_result is not None:
            (
                _scored_items,
                fc_score,
                fc_conflict,
                fc_status,
            ) = self.normalize_fact_checks(fact_check_result)
            signal_statuses[COMPONENT_FACT_CHECK] = fc_status
            raw_scores[COMPONENT_FACT_CHECK] = fc_score
            fact_check_conflict = fc_conflict
        else:
            signal_statuses[COMPONENT_FACT_CHECK] = SignalStatus.NO_EVIDENCE
            raw_scores[COMPONENT_FACT_CHECK] = None

        # -------------------------------------------------------------------
        # 3. Evaluate Rule Engine Signal
        # -------------------------------------------------------------------
        if rule_error is not None:
            signal_statuses[COMPONENT_RULE_ENGINE] = SignalStatus.FAILED
            raw_scores[COMPONENT_RULE_ENGINE] = None
            error_details[COMPONENT_RULE_ENGINE] = str(rule_error)
        elif rule_validation_result is not None:
            signal_statuses[COMPONENT_RULE_ENGINE] = SignalStatus.AVAILABLE
            raw_scores[COMPONENT_RULE_ENGINE] = float(rule_validation_result.rule_score)
        else:
            signal_statuses[COMPONENT_RULE_ENGINE] = SignalStatus.NO_EVIDENCE
            raw_scores[COMPONENT_RULE_ENGINE] = None

        # -------------------------------------------------------------------
        # 4. Evaluate Narrative Signal (Interim Option 3)
        # -------------------------------------------------------------------
        if narrative_error is not None:
            signal_statuses[COMPONENT_NARRATIVE] = SignalStatus.FAILED
            raw_scores[COMPONENT_NARRATIVE] = None
            error_details[COMPONENT_NARRATIVE] = str(narrative_error)
        elif narrative_activity is not None:
            # Under interim Option 3: narrative is retained at configured weight
            # but marked UNSCORABLE for truth score aggregation.
            signal_statuses[COMPONENT_NARRATIVE] = SignalStatus.UNSCORABLE
            raw_scores[COMPONENT_NARRATIVE] = None
            narrative_context = narrative_activity.to_dict()
        else:
            signal_statuses[COMPONENT_NARRATIVE] = SignalStatus.NO_EVIDENCE
            raw_scores[COMPONENT_NARRATIVE] = None

        # -------------------------------------------------------------------
        # 5. Determine Usable Signals & Minimum Primary Truth Signal Check
        # -------------------------------------------------------------------
        usable_components = [
            comp
            for comp in ALL_COMPONENTS
            if signal_statuses[comp] == SignalStatus.AVAILABLE
            and raw_scores[comp] is not None
        ]

        has_primary_truth = any(
            comp in usable_components for comp in PRIMARY_TRUTH_COMPONENTS
        )

        effective_weights: dict[str, float] = {comp: 0.0 for comp in ALL_COMPONENTS}
        weighted_contributions: dict[str, float] = {
            comp: 0.0 for comp in ALL_COMPONENTS
        }

        # Coverage ratio: sum of configured weights for usable signals
        coverage_ratio = sum(
            self._configured_weights[comp] for comp in usable_components
        )

        has_failed_component = any(
            status == SignalStatus.FAILED for status in signal_statuses.values()
        )

        if not has_primary_truth or not usable_components:
            # Rules-only, narrative-only, or no signals usable
            credibility_score = None
            overall_status = HybridAnalysisStatus.INSUFFICIENT_EVIDENCE
            confidence_level = "NONE"
        else:
            # Renormalize weights among usable components
            for comp in usable_components:
                effective_weights[comp] = (
                    self._configured_weights[comp] / coverage_ratio
                )

            # Raw unrounded calculation
            raw_score = 100.0 * sum(
                effective_weights[comp] * raw_scores[comp] for comp in usable_components
            )
            clamped_score = max(0.0, min(100.0, raw_score))
            credibility_score = round(clamped_score, 1)

            # Displayed contributions rounded independently to 2 decimal places
            for comp in usable_components:
                weighted_contributions[comp] = round(
                    100.0 * effective_weights[comp] * raw_scores[comp], 2
                )

            # Overall status
            if has_failed_component:
                overall_status = HybridAnalysisStatus.PARTIAL_FAILURE
            else:
                overall_status = HybridAnalysisStatus.COMPLETED

            # Confidence level determination
            if coverage_ratio >= 0.75:
                confidence_level = "LOW" if fact_check_conflict else "HIGH"
            elif coverage_ratio >= 0.35:
                confidence_level = "LOW" if fact_check_conflict else "MEDIUM"
            else:
                confidence_level = "LOW"

        failed_components = tuple(
            comp
            for comp in ALL_COMPONENTS
            if signal_statuses[comp] == SignalStatus.FAILED
        )

        return HybridCredibilityResult(
            credibility_score=credibility_score,
            overall_status=overall_status,
            confidence_level=confidence_level,
            coverage_ratio=coverage_ratio,
            component_scores=raw_scores,
            effective_weights=effective_weights,
            weighted_contributions=weighted_contributions,
            signal_statuses=signal_statuses,
            failed_components=failed_components,
            error_details=error_details,
            fact_check_conflict=fact_check_conflict,
            narrative_context=narrative_context,
        )

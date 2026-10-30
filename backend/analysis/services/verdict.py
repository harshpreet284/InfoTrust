"""
Verdict Generation Service (AI-010).
Evaluates credibility assessment results from AI-009 (HybridCredibilityResult)
and produces standardized, explainable credibility verdicts.
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Optional

from django.conf import settings

from analysis.models import Verdict
from analysis.services.hybrid import HybridAnalysisStatus, HybridCredibilityResult

# ---------------------------------------------------------------------------
# Domain Exceptions
# ---------------------------------------------------------------------------


class VerdictEngineError(RuntimeError):
    """Base exception for all operational and domain failures in VerdictService."""

    pass


class VerdictConfigError(VerdictEngineError, ValueError):
    """Raised when threshold configuration is invalid, inverted, or out of bounds."""

    pass


class VerdictInputError(VerdictEngineError, ValueError):
    """Raised when input provided to VerdictService is malformed or violates contract invariants."""

    pass


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_THRESHOLD_CREDIBLE: float = 70.0
DEFAULT_THRESHOLD_UNCERTAIN: float = 40.0

LABEL_CREDIBLE: str = "Likely Credible"
LABEL_UNCERTAIN: str = "Uncertain"
LABEL_MISINFORMATION: str = "Likely Misinformation"

VALID_CONFIDENCE_LEVELS: frozenset[str] = frozenset({"HIGH", "MEDIUM", "LOW", "NONE"})


# ---------------------------------------------------------------------------
# Domain Data Contract
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VerdictResult:
    """
    Immutable domain output produced by AI-010 (Verdict Generation).
    Encapsulates final standardized verdict, human-readable label, score, confidence,
    status, diagnostic traces, and deterministic explanation.
    """

    verdict: Verdict
    label: str
    credibility_score: Optional[float]
    confidence_level: str
    overall_status: HybridAnalysisStatus
    is_definitive: bool
    thresholds: Mapping[str, float]
    reason: str
    failed_components: tuple[str, ...]
    error_details: Mapping[str, str]
    fact_check_conflict: bool

    def __post_init__(self) -> None:
        # Validate thresholds mapping
        if isinstance(self.thresholds, bool) or not isinstance(
            self.thresholds, Mapping
        ):
            raise TypeError("thresholds must be a dictionary or Mapping.")

        expected_keys = {"credible", "uncertain"}
        actual_keys = set(self.thresholds.keys())
        if actual_keys != expected_keys:
            raise VerdictConfigError(
                f"thresholds mapping must contain exactly keys {sorted(expected_keys)}, got {sorted(actual_keys)}."
            )

        for k in ("credible", "uncertain"):
            val = self.thresholds[k]
            if isinstance(val, bool) or not isinstance(val, (int, float)):
                raise VerdictConfigError(
                    f"threshold '{k}' must be a numeric float, got {type(val).__name__}."
                )
            if not math.isfinite(val):
                raise VerdictConfigError(
                    f"threshold '{k}' must be a finite number, got {val}."
                )
            if not (0.0 <= float(val) <= 100.0):
                raise VerdictConfigError(
                    f"threshold '{k}' must be between 0.0 and 100.0, got {val}."
                )

        credible_val = float(self.thresholds["credible"])
        uncertain_val = float(self.thresholds["uncertain"])
        if credible_val <= uncertain_val:
            raise VerdictConfigError(
                f"credible threshold ({credible_val}) must be strictly greater than "
                f"uncertain threshold ({uncertain_val})."
            )

        # Enforce defensive copies and read-only proxy wrappers
        object.__setattr__(
            self,
            "thresholds",
            MappingProxyType({"credible": credible_val, "uncertain": uncertain_val}),
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

        # Invariant validations
        if not isinstance(self.verdict, Verdict):
            raise TypeError(
                f"verdict must be an instance of Verdict, got {type(self.verdict).__name__}."
            )

        if not isinstance(self.label, str) or not self.label.strip():
            raise TypeError("label must be a non-empty string.")

        if not isinstance(self.overall_status, HybridAnalysisStatus):
            raise TypeError(
                f"overall_status must be HybridAnalysisStatus, got {type(self.overall_status).__name__}."
            )

        if self.confidence_level not in VALID_CONFIDENCE_LEVELS:
            raise ValueError(
                f"confidence_level must be one of {sorted(VALID_CONFIDENCE_LEVELS)}, got {self.confidence_level}."
            )

        if isinstance(self.is_definitive, bool) is False:
            raise TypeError("is_definitive must be a strict boolean.")

        expected_definitive = self.verdict != Verdict.UNCERTAIN
        if self.is_definitive != expected_definitive:
            raise ValueError(
                f"is_definitive ({self.is_definitive}) inconsistent with verdict {self.verdict}."
            )

        if not isinstance(self.reason, str) or not self.reason.strip():
            raise TypeError("reason must be a non-empty string.")

        if isinstance(self.fact_check_conflict, bool) is False:
            raise TypeError("fact_check_conflict must be a strict boolean.")

        # Invariants regarding credibility_score
        if self.credibility_score is None:
            if self.verdict != Verdict.UNCERTAIN:
                raise ValueError(
                    "verdict must be UNCERTAIN when credibility_score is None."
                )
            if self.confidence_level != "NONE":
                raise ValueError(
                    "confidence_level must be 'NONE' when credibility_score is None."
                )
            if self.overall_status != HybridAnalysisStatus.INSUFFICIENT_EVIDENCE:
                raise ValueError(
                    "overall_status must be INSUFFICIENT_EVIDENCE when credibility_score is None."
                )
        else:
            if isinstance(self.credibility_score, bool) or not isinstance(
                self.credibility_score, (int, float)
            ):
                raise TypeError("credibility_score must be a numeric float or None.")
            if not math.isfinite(self.credibility_score):
                raise ValueError("credibility_score must be a finite float.")
            if not (0.0 <= float(self.credibility_score) <= 100.0):
                raise ValueError(
                    f"credibility_score must be in [0.0, 100.0], got {self.credibility_score}."
                )
            if self.overall_status not in (
                HybridAnalysisStatus.COMPLETED,
                HybridAnalysisStatus.PARTIAL_FAILURE,
            ):
                raise ValueError(
                    "overall_status must be COMPLETED or PARTIAL_FAILURE when credibility_score is present."
                )
            if self.confidence_level not in {"HIGH", "MEDIUM", "LOW"}:
                raise ValueError(
                    f"confidence_level must be HIGH, MEDIUM, or LOW when credibility_score is present, got {self.confidence_level}."
                )

            # Score/verdict consistency against result's own thresholds
            score = float(self.credibility_score)
            if score >= credible_val:
                expected_verdict = Verdict.CREDIBLE
            elif score >= uncertain_val:
                expected_verdict = Verdict.UNCERTAIN
            else:
                expected_verdict = Verdict.MISINFORMATION

            if self.verdict != expected_verdict:
                raise ValueError(
                    f"verdict Verdict.{self.verdict.name} is inconsistent with credibility_score {score:.1f} "
                    f"and thresholds (credible={credible_val:.1f}, uncertain={uncertain_val:.1f}). "
                    f"Expected Verdict.{expected_verdict.name}."
                )

    def to_dict(self) -> dict[str, Any]:
        """Returns an independent, mutable, JSON-serializable dictionary representation."""
        return {
            "verdict": (
                self.verdict.value
                if isinstance(self.verdict, Verdict)
                else str(self.verdict)
            ),
            "label": self.label,
            "credibility_score": (
                float(self.credibility_score)
                if self.credibility_score is not None
                else None
            ),
            "confidence_level": self.confidence_level,
            "overall_status": self.overall_status.value,
            "is_definitive": self.is_definitive,
            "thresholds": dict(self.thresholds),
            "reason": self.reason,
            "failed_components": list(self.failed_components),
            "error_details": dict(self.error_details),
            "fact_check_conflict": self.fact_check_conflict,
        }


# ---------------------------------------------------------------------------
# Verdict Service Implementation
# ---------------------------------------------------------------------------


class VerdictService:
    """
    Coordinates deterministic credibility verdict generation based on
    predefined, configurable score thresholds and hybrid analysis results.
    """

    def __init__(
        self,
        credible_threshold: Optional[float] = None,
        uncertain_threshold: Optional[float] = None,
    ) -> None:
        """
        Initializes the service with validated score thresholds.
        Defaults to settings.VERDICT_THRESHOLD_CREDIBLE and settings.VERDICT_THRESHOLD_UNCERTAIN.
        """
        raw_credible = (
            credible_threshold
            if credible_threshold is not None
            else getattr(
                settings, "VERDICT_THRESHOLD_CREDIBLE", DEFAULT_THRESHOLD_CREDIBLE
            )
        )
        raw_uncertain = (
            uncertain_threshold
            if uncertain_threshold is not None
            else getattr(
                settings, "VERDICT_THRESHOLD_UNCERTAIN", DEFAULT_THRESHOLD_UNCERTAIN
            )
        )

        for name, val in [
            ("credible_threshold", raw_credible),
            ("uncertain_threshold", raw_uncertain),
        ]:
            if isinstance(val, bool) or not isinstance(val, (int, float)):
                raise VerdictConfigError(
                    f"{name} must be a numeric float, got {type(val).__name__}."
                )
            if not math.isfinite(val):
                raise VerdictConfigError(f"{name} must be a finite number, got {val}.")
            if not (0.0 <= float(val) <= 100.0):
                raise VerdictConfigError(
                    f"{name} must be between 0.0 and 100.0, got {val}."
                )

        if float(raw_credible) <= float(raw_uncertain):
            raise VerdictConfigError(
                f"credible_threshold ({raw_credible}) must be strictly greater than "
                f"uncertain_threshold ({raw_uncertain})."
            )

        self._credible_threshold = float(raw_credible)
        self._uncertain_threshold = float(raw_uncertain)

    @property
    def credible_threshold(self) -> float:
        """Configured threshold for CREDIBLE classification."""
        return self._credible_threshold

    @property
    def uncertain_threshold(self) -> float:
        """Configured threshold for UNCERTAIN classification lower bound."""
        return self._uncertain_threshold

    def generate_verdict(
        self,
        hybrid_result: HybridCredibilityResult,
    ) -> VerdictResult:
        """
        Maps a HybridCredibilityResult into a standardized VerdictResult.

        Constraints:
        - When credibility_score is None (INSUFFICIENT_EVIDENCE), returns UNCERTAIN without fallback scores.
        - When credibility_score is present, uses pure threshold comparison without additional rounding.
        - Preserves fact_check_conflict, failed_components, and error_details in diagnostic output.
        """
        if not isinstance(hybrid_result, HybridCredibilityResult):
            raise VerdictInputError(
                f"hybrid_result must be a HybridCredibilityResult instance, got {type(hybrid_result).__name__}."
            )

        if not isinstance(hybrid_result.overall_status, HybridAnalysisStatus):
            raise VerdictInputError(
                f"overall_status must be a HybridAnalysisStatus, got {type(hybrid_result.overall_status).__name__}."
            )

        if hybrid_result.overall_status == HybridAnalysisStatus.INSUFFICIENT_EVIDENCE:
            if hybrid_result.credibility_score is not None:
                raise VerdictInputError(
                    "INSUFFICIENT_EVIDENCE result must have credibility_score=None."
                )
            if hybrid_result.confidence_level != "NONE":
                raise VerdictInputError(
                    "INSUFFICIENT_EVIDENCE result must have confidence_level='NONE'."
                )

            reason = (
                "Insufficient evidence: primary truth signals (model inference and "
                "fact-checking evidence) were unavailable to compute a credibility score."
            )
            if hybrid_result.failed_components:
                failed_str = ", ".join(sorted(hybrid_result.failed_components))
                reason += f" Failed components: [{failed_str}]."

            verdict = Verdict.UNCERTAIN
            label = LABEL_UNCERTAIN
        elif hybrid_result.overall_status in (
            HybridAnalysisStatus.COMPLETED,
            HybridAnalysisStatus.PARTIAL_FAILURE,
        ):
            if hybrid_result.credibility_score is None:
                raise VerdictInputError(
                    f"{hybrid_result.overall_status.value} result must have a valid numeric credibility_score."
                )
            if isinstance(hybrid_result.credibility_score, bool) or not isinstance(
                hybrid_result.credibility_score, (int, float)
            ):
                raise VerdictInputError("credibility_score must be a numeric float.")
            if not math.isfinite(hybrid_result.credibility_score) or not (
                0.0 <= float(hybrid_result.credibility_score) <= 100.0
            ):
                raise VerdictInputError(
                    f"credibility_score must be a finite float in [0.0, 100.0], got {hybrid_result.credibility_score}."
                )
            if hybrid_result.confidence_level not in {"HIGH", "MEDIUM", "LOW"}:
                raise VerdictInputError(
                    f"Scored result must have confidence_level in HIGH, MEDIUM, LOW, got {hybrid_result.confidence_level}."
                )

            score = float(hybrid_result.credibility_score)
            if score >= self.credible_threshold:
                verdict = Verdict.CREDIBLE
                label = LABEL_CREDIBLE
                base_reason = f"Credibility score {score:.1f} meets or exceeds credible threshold ({self.credible_threshold:.1f})."
            elif score >= self.uncertain_threshold:
                verdict = Verdict.UNCERTAIN
                label = LABEL_UNCERTAIN
                base_reason = f"Credibility score {score:.1f} falls in uncertain range [{self.uncertain_threshold:.1f}, {self.credible_threshold:.1f})."
            else:
                verdict = Verdict.MISINFORMATION
                label = LABEL_MISINFORMATION
                base_reason = f"Credibility score {score:.1f} falls below uncertain threshold ({self.uncertain_threshold:.1f})."

            # Diagnostic enrichment
            if hybrid_result.fact_check_conflict:
                base_reason += " External fact-checks contain conflicting ratings (confidence downgraded to LOW)."

            if hybrid_result.overall_status == HybridAnalysisStatus.PARTIAL_FAILURE:
                failed_str = ", ".join(sorted(hybrid_result.failed_components))
                base_reason += (
                    f" Evaluated under partial component failure: [{failed_str}]."
                )

            reason = base_reason
        else:
            raise VerdictInputError(
                f"Unsupported overall_status: {hybrid_result.overall_status}"
            )

        thresholds_dict = {
            "credible": self.credible_threshold,
            "uncertain": self.uncertain_threshold,
        }

        return VerdictResult(
            verdict=verdict,
            label=label,
            credibility_score=hybrid_result.credibility_score,
            confidence_level=hybrid_result.confidence_level,
            overall_status=hybrid_result.overall_status,
            is_definitive=(verdict != Verdict.UNCERTAIN),
            thresholds=thresholds_dict,
            reason=reason,
            failed_components=tuple(hybrid_result.failed_components),
            error_details=dict(hybrid_result.error_details),
            fact_check_conflict=hybrid_result.fact_check_conflict,
        )

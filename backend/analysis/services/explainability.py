"""
Explainability Data Service (AI-011).
Synthesizes multi-signal analysis results from AI-009 (HybridCredibilityResult),
AI-010 (VerdictResult), and optional upstream detailed results into an immutable,
deterministic, human-readable explainability report.
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Optional

from analysis.inference.adapter import ModelOutput
from analysis.models import Verdict
from analysis.services.fact_check import FactCheckResult
from analysis.services.hybrid import (
    ALL_COMPONENTS,
    COMPONENT_FACT_CHECK,
    COMPONENT_MODEL,
    COMPONENT_NARRATIVE,
    COMPONENT_RULE_ENGINE,
    HybridAnalysisStatus,
    HybridCredibilityResult,
    SignalStatus,
)
from analysis.services.narrative import NarrativeActivity
from analysis.services.rules import RuleValidationResult
from analysis.services.similarity import SimilarityMetrics
from analysis.services.verdict import VerdictResult

# ---------------------------------------------------------------------------
# Domain Exceptions
# ---------------------------------------------------------------------------


class ExplainabilityEngineError(RuntimeError):
    """Base exception for explainability engine failures."""

    pass


class ExplainabilityInputError(ExplainabilityEngineError, ValueError):
    """Raised when explainability inputs violate their contracts or contain contradictory states."""

    pass


# ---------------------------------------------------------------------------
# Detail Availability Constants
# ---------------------------------------------------------------------------

DETAIL_FULL: str = "FULL"
DETAIL_SUMMARY_ONLY: str = "SUMMARY_ONLY"
DETAIL_NO_EVIDENCE: str = "NO_EVIDENCE"
DETAIL_FAILED: str = "FAILED"
DETAIL_UNSCORABLE: str = "UNSCORABLE"
DETAIL_CONTEXT_UNAVAILABLE: str = "CONTEXT_UNAVAILABLE"
DETAIL_NOT_SUPPLIED: str = "NOT_SUPPLIED"


# ---------------------------------------------------------------------------
# Domain Output Data Contract
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExplainabilityResult:
    """
    Immutable domain output produced by AI-011 (Explainability Data).
    Encapsulates complete public explainability reporting and internal diagnostics.
    """

    verdict: Verdict
    verdict_label: str
    credibility_score: Optional[float]
    confidence_level: str
    overall_status: HybridAnalysisStatus
    is_definitive: bool
    verdict_reason: str
    reasoning: tuple[str, ...]
    score_breakdown: Mapping[str, Mapping[str, Any]]
    effective_weights: Mapping[str, float]
    coverage_ratio: float
    model_explanation: Mapping[str, Any]
    fact_check_explanation: Mapping[str, Any]
    narrative_explanation: Mapping[str, Any]
    rule_explanation: Mapping[str, Any]
    similarity_explanation: Mapping[str, Any]
    diagnostics: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.verdict, Verdict):
            raise TypeError(
                f"verdict must be an instance of Verdict, got {type(self.verdict).__name__}."
            )

        if not isinstance(self.verdict_label, str) or not self.verdict_label.strip():
            raise TypeError("verdict_label must be a non-empty string.")

        if not isinstance(self.overall_status, HybridAnalysisStatus):
            raise TypeError(
                f"overall_status must be HybridAnalysisStatus, got {type(self.overall_status).__name__}."
            )

        if self.confidence_level not in {"HIGH", "MEDIUM", "LOW", "NONE"}:
            raise ValueError(
                f"confidence_level must be HIGH, MEDIUM, LOW, or NONE, got {self.confidence_level}."
            )

        if isinstance(self.is_definitive, bool) is False:
            raise TypeError("is_definitive must be a strict boolean.")

        expected_definitive = self.verdict != Verdict.UNCERTAIN
        if self.is_definitive != expected_definitive:
            raise ValueError(
                f"is_definitive ({self.is_definitive}) inconsistent with verdict {self.verdict}."
            )

        if not isinstance(self.verdict_reason, str) or not self.verdict_reason.strip():
            raise TypeError("verdict_reason must be a non-empty string.")

        if not isinstance(self.reasoning, (tuple, list)):
            raise TypeError("reasoning must be a sequence of strings.")

        for r in self.reasoning:
            if not isinstance(r, str) or not r.strip():
                raise TypeError("All reasoning items must be non-empty strings.")

        if isinstance(self.coverage_ratio, bool) or not isinstance(
            self.coverage_ratio, (int, float)
        ):
            raise TypeError("coverage_ratio must be a numeric float.")
        if not math.isfinite(self.coverage_ratio) or not (
            0.0 <= float(self.coverage_ratio) <= 1.0
        ):
            raise ValueError(
                f"coverage_ratio must be between 0.0 and 1.0, got {self.coverage_ratio}."
            )

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

        # Enforce defensive copies and read-only proxy wrappers
        object.__setattr__(self, "reasoning", tuple(self.reasoning))

        def _deep_freeze_mapping(m: Mapping[str, Any]) -> MappingProxyType:
            frozen = {}
            for k, v in m.items():
                if isinstance(v, Mapping):
                    frozen[k] = _deep_freeze_mapping(v)
                elif isinstance(v, list):
                    frozen[k] = tuple(v)
                else:
                    frozen[k] = v
            return MappingProxyType(frozen)

        object.__setattr__(
            self, "score_breakdown", _deep_freeze_mapping(self.score_breakdown)
        )
        object.__setattr__(
            self,
            "effective_weights",
            MappingProxyType({k: float(v) for k, v in self.effective_weights.items()}),
        )
        object.__setattr__(
            self, "model_explanation", _deep_freeze_mapping(self.model_explanation)
        )
        object.__setattr__(
            self,
            "fact_check_explanation",
            _deep_freeze_mapping(self.fact_check_explanation),
        )
        object.__setattr__(
            self,
            "narrative_explanation",
            _deep_freeze_mapping(self.narrative_explanation),
        )
        object.__setattr__(
            self, "rule_explanation", _deep_freeze_mapping(self.rule_explanation)
        )
        object.__setattr__(
            self,
            "similarity_explanation",
            _deep_freeze_mapping(self.similarity_explanation),
        )
        object.__setattr__(self, "diagnostics", _deep_freeze_mapping(self.diagnostics))

    def to_dict(self) -> dict[str, Any]:
        """
        Returns safe, public-facing dictionary representation for API serialization.
        Strictly excludes internal error_details, stack traces, and operational diagnostics.
        """

        def _unfreeze(val: Any) -> Any:
            if isinstance(val, (Mapping, MappingProxyType)):
                return {k: _unfreeze(v) for k, v in val.items()}
            if isinstance(val, (list, tuple)):
                return [_unfreeze(v) for v in val]
            return val

        failed_comps = list(self.diagnostics.get("failed_components", ()))

        return {
            "verdict": self.verdict.value,
            "verdict_label": self.verdict_label,
            "credibility_score": (
                float(self.credibility_score)
                if self.credibility_score is not None
                else None
            ),
            "confidence_level": self.confidence_level,
            "overall_status": self.overall_status.value,
            "is_definitive": self.is_definitive,
            "verdict_reason": self.verdict_reason,
            "reasoning": list(self.reasoning),
            "score_breakdown": _unfreeze(self.score_breakdown),
            "effective_weights": {
                k: float(v) for k, v in self.effective_weights.items()
            },
            "coverage_ratio": float(self.coverage_ratio),
            "components": {
                COMPONENT_MODEL: _unfreeze(self.model_explanation),
                COMPONENT_FACT_CHECK: _unfreeze(self.fact_check_explanation),
                COMPONENT_NARRATIVE: _unfreeze(self.narrative_explanation),
                COMPONENT_RULE_ENGINE: _unfreeze(self.rule_explanation),
                "similarity": _unfreeze(self.similarity_explanation),
            },
            "failed_components": failed_comps,
        }

    def to_internal_dict(self) -> dict[str, Any]:
        """
        Returns forensic dictionary representation including full internal diagnostics.
        Destined for Analysis.explainability_json persistence and audit logging.
        """

        def _unfreeze(val: Any) -> Any:
            if isinstance(val, (Mapping, MappingProxyType)):
                return {k: _unfreeze(v) for k, v in val.items()}
            if isinstance(val, (list, tuple)):
                return [_unfreeze(v) for v in val]
            return val

        data = self.to_dict()
        data["diagnostics"] = _unfreeze(self.diagnostics)
        return data


# ---------------------------------------------------------------------------
# Explainability Service Implementation
# ---------------------------------------------------------------------------


class ExplainabilityService:
    """
    Coordinates synthesis of multi-signal analysis results into structured,
    explainable domain representations.
    Operates strictly in memory; zero database, network, or ML inference calls.
    """

    def generate_explainability(
        self,
        hybrid_result: HybridCredibilityResult,
        verdict_result: VerdictResult,
        *,
        model_output: Optional[ModelOutput] = None,
        fact_check_result: Optional[FactCheckResult] = None,
        narrative_activity: Optional[NarrativeActivity] = None,
        rule_validation_result: Optional[RuleValidationResult] = None,
        similarity_metrics: Optional[SimilarityMetrics] = None,
    ) -> ExplainabilityResult:
        """
        Synthesizes an explainability report from hybrid and verdict results,
        enriched with optional upstream detailed objects.

        Raises:
            ExplainabilityInputError: If hybrid and verdict results conflict, or if
                supplied detailed objects contradict recorded signal statuses.
        """
        # 1. Base input type validation
        if not isinstance(hybrid_result, HybridCredibilityResult):
            raise ExplainabilityInputError(
                f"hybrid_result must be a HybridCredibilityResult instance, got {type(hybrid_result).__name__}."
            )
        if not isinstance(verdict_result, VerdictResult):
            raise ExplainabilityInputError(
                f"verdict_result must be a VerdictResult instance, got {type(verdict_result).__name__}."
            )

        # 2. Strict Cross-Result Consistency Validation
        if hybrid_result.credibility_score is None:
            if verdict_result.credibility_score is not None:
                raise ExplainabilityInputError(
                    "credibility_score mismatch: hybrid_result is None but verdict_result has numeric score."
                )
        else:
            if verdict_result.credibility_score is None:
                raise ExplainabilityInputError(
                    "credibility_score mismatch: hybrid_result has numeric score but verdict_result is None."
                )
            if hybrid_result.credibility_score != verdict_result.credibility_score:
                raise ExplainabilityInputError(
                    f"credibility_score mismatch: hybrid_result ({hybrid_result.credibility_score}) != "
                    f"verdict_result ({verdict_result.credibility_score})."
                )

        if hybrid_result.overall_status != verdict_result.overall_status:
            raise ExplainabilityInputError(
                f"overall_status mismatch: hybrid_result ({hybrid_result.overall_status}) != "
                f"verdict_result ({verdict_result.overall_status})."
            )

        if hybrid_result.confidence_level != verdict_result.confidence_level:
            raise ExplainabilityInputError(
                f"confidence_level mismatch: hybrid_result ({hybrid_result.confidence_level}) != "
                f"verdict_result ({verdict_result.confidence_level})."
            )

        if hybrid_result.fact_check_conflict != verdict_result.fact_check_conflict:
            raise ExplainabilityInputError(
                f"fact_check_conflict mismatch: hybrid_result ({hybrid_result.fact_check_conflict}) != "
                f"verdict_result ({verdict_result.fact_check_conflict})."
            )

        if tuple(sorted(hybrid_result.failed_components)) != tuple(
            sorted(verdict_result.failed_components)
        ):
            raise ExplainabilityInputError(
                f"failed_components mismatch: hybrid_result ({hybrid_result.failed_components}) != "
                f"verdict_result ({verdict_result.failed_components})."
            )

        if dict(hybrid_result.error_details) != dict(verdict_result.error_details):
            raise ExplainabilityInputError(
                "error_details mismatch between hybrid_result and verdict_result."
            )

        # 3. Optional Detailed Objects Contract Validation Matrix
        model_status = hybrid_result.signal_statuses[COMPONENT_MODEL]
        if model_output is not None:
            if not isinstance(model_output, ModelOutput):
                raise ExplainabilityInputError(
                    f"model_output must be a ModelOutput instance, got {type(model_output).__name__}."
                )
            if model_status in (SignalStatus.FAILED, SignalStatus.NO_EVIDENCE):
                raise ExplainabilityInputError(
                    f"model_output supplied but model status in hybrid_result is {model_status.value}."
                )

        fc_status = hybrid_result.signal_statuses[COMPONENT_FACT_CHECK]
        if fact_check_result is not None:
            if not isinstance(fact_check_result, FactCheckResult):
                raise ExplainabilityInputError(
                    f"fact_check_result must be a FactCheckResult instance, got {type(fact_check_result).__name__}."
                )
            if fc_status == SignalStatus.FAILED:
                raise ExplainabilityInputError(
                    "fact_check_result supplied but fact_check status in hybrid_result is FAILED."
                )
            if fc_status == SignalStatus.NO_EVIDENCE and fact_check_result.matches > 0:
                raise ExplainabilityInputError(
                    f"fact_check_result with matches={fact_check_result.matches} supplied but "
                    "fact_check status in hybrid_result is NO_EVIDENCE."
                )
            if fc_status == SignalStatus.AVAILABLE and fact_check_result.matches == 0:
                raise ExplainabilityInputError(
                    "fact_check_result with 0 matches supplied but fact_check status in hybrid_result is AVAILABLE."
                )

        narrative_status = hybrid_result.signal_statuses[COMPONENT_NARRATIVE]
        if narrative_activity is not None:
            if not isinstance(narrative_activity, NarrativeActivity):
                raise ExplainabilityInputError(
                    f"narrative_activity must be a NarrativeActivity instance, got {type(narrative_activity).__name__}."
                )
            if narrative_status in (SignalStatus.FAILED, SignalStatus.NO_EVIDENCE):
                raise ExplainabilityInputError(
                    f"narrative_activity supplied but narrative status in hybrid_result is {narrative_status.value}."
                )

        rule_status = hybrid_result.signal_statuses[COMPONENT_RULE_ENGINE]
        if rule_validation_result is not None:
            if not isinstance(rule_validation_result, RuleValidationResult):
                raise ExplainabilityInputError(
                    f"rule_validation_result must be a RuleValidationResult instance, got {type(rule_validation_result).__name__}."
                )
            if rule_status in (SignalStatus.FAILED, SignalStatus.NO_EVIDENCE):
                raise ExplainabilityInputError(
                    f"rule_validation_result supplied but rule_engine status in hybrid_result is {rule_status.value}."
                )

        if similarity_metrics is not None:
            if not isinstance(similarity_metrics, SimilarityMetrics):
                raise ExplainabilityInputError(
                    f"similarity_metrics must be a SimilarityMetrics instance, got {type(similarity_metrics).__name__}."
                )
            if narrative_status in (SignalStatus.FAILED, SignalStatus.NO_EVIDENCE):
                if (
                    similarity_metrics.related_claims_count > 0
                    or similarity_metrics.highest_similarity_score > 0.0
                ):
                    raise ExplainabilityInputError(
                        f"similarity_metrics with positive matches supplied but narrative status is {narrative_status.value}."
                    )

        # 4. Synthesize Component Explanations
        model_explanation = self._build_model_explanation(
            status=model_status,
            component_score=hybrid_result.component_scores[COMPONENT_MODEL],
            effective_weight=hybrid_result.effective_weights[COMPONENT_MODEL],
            weighted_contribution=hybrid_result.weighted_contributions[COMPONENT_MODEL],
            model_output=model_output,
            error_message=hybrid_result.error_details.get(COMPONENT_MODEL),
        )

        fact_check_explanation = self._build_fact_check_explanation(
            status=fc_status,
            component_score=hybrid_result.component_scores[COMPONENT_FACT_CHECK],
            effective_weight=hybrid_result.effective_weights[COMPONENT_FACT_CHECK],
            weighted_contribution=hybrid_result.weighted_contributions[
                COMPONENT_FACT_CHECK
            ],
            has_conflict=hybrid_result.fact_check_conflict,
            fact_check_result=fact_check_result,
            error_message=hybrid_result.error_details.get(COMPONENT_FACT_CHECK),
        )

        narrative_explanation = self._build_narrative_explanation(
            status=narrative_status,
            narrative_activity=narrative_activity,
            narrative_context=hybrid_result.narrative_context,
            error_message=hybrid_result.error_details.get(COMPONENT_NARRATIVE),
        )

        rule_explanation = self._build_rule_explanation(
            status=rule_status,
            component_score=hybrid_result.component_scores[COMPONENT_RULE_ENGINE],
            effective_weight=hybrid_result.effective_weights[COMPONENT_RULE_ENGINE],
            weighted_contribution=hybrid_result.weighted_contributions[
                COMPONENT_RULE_ENGINE
            ],
            rule_validation_result=rule_validation_result,
            error_message=hybrid_result.error_details.get(COMPONENT_RULE_ENGINE),
        )

        similarity_explanation = self._build_similarity_explanation(
            narrative_status=narrative_status,
            similarity_metrics=similarity_metrics,
        )

        # 5. Build Canonical Score Breakdown
        score_breakdown = {}
        for comp in ALL_COMPONENTS:
            raw_sc = hybrid_result.component_scores[comp]
            score_breakdown[comp] = {
                "component_score": float(raw_sc) if raw_sc is not None else None,
                "effective_weight": float(hybrid_result.effective_weights[comp]),
                "weighted_contribution": float(
                    hybrid_result.weighted_contributions[comp]
                ),
                "status": hybrid_result.signal_statuses[comp].value,
            }

        # 6. Synthesize Deterministic Reasoning Statements
        reasoning = self._build_reasoning(
            hybrid_result=hybrid_result,
            verdict_result=verdict_result,
            model_explanation=model_explanation,
            fact_check_explanation=fact_check_explanation,
            narrative_explanation=narrative_explanation,
            rule_explanation=rule_explanation,
        )

        # 7. Internal Diagnostics
        diagnostics = {
            "failed_components": list(hybrid_result.failed_components),
            "error_details": dict(hybrid_result.error_details),
            "thresholds": dict(verdict_result.thresholds),
            "signal_statuses": {
                k: v.value for k, v in hybrid_result.signal_statuses.items()
            },
            "coverage_ratio": float(hybrid_result.coverage_ratio),
        }

        return ExplainabilityResult(
            verdict=verdict_result.verdict,
            verdict_label=verdict_result.label,
            credibility_score=verdict_result.credibility_score,
            confidence_level=verdict_result.confidence_level,
            overall_status=verdict_result.overall_status,
            is_definitive=verdict_result.is_definitive,
            verdict_reason=verdict_result.reason,
            reasoning=tuple(reasoning),
            score_breakdown=score_breakdown,
            effective_weights=dict(hybrid_result.effective_weights),
            coverage_ratio=float(hybrid_result.coverage_ratio),
            model_explanation=model_explanation,
            fact_check_explanation=fact_check_explanation,
            narrative_explanation=narrative_explanation,
            rule_explanation=rule_explanation,
            similarity_explanation=similarity_explanation,
            diagnostics=diagnostics,
        )

    # -----------------------------------------------------------------------
    # Component Explanation Builders
    # -----------------------------------------------------------------------

    def _build_model_explanation(
        self,
        status: SignalStatus,
        component_score: Optional[float],
        effective_weight: float,
        weighted_contribution: float,
        model_output: Optional[ModelOutput],
        error_message: Optional[str],
    ) -> dict[str, Any]:
        if status == SignalStatus.FAILED:
            detail_status = DETAIL_FAILED
            prediction = None
            confidence = None
            summary = "AI classification model failed during processing."
        elif status == SignalStatus.NO_EVIDENCE:
            detail_status = DETAIL_NO_EVIDENCE
            prediction = None
            confidence = None
            summary = (
                "AI classification model inference was not provided for this claim."
            )
        elif model_output is not None:
            detail_status = DETAIL_FULL
            prediction = model_output.prediction.value
            confidence = float(model_output.confidence)
            label_text = model_output.prediction.label.lower()
            summary = (
                f"Fine-tuned classification model predicted the claim is {label_text} "
                f"with {confidence * 100:.1f}% confidence."
            )
        else:
            detail_status = DETAIL_SUMMARY_ONLY
            prediction = None
            confidence = None
            score_val = float(component_score) if component_score is not None else 0.0
            summary = (
                f"AI classification model contributed a credibility signal of {score_val:.2f}, "
                "but detailed prediction/confidence object was not supplied."
            )

        return {
            "detail_status": detail_status,
            "signal_status": status.value,
            "component_score": (
                float(component_score) if component_score is not None else None
            ),
            "effective_weight": float(effective_weight),
            "weighted_contribution": float(weighted_contribution),
            "prediction": prediction,
            "confidence": confidence,
            "summary": summary,
        }

    def _build_fact_check_explanation(
        self,
        status: SignalStatus,
        component_score: Optional[float],
        effective_weight: float,
        weighted_contribution: float,
        has_conflict: bool,
        fact_check_result: Optional[FactCheckResult],
        error_message: Optional[str],
    ) -> dict[str, Any]:
        sources: list[dict[str, Any]] = []
        matches_count: Optional[int] = None

        if status == SignalStatus.FAILED:
            detail_status = DETAIL_FAILED
            summary = "External fact-check service failed during evaluation."
        elif status == SignalStatus.NO_EVIDENCE:
            detail_status = DETAIL_NO_EVIDENCE
            matches_count = 0
            summary = "No external fact-check reviews were found for this claim."
            if fact_check_result and fact_check_result.summary:
                summary = fact_check_result.summary
        elif status == SignalStatus.UNSCORABLE:
            detail_status = DETAIL_UNSCORABLE
            if fact_check_result:
                matches_count = fact_check_result.matches
                sources = [
                    {
                        "publisher": s.publisher,
                        "rating": s.rating,
                        "url": s.url,
                        "review_date": s.review_date,
                    }
                    for s in fact_check_result.sources
                ]
            summary = "External fact-check reviews were found, but publisher ratings were ambiguous or unscorable."
        elif fact_check_result is not None:
            detail_status = DETAIL_FULL
            matches_count = fact_check_result.matches
            sources = [
                {
                    "publisher": s.publisher,
                    "rating": s.rating,
                    "url": s.url,
                    "review_date": s.review_date,
                }
                for s in fact_check_result.sources
            ]
            summary = fact_check_result.summary
            if not summary or summary.strip() == "":
                summary = f"External fact-checking evidence confirmed {matches_count} matching review(s)."
        else:
            detail_status = DETAIL_SUMMARY_ONLY
            score_val = float(component_score) if component_score is not None else 0.0
            summary = (
                f"External fact-checking evidence contributed a credibility signal of {score_val:.2f}, "
                "but detailed publisher sources were not supplied."
            )

        return {
            "detail_status": detail_status,
            "signal_status": status.value,
            "component_score": (
                float(component_score) if component_score is not None else None
            ),
            "effective_weight": float(effective_weight),
            "weighted_contribution": float(weighted_contribution),
            "has_conflict": has_conflict,
            "matches_count": matches_count,
            "summary": summary,
            "sources": sources,
        }

    def _build_narrative_explanation(
        self,
        status: SignalStatus,
        narrative_activity: Optional[NarrativeActivity],
        narrative_context: Optional[Mapping[str, Any]],
        error_message: Optional[str],
    ) -> dict[str, Any]:
        similar_claims_count: Optional[int] = None
        activity_level: str = "NONE"
        first_seen: Optional[str] = None
        latest_occurrence: Optional[str] = None

        if status == SignalStatus.FAILED:
            detail_status = DETAIL_FAILED
            summary = "Narrative activity evaluation failed during processing."
        elif status == SignalStatus.NO_EVIDENCE:
            detail_status = DETAIL_NO_EVIDENCE
            summary = "Narrative evaluation was not performed or provided no evidence."
        elif narrative_activity is not None:
            detail_status = DETAIL_FULL
            similar_claims_count = narrative_activity.similar_claims_count
            activity_level = narrative_activity.activity_level
            first_seen = (
                narrative_activity.first_seen.isoformat()
                if narrative_activity.first_seen
                else None
            )
            latest_occurrence = (
                narrative_activity.latest_occurrence.isoformat()
                if narrative_activity.latest_occurrence
                else None
            )
            if similar_claims_count == 0:
                summary = "Historical narrative analysis evaluated candidates and found zero matching claims."
            else:
                date_str = first_seen[:10] if first_seen else "unknown date"
                summary = (
                    f"Historical narrative recurrence detected across {similar_claims_count} similar claims "
                    f"(first seen: {date_str}); retained for context but excluded from numeric truth aggregation per interim policy."
                )
        elif narrative_context is not None:
            detail_status = DETAIL_FULL
            similar_claims_count = int(narrative_context.get("similar_claims_count", 0))
            activity_level = str(narrative_context.get("activity_level", "LOW"))
            first_seen = narrative_context.get("first_seen")
            latest_occurrence = narrative_context.get("latest_occurrence")
            if similar_claims_count == 0:
                summary = "Historical narrative analysis evaluated candidates and found zero matching claims."
            else:
                date_str = first_seen[:10] if first_seen else "unknown date"
                summary = (
                    f"Historical narrative recurrence detected across {similar_claims_count} similar claims "
                    f"(first seen: {date_str}); retained for context but excluded from numeric truth aggregation per interim policy."
                )
        else:
            detail_status = DETAIL_CONTEXT_UNAVAILABLE
            summary = (
                "Narrative evaluation was recorded as unscorable by the credibility engine, "
                "but detailed narrative context was not supplied to explainability."
            )

        return {
            "detail_status": detail_status,
            "signal_status": status.value,
            "is_scorable": False,
            "effective_weight": 0.0,
            "weighted_contribution": 0.0,
            "similar_claims_count": similar_claims_count,
            "activity_level": activity_level,
            "first_seen": first_seen,
            "latest_occurrence": latest_occurrence,
            "summary": summary,
        }

    def _build_rule_explanation(
        self,
        status: SignalStatus,
        component_score: Optional[float],
        effective_weight: float,
        weighted_contribution: float,
        rule_validation_result: Optional[RuleValidationResult],
        error_message: Optional[str],
    ) -> dict[str, Any]:
        flags_triggered: list[str] = []
        observations: list[str] = []
        penalty_applied: Optional[float] = None

        if status == SignalStatus.FAILED:
            detail_status = DETAIL_FAILED
            summary = "Rule heuristics evaluation failed during processing."
        elif status == SignalStatus.NO_EVIDENCE:
            detail_status = DETAIL_NO_EVIDENCE
            summary = "Rule-based heuristics were not evaluated for this claim."
        elif rule_validation_result is not None:
            detail_status = DETAIL_FULL
            penalty_applied = float(rule_validation_result.credibility_penalty)
            flags_triggered = [
                k for k, v in rule_validation_result.flags.items() if v is True
            ]
            observations = list(rule_validation_result.observations)
            if rule_validation_result.triggered_count == 0:
                summary = "Deterministic rule heuristics detected no sensationalism, clickbait, or deceptive patterns."
            else:
                summary = (
                    f"Rule heuristics triggered {rule_validation_result.triggered_count} flag(s) with a "
                    f"{penalty_applied:.2f} credibility penalty."
                )
        else:
            detail_status = DETAIL_SUMMARY_ONLY
            score_val = float(component_score) if component_score is not None else 0.0
            summary = (
                f"Rule heuristics contributed a credibility score of {score_val:.2f}, "
                "but detailed heuristic flags were not supplied."
            )

        return {
            "detail_status": detail_status,
            "signal_status": status.value,
            "component_score": (
                float(component_score) if component_score is not None else None
            ),
            "effective_weight": float(effective_weight),
            "weighted_contribution": float(weighted_contribution),
            "penalty_applied": penalty_applied,
            "flags_triggered": flags_triggered,
            "observations": observations,
            "summary": summary,
        }

    def _build_similarity_explanation(
        self,
        narrative_status: SignalStatus,
        similarity_metrics: Optional[SimilarityMetrics],
    ) -> dict[str, Any]:
        if similarity_metrics is not None:
            detail_status = DETAIL_FULL
            highest = float(similarity_metrics.highest_similarity_score)
            average = float(similarity_metrics.average_similarity_score)
            count = int(similarity_metrics.related_claims_count)
            has_matches = bool(similarity_metrics.has_matches)
            summary = (
                f"Semantic similarity analysis identified {count} related claim(s) "
                f"(highest similarity: {highest * 100:.1f}%, average: {average * 100:.1f}%)."
            )
        elif narrative_status == SignalStatus.FAILED:
            detail_status = DETAIL_FAILED
            highest = None
            average = None
            count = None
            has_matches = None
            summary = (
                "Similarity metrics are unavailable due to narrative component failure."
            )
        elif narrative_status == SignalStatus.NO_EVIDENCE:
            detail_status = DETAIL_NO_EVIDENCE
            highest = None
            average = None
            count = None
            has_matches = None
            summary = "Similarity metrics are unavailable because narrative analysis did not provide evidence."
        else:
            detail_status = DETAIL_NOT_SUPPLIED
            highest = None
            average = None
            count = None
            has_matches = None
            summary = "Similarity metrics were not supplied to explainability."

        return {
            "detail_status": detail_status,
            "highest_similarity_score": highest,
            "average_similarity_score": average,
            "related_claims_count": count,
            "has_matches": has_matches,
            "summary": summary,
        }

    # -----------------------------------------------------------------------
    # Deterministic Reasoning Synthesis
    # -----------------------------------------------------------------------

    def _build_reasoning(
        self,
        hybrid_result: HybridCredibilityResult,
        verdict_result: VerdictResult,
        model_explanation: dict[str, Any],
        fact_check_explanation: dict[str, Any],
        narrative_explanation: dict[str, Any],
        rule_explanation: dict[str, Any],
    ) -> list[str]:
        statements: list[str] = []

        # 1. Model inference statement
        statements.append(model_explanation["summary"])

        # 2. Fact check statement
        statements.append(fact_check_explanation["summary"])

        # 3. Conflict warning statement if conflict detected
        if hybrid_result.fact_check_conflict:
            statements.append(
                "External fact-check sources contain conflicting ratings across publishers; "
                "overall confidence was downgraded to LOW."
            )

        # 4. Rule engine statement
        statements.append(rule_explanation["summary"])

        # 5. Narrative activity statement
        statements.append(narrative_explanation["summary"])

        # 6. Partial failure statement
        if hybrid_result.overall_status == HybridAnalysisStatus.PARTIAL_FAILURE:
            failed_str = ", ".join(sorted(hybrid_result.failed_components))
            statements.append(
                f"Analysis was evaluated under partial component failure: [{failed_str}]. "
                "Remaining available signals were renormalized."
            )

        # 7. Insufficient evidence statement
        if hybrid_result.overall_status == HybridAnalysisStatus.INSUFFICIENT_EVIDENCE:
            statements.append(
                "Primary truth signals (model inference and fact-checking evidence) were unavailable; "
                "credibility cannot be calculated."
            )

        return statements

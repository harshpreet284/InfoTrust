"""
Unit and integration tests for AI-011 Explainability Data Service.
Verifies contract validation, detail status availability, narrative and similarity state handling,
numerical integrity, deterministic reasoning, public vs internal serialization,
immutability, and architectural isolation.
"""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

from django.test import SimpleTestCase

from analysis.inference.adapter import ModelOutput
from analysis.models import ModelPrediction, Verdict
from analysis.services.explainability import (
    DETAIL_CONTEXT_UNAVAILABLE,
    DETAIL_FAILED,
    DETAIL_FULL,
    DETAIL_NO_EVIDENCE,
    DETAIL_NOT_SUPPLIED,
    DETAIL_SUMMARY_ONLY,
    ExplainabilityInputError,
    ExplainabilityService,
)
from analysis.services.fact_check import FactCheckEvidenceItem, FactCheckResult
from analysis.services.hybrid import (
    COMPONENT_FACT_CHECK,
    COMPONENT_MODEL,
    COMPONENT_NARRATIVE,
    COMPONENT_RULE_ENGINE,
    HybridAnalysisStatus,
    HybridCredibilityResult,
    SignalStatus,
)
from analysis.services.narrative import NarrativeActivity, NarrativeMatchRecord
from analysis.services.rules import RuleValidationResult
from analysis.services.similarity import SimilarityMetrics
from analysis.services.verdict import VerdictResult


def _build_nominal_hybrid_result(
    *,
    credibility_score: float | None = 88.4,
    overall_status: HybridAnalysisStatus = HybridAnalysisStatus.COMPLETED,
    confidence_level: str = "HIGH",
    coverage_ratio: float = 0.85,
    component_scores: dict[str, float | None] | None = None,
    effective_weights: dict[str, float] | None = None,
    weighted_contributions: dict[str, float] | None = None,
    signal_statuses: dict[str, SignalStatus] | None = None,
    failed_components: tuple[str, ...] = (),
    error_details: dict[str, str] | None = None,
    fact_check_conflict: bool = False,
    narrative_context: dict | None = None,
) -> HybridCredibilityResult:
    return HybridCredibilityResult(
        credibility_score=credibility_score,
        overall_status=overall_status,
        confidence_level=confidence_level,
        coverage_ratio=coverage_ratio,
        component_scores=component_scores
        or {
            COMPONENT_MODEL: 0.96,
            COMPONENT_FACT_CHECK: 0.80,
            COMPONENT_NARRATIVE: None,
            COMPONENT_RULE_ENGINE: 0.95,
        },
        effective_weights=effective_weights
        or {
            COMPONENT_MODEL: 0.41,
            COMPONENT_FACT_CHECK: 0.47,
            COMPONENT_NARRATIVE: 0.0,
            COMPONENT_RULE_ENGINE: 0.12,
        },
        weighted_contributions=weighted_contributions
        or {
            COMPONENT_MODEL: 39.53,
            COMPONENT_FACT_CHECK: 37.65,
            COMPONENT_NARRATIVE: 0.0,
            COMPONENT_RULE_ENGINE: 11.18,
        },
        signal_statuses=signal_statuses
        or {
            COMPONENT_MODEL: SignalStatus.AVAILABLE,
            COMPONENT_FACT_CHECK: SignalStatus.AVAILABLE,
            COMPONENT_NARRATIVE: SignalStatus.UNSCORABLE,
            COMPONENT_RULE_ENGINE: SignalStatus.AVAILABLE,
        },
        failed_components=failed_components,
        error_details=error_details or {},
        fact_check_conflict=fact_check_conflict,
        narrative_context=narrative_context,
    )


def _build_nominal_verdict_result(
    *,
    verdict: Verdict = Verdict.CREDIBLE,
    label: str = "Likely Credible",
    credibility_score: float | None = 88.4,
    confidence_level: str = "HIGH",
    overall_status: HybridAnalysisStatus = HybridAnalysisStatus.COMPLETED,
    is_definitive: bool = True,
    thresholds: dict[str, float] | None = None,
    reason: str = "Credibility score 88.4 meets or exceeds credible threshold (70.0).",
    failed_components: tuple[str, ...] = (),
    error_details: dict[str, str] | None = None,
    fact_check_conflict: bool = False,
) -> VerdictResult:
    return VerdictResult(
        verdict=verdict,
        label=label,
        credibility_score=credibility_score,
        confidence_level=confidence_level,
        overall_status=overall_status,
        is_definitive=is_definitive,
        thresholds=thresholds or {"credible": 70.0, "uncertain": 40.0},
        reason=reason,
        failed_components=failed_components,
        error_details=error_details or {},
        fact_check_conflict=fact_check_conflict,
    )


class ExplainabilityInputValidationTests(SimpleTestCase):
    """Verifies strict cross-result validation and contract-level integrity checks."""

    def setUp(self):
        self.service = ExplainabilityService()
        self.hybrid_res = _build_nominal_hybrid_result()
        self.verdict_res = _build_nominal_verdict_result()

    def test_invalid_input_types_rejected(self):
        with self.assertRaises(ExplainabilityInputError):
            self.service.generate_explainability("invalid", self.verdict_res)  # type: ignore[arg-type]

        with self.assertRaises(ExplainabilityInputError):
            self.service.generate_explainability(self.hybrid_res, "invalid")  # type: ignore[arg-type]

    def test_score_exact_equality_accepted(self):
        # Identical scores are accepted without error
        res = self.service.generate_explainability(self.hybrid_res, self.verdict_res)
        self.assertEqual(res.credibility_score, 88.4)

    def test_score_both_none_accepted(self):
        # Both None values are accepted
        none_hybrid = _build_nominal_hybrid_result(
            credibility_score=None,
            overall_status=HybridAnalysisStatus.INSUFFICIENT_EVIDENCE,
            confidence_level="NONE",
        )
        none_verdict = _build_nominal_verdict_result(
            verdict=Verdict.UNCERTAIN,
            label="Uncertain",
            credibility_score=None,
            overall_status=HybridAnalysisStatus.INSUFFICIENT_EVIDENCE,
            confidence_level="NONE",
            is_definitive=False,
            reason="Insufficient evidence",
        )
        res = self.service.generate_explainability(none_hybrid, none_verdict)
        self.assertIsNone(res.credibility_score)

    def test_score_mismatch_rejected(self):
        # Numeric vs different numeric
        mismatched_verdict = _build_nominal_verdict_result(credibility_score=85.0)
        with self.assertRaises(ExplainabilityInputError) as ctx:
            self.service.generate_explainability(self.hybrid_res, mismatched_verdict)
        self.assertIn("credibility_score mismatch", str(ctx.exception))

        # Difference smaller than 1e-9 is rejected under exact equality
        sub_epsilon_verdict = _build_nominal_verdict_result(
            credibility_score=88.4 + 1e-10
        )
        with self.assertRaises(ExplainabilityInputError) as ctx:
            self.service.generate_explainability(self.hybrid_res, sub_epsilon_verdict)
        self.assertIn("credibility_score mismatch", str(ctx.exception))

        # Hybrid None vs Verdict numeric rejected
        none_hybrid = _build_nominal_hybrid_result(
            credibility_score=None,
            overall_status=HybridAnalysisStatus.INSUFFICIENT_EVIDENCE,
            confidence_level="NONE",
        )
        with self.assertRaises(ExplainabilityInputError) as ctx:
            self.service.generate_explainability(none_hybrid, self.verdict_res)
        self.assertIn("credibility_score mismatch", str(ctx.exception))

        # Hybrid numeric vs Verdict None rejected
        none_verdict = _build_nominal_verdict_result(
            verdict=Verdict.UNCERTAIN,
            label="Uncertain",
            credibility_score=None,
            overall_status=HybridAnalysisStatus.INSUFFICIENT_EVIDENCE,
            confidence_level="NONE",
            is_definitive=False,
            reason="Insufficient evidence",
        )
        with self.assertRaises(ExplainabilityInputError) as ctx:
            self.service.generate_explainability(self.hybrid_res, none_verdict)
        self.assertIn("credibility_score mismatch", str(ctx.exception))

    def test_overall_status_mismatch_rejected(self):
        mismatched_verdict = _build_nominal_verdict_result(
            overall_status=HybridAnalysisStatus.PARTIAL_FAILURE
        )
        with self.assertRaises(ExplainabilityInputError) as ctx:
            self.service.generate_explainability(self.hybrid_res, mismatched_verdict)
        self.assertIn("overall_status mismatch", str(ctx.exception))

    def test_confidence_level_mismatch_rejected(self):
        mismatched_verdict = _build_nominal_verdict_result(confidence_level="LOW")
        with self.assertRaises(ExplainabilityInputError) as ctx:
            self.service.generate_explainability(self.hybrid_res, mismatched_verdict)
        self.assertIn("confidence_level mismatch", str(ctx.exception))

    def test_fact_check_conflict_mismatch_rejected(self):
        mismatched_verdict = _build_nominal_verdict_result(fact_check_conflict=True)
        with self.assertRaises(ExplainabilityInputError) as ctx:
            self.service.generate_explainability(self.hybrid_res, mismatched_verdict)
        self.assertIn("fact_check_conflict mismatch", str(ctx.exception))

    def test_failed_components_mismatch_rejected(self):
        mismatched_verdict = _build_nominal_verdict_result(
            failed_components=("fact_check",)
        )
        with self.assertRaises(ExplainabilityInputError) as ctx:
            self.service.generate_explainability(self.hybrid_res, mismatched_verdict)
        self.assertIn("failed_components mismatch", str(ctx.exception))

    def test_error_details_mismatch_rejected(self):
        mismatched_verdict = _build_nominal_verdict_result(
            error_details={"model": "Mismatch error"}
        )
        with self.assertRaises(ExplainabilityInputError) as ctx:
            self.service.generate_explainability(self.hybrid_res, mismatched_verdict)
        self.assertIn("error_details mismatch", str(ctx.exception))

    def test_model_output_with_failed_or_no_evidence_rejected(self):
        model_out = ModelOutput(prediction=ModelPrediction.CREDIBLE, confidence=0.95)

        # Model is FAILED in hybrid
        hybrid_failed = _build_nominal_hybrid_result(
            signal_statuses={
                COMPONENT_MODEL: SignalStatus.FAILED,
                COMPONENT_FACT_CHECK: SignalStatus.AVAILABLE,
                COMPONENT_NARRATIVE: SignalStatus.UNSCORABLE,
                COMPONENT_RULE_ENGINE: SignalStatus.AVAILABLE,
            },
            failed_components=(COMPONENT_MODEL,),
            error_details={COMPONENT_MODEL: "OOM error"},
        )
        verdict_failed = _build_nominal_verdict_result(
            failed_components=(COMPONENT_MODEL,),
            error_details={COMPONENT_MODEL: "OOM error"},
        )
        with self.assertRaises(ExplainabilityInputError) as ctx:
            self.service.generate_explainability(
                hybrid_failed, verdict_failed, model_output=model_out
            )
        self.assertIn("model_output supplied but model status", str(ctx.exception))

    def test_fact_check_result_contradictions_rejected(self):
        ev = FactCheckEvidenceItem(
            publisher="PolitiFact",
            rating="True",
            url="https://politifact.com/factchecks/1",
        )
        fc_res_matches = FactCheckResult(
            matches=1,
            sources=(ev,),
            summary="Verified claim",
            evidence_urls=("https://politifact.com/factchecks/1",),
        )
        fc_res_empty = FactCheckResult.empty()

        # matches > 0 supplied while NO_EVIDENCE
        hybrid_no_fc = _build_nominal_hybrid_result(
            signal_statuses={
                COMPONENT_MODEL: SignalStatus.AVAILABLE,
                COMPONENT_FACT_CHECK: SignalStatus.NO_EVIDENCE,
                COMPONENT_NARRATIVE: SignalStatus.UNSCORABLE,
                COMPONENT_RULE_ENGINE: SignalStatus.AVAILABLE,
            }
        )
        with self.assertRaises(ExplainabilityInputError) as ctx:
            self.service.generate_explainability(
                hybrid_no_fc, self.verdict_res, fact_check_result=fc_res_matches
            )
        self.assertIn(
            "fact_check_result with matches=1 supplied but fact_check status in hybrid_result is NO_EVIDENCE",
            str(ctx.exception),
        )

        # matches == 0 supplied while AVAILABLE
        with self.assertRaises(ExplainabilityInputError) as ctx:
            self.service.generate_explainability(
                self.hybrid_res, self.verdict_res, fact_check_result=fc_res_empty
            )
        self.assertIn(
            "fact_check_result with 0 matches supplied but fact_check status in hybrid_result is AVAILABLE",
            str(ctx.exception),
        )

    def test_positive_similarity_metrics_with_no_narrative_evidence_rejected(self):
        sim_positive = SimilarityMetrics(
            highest_similarity_score=0.85,
            average_similarity_score=0.85,
            related_claims_count=1,
        )
        hybrid_no_narrative = _build_nominal_hybrid_result(
            signal_statuses={
                COMPONENT_MODEL: SignalStatus.AVAILABLE,
                COMPONENT_FACT_CHECK: SignalStatus.AVAILABLE,
                COMPONENT_NARRATIVE: SignalStatus.NO_EVIDENCE,
                COMPONENT_RULE_ENGINE: SignalStatus.AVAILABLE,
            }
        )
        with self.assertRaises(ExplainabilityInputError) as ctx:
            self.service.generate_explainability(
                hybrid_no_narrative, self.verdict_res, similarity_metrics=sim_positive
            )
        self.assertIn(
            "similarity_metrics with positive matches supplied", str(ctx.exception)
        )


class ModelExplanationTests(SimpleTestCase):
    """Verifies FULL, SUMMARY_ONLY, NO_EVIDENCE, and FAILED states for AI Model."""

    def setUp(self):
        self.service = ExplainabilityService()
        self.hybrid_res = _build_nominal_hybrid_result()
        self.verdict_res = _build_nominal_verdict_result()

    def test_full_model_explanation(self):
        model_out = ModelOutput(prediction=ModelPrediction.CREDIBLE, confidence=0.96)
        res = self.service.generate_explainability(
            self.hybrid_res, self.verdict_res, model_output=model_out
        )
        model_exp = res.model_explanation
        self.assertEqual(model_exp["detail_status"], DETAIL_FULL)
        self.assertEqual(model_exp["prediction"], "CREDIBLE")
        self.assertEqual(model_exp["confidence"], 0.96)
        self.assertEqual(model_exp["component_score"], 0.96)
        self.assertIn("96.0% confidence", model_exp["summary"])

    def test_summary_only_model_explanation(self):
        # model_output omitted while AVAILABLE
        res = self.service.generate_explainability(
            self.hybrid_res, self.verdict_res, model_output=None
        )
        model_exp = res.model_explanation
        self.assertEqual(model_exp["detail_status"], DETAIL_SUMMARY_ONLY)
        self.assertIsNone(model_exp["prediction"])
        self.assertIsNone(model_exp["confidence"])
        self.assertEqual(model_exp["component_score"], 0.96)
        self.assertIn(
            "detailed prediction/confidence object was not supplied",
            model_exp["summary"],
        )


class FactCheckExplanationTests(SimpleTestCase):
    """Verifies fact-check explanation, conflict preservation, and source integrity."""

    def setUp(self):
        self.service = ExplainabilityService()
        self.hybrid_res = _build_nominal_hybrid_result()
        self.verdict_res = _build_nominal_verdict_result()

    def test_full_fact_check_explanation(self):
        ev = FactCheckEvidenceItem(
            publisher="FactCheck.org",
            rating="Mostly True",
            url="https://factcheck.org/1",
            review_date="2026-05-01",
        )
        fc_res = FactCheckResult(
            matches=1,
            sources=(ev,),
            summary="Claim verified mostly true by FactCheck.org",
            evidence_urls=("https://factcheck.org/1",),
        )
        res = self.service.generate_explainability(
            self.hybrid_res, self.verdict_res, fact_check_result=fc_res
        )
        fc_exp = res.fact_check_explanation
        self.assertEqual(fc_exp["detail_status"], DETAIL_FULL)
        self.assertEqual(fc_exp["matches_count"], 1)
        self.assertFalse(fc_exp["has_conflict"])
        self.assertEqual(len(fc_exp["sources"]), 1)
        self.assertEqual(fc_exp["sources"][0]["publisher"], "FactCheck.org")
        self.assertEqual(fc_exp["sources"][0]["rating"], "Mostly True")

    def test_fact_check_conflict_reflected(self):
        hybrid_conflict = _build_nominal_hybrid_result(
            fact_check_conflict=True,
            confidence_level="LOW",
        )
        verdict_conflict = _build_nominal_verdict_result(
            fact_check_conflict=True,
            confidence_level="LOW",
        )
        res = self.service.generate_explainability(
            hybrid_conflict, verdict_conflict, fact_check_result=None
        )
        self.assertTrue(res.fact_check_explanation["has_conflict"])
        self.assertTrue(
            any("conflicting ratings across publishers" in s for s in res.reasoning)
        )


class NarrativeAndSimilarityTests(SimpleTestCase):
    """Verifies the five narrative availability states and AI-007 boundary."""

    def setUp(self):
        self.service = ExplainabilityService()
        self.hybrid_res = _build_nominal_hybrid_result()
        self.verdict_res = _build_nominal_verdict_result()

    def test_narrative_zero_matches_completed(self):
        act_zero = NarrativeActivity.empty(evaluated_candidates_count=10)
        res = self.service.generate_explainability(
            self.hybrid_res, self.verdict_res, narrative_activity=act_zero
        )
        narr_exp = res.narrative_explanation
        self.assertEqual(narr_exp["detail_status"], DETAIL_FULL)
        self.assertEqual(narr_exp["similar_claims_count"], 0)
        self.assertFalse(narr_exp["is_scorable"])
        self.assertIn("zero matching claims", narr_exp["summary"])

    def test_narrative_positive_recurrence(self):
        m = NarrativeMatchRecord(
            claim_id=uuid.uuid4(),
            similarity_score=0.88,
            submitted_at=datetime(2026, 4, 15, tzinfo=timezone.utc),
        )
        act = NarrativeActivity(
            similar_claims_count=1,
            first_seen=datetime(2026, 4, 15, tzinfo=timezone.utc),
            latest_occurrence=datetime(2026, 4, 15, tzinfo=timezone.utc),
            activity_level="LOW",
            evaluated_candidates_count=10,
            matches=(m,),
        )
        res = self.service.generate_explainability(
            self.hybrid_res, self.verdict_res, narrative_activity=act
        )
        narr_exp = res.narrative_explanation
        self.assertEqual(narr_exp["detail_status"], DETAIL_FULL)
        self.assertEqual(narr_exp["similar_claims_count"], 1)
        self.assertIn(
            "Historical narrative recurrence detected across 1 similar claims",
            narr_exp["summary"],
        )
        self.assertIn("excluded from numeric truth aggregation", narr_exp["summary"])

    def test_narrative_no_evidence_state(self):
        hybrid_no_ev = _build_nominal_hybrid_result(
            signal_statuses={
                COMPONENT_MODEL: SignalStatus.AVAILABLE,
                COMPONENT_FACT_CHECK: SignalStatus.AVAILABLE,
                COMPONENT_NARRATIVE: SignalStatus.NO_EVIDENCE,
                COMPONENT_RULE_ENGINE: SignalStatus.AVAILABLE,
            }
        )
        res = self.service.generate_explainability(
            hybrid_no_ev, self.verdict_res, narrative_activity=None
        )
        narr_exp = res.narrative_explanation
        self.assertEqual(narr_exp["detail_status"], DETAIL_NO_EVIDENCE)
        self.assertIn(
            "Narrative evaluation was not performed or provided no evidence",
            narr_exp["summary"],
        )

    def test_narrative_failed_state(self):
        hybrid_failed = _build_nominal_hybrid_result(
            signal_statuses={
                COMPONENT_MODEL: SignalStatus.AVAILABLE,
                COMPONENT_FACT_CHECK: SignalStatus.AVAILABLE,
                COMPONENT_NARRATIVE: SignalStatus.FAILED,
                COMPONENT_RULE_ENGINE: SignalStatus.AVAILABLE,
            },
            failed_components=(COMPONENT_NARRATIVE,),
            error_details={COMPONENT_NARRATIVE: "Embedding server timeout"},
        )
        verdict_failed = _build_nominal_verdict_result(
            failed_components=(COMPONENT_NARRATIVE,),
            error_details={COMPONENT_NARRATIVE: "Embedding server timeout"},
        )
        res = self.service.generate_explainability(
            hybrid_failed, verdict_failed, narrative_activity=None
        )
        narr_exp = res.narrative_explanation
        self.assertEqual(narr_exp["detail_status"], DETAIL_FAILED)
        self.assertIn(
            "Narrative activity evaluation failed during processing",
            narr_exp["summary"],
        )
        self.assertEqual(
            res.diagnostics["error_details"]["narrative"], "Embedding server timeout"
        )

    def test_narrative_unscorable_with_context_unavailable(self):
        # signal_status is UNSCORABLE, but narrative_activity is None and narrative_context is None
        hybrid_no_ctx = _build_nominal_hybrid_result(narrative_context=None)
        res = self.service.generate_explainability(
            hybrid_no_ctx, self.verdict_res, narrative_activity=None
        )
        narr_exp = res.narrative_explanation
        self.assertEqual(narr_exp["detail_status"], DETAIL_CONTEXT_UNAVAILABLE)
        self.assertIn(
            "detailed narrative context was not supplied", narr_exp["summary"]
        )

    def test_similarity_not_supplied_when_metrics_omitted(self):
        # AI-011 must NOT recalculate similarity even if narrative activity exists
        act_zero = NarrativeActivity.empty(evaluated_candidates_count=5)
        res = self.service.generate_explainability(
            self.hybrid_res,
            self.verdict_res,
            narrative_activity=act_zero,
            similarity_metrics=None,
        )
        sim_exp = res.similarity_explanation
        self.assertEqual(sim_exp["detail_status"], DETAIL_NOT_SUPPLIED)
        self.assertIsNone(sim_exp["highest_similarity_score"])
        self.assertIsNone(sim_exp["average_similarity_score"])
        self.assertIsNone(sim_exp["related_claims_count"])
        self.assertIsNone(sim_exp["has_matches"])

    def test_similarity_full_when_metrics_supplied(self):
        sim = SimilarityMetrics(
            highest_similarity_score=0.91,
            average_similarity_score=0.82,
            related_claims_count=3,
        )
        res = self.service.generate_explainability(
            self.hybrid_res, self.verdict_res, similarity_metrics=sim
        )
        sim_exp = res.similarity_explanation
        self.assertEqual(sim_exp["detail_status"], DETAIL_FULL)
        self.assertEqual(sim_exp["highest_similarity_score"], 0.91)
        self.assertEqual(sim_exp["average_similarity_score"], 0.82)
        self.assertEqual(sim_exp["related_claims_count"], 3)
        self.assertTrue(sim_exp["has_matches"])


class RuleEngineExplanationTests(SimpleTestCase):
    """Verifies rule engine explanation and observation preservation."""

    def setUp(self):
        self.service = ExplainabilityService()
        self.hybrid_res = _build_nominal_hybrid_result()
        self.verdict_res = _build_nominal_verdict_result()

    def test_full_rule_explanation(self):
        rule_res = RuleValidationResult(
            flags={
                "excessive_capitalization": False,
                "duplicate_punctuation": False,
                "clickbait_phrases": False,
                "sensational_language": True,
                "short_or_vague_claim": False,
                "spam_patterns": False,
            },
            triggered_count=1,
            credibility_penalty=0.05,
            rule_score=0.95,
            observations=("Sensational or alarmist language detected.",),
        )
        res = self.service.generate_explainability(
            self.hybrid_res, self.verdict_res, rule_validation_result=rule_res
        )
        rule_exp = res.rule_explanation
        self.assertEqual(rule_exp["detail_status"], DETAIL_FULL)
        self.assertEqual(rule_exp["penalty_applied"], 0.05)
        self.assertEqual(list(rule_exp["flags_triggered"]), ["sensational_language"])
        self.assertEqual(
            list(rule_exp["observations"]),
            ["Sensational or alarmist language detected."],
        )


class NumericalIntegrityTests(SimpleTestCase):
    """Verifies numerical score preservation, genuine zero handling, and no recalculation."""

    def setUp(self):
        self.service = ExplainabilityService()

    def test_exact_preservation_of_ai009_scores_and_contributions(self):
        hybrid_res = _build_nominal_hybrid_result()
        verdict_res = _build_nominal_verdict_result()

        res = self.service.generate_explainability(hybrid_res, verdict_res)

        # Invariable passthrough of AI-009 values
        self.assertEqual(res.credibility_score, 88.4)
        self.assertEqual(
            res.score_breakdown[COMPONENT_MODEL]["weighted_contribution"], 39.53
        )
        self.assertEqual(
            res.score_breakdown[COMPONENT_FACT_CHECK]["weighted_contribution"], 37.65
        )
        self.assertEqual(
            res.score_breakdown[COMPONENT_RULE_ENGINE]["weighted_contribution"], 11.18
        )
        self.assertEqual(
            res.score_breakdown[COMPONENT_NARRATIVE]["weighted_contribution"], 0.0
        )
        self.assertEqual(res.coverage_ratio, 0.85)

    def test_genuine_zero_component_score_vs_missing_score(self):
        # Model evaluates claim as 0.0 credibility (e.g. 100% confidence Misinformation)
        hybrid_res = _build_nominal_hybrid_result(
            component_scores={
                COMPONENT_MODEL: 0.0,
                COMPONENT_FACT_CHECK: 0.80,
                COMPONENT_NARRATIVE: None,  # Excluded
                COMPONENT_RULE_ENGINE: None,  # No evidence
            },
            signal_statuses={
                COMPONENT_MODEL: SignalStatus.AVAILABLE,
                COMPONENT_FACT_CHECK: SignalStatus.AVAILABLE,
                COMPONENT_NARRATIVE: SignalStatus.UNSCORABLE,
                COMPONENT_RULE_ENGINE: SignalStatus.NO_EVIDENCE,
            },
            weighted_contributions={
                COMPONENT_MODEL: 0.0,
                COMPONENT_FACT_CHECK: 42.67,
                COMPONENT_NARRATIVE: 0.0,
                COMPONENT_RULE_ENGINE: 0.0,
            },
        )
        verdict_res = _build_nominal_verdict_result()

        res = self.service.generate_explainability(hybrid_res, verdict_res)

        # Genuine zero score must remain 0.0
        self.assertEqual(res.score_breakdown[COMPONENT_MODEL]["component_score"], 0.0)
        self.assertEqual(res.model_explanation["component_score"], 0.0)

        # Missing scores must remain None
        self.assertIsNone(res.score_breakdown[COMPONENT_NARRATIVE]["component_score"])
        self.assertIsNone(res.score_breakdown[COMPONENT_RULE_ENGINE]["component_score"])


class InsufficientEvidenceAndPartialFailureTests(SimpleTestCase):
    """Verifies explanation behavior under insufficient evidence and partial failure."""

    def setUp(self):
        self.service = ExplainabilityService()

    def test_insufficient_evidence_explanation(self):
        hybrid_res = _build_nominal_hybrid_result(
            credibility_score=None,
            overall_status=HybridAnalysisStatus.INSUFFICIENT_EVIDENCE,
            confidence_level="NONE",
            coverage_ratio=0.10,
            component_scores={
                COMPONENT_MODEL: None,
                COMPONENT_FACT_CHECK: None,
                COMPONENT_NARRATIVE: None,
                COMPONENT_RULE_ENGINE: 0.95,
            },
            signal_statuses={
                COMPONENT_MODEL: SignalStatus.FAILED,
                COMPONENT_FACT_CHECK: SignalStatus.NO_EVIDENCE,
                COMPONENT_NARRATIVE: SignalStatus.NO_EVIDENCE,
                COMPONENT_RULE_ENGINE: SignalStatus.AVAILABLE,
            },
            failed_components=(COMPONENT_MODEL,),
            error_details={COMPONENT_MODEL: "Inference server error"},
        )
        verdict_res = _build_nominal_verdict_result(
            verdict=Verdict.UNCERTAIN,
            label="Uncertain",
            credibility_score=None,
            confidence_level="NONE",
            overall_status=HybridAnalysisStatus.INSUFFICIENT_EVIDENCE,
            is_definitive=False,
            failed_components=(COMPONENT_MODEL,),
            error_details={COMPONENT_MODEL: "Inference server error"},
            reason="Insufficient evidence: primary truth signals were unavailable.",
        )

        res = self.service.generate_explainability(hybrid_res, verdict_res)
        self.assertIsNone(res.credibility_score)
        self.assertEqual(res.verdict, Verdict.UNCERTAIN)
        self.assertEqual(res.confidence_level, "NONE")
        self.assertTrue(any("Primary truth signals" in s for s in res.reasoning))

    def test_partial_failure_diagnostics_preserved(self):
        hybrid_res = _build_nominal_hybrid_result(
            overall_status=HybridAnalysisStatus.PARTIAL_FAILURE,
            failed_components=(COMPONENT_FACT_CHECK,),
            error_details={COMPONENT_FACT_CHECK: "Fact check API rate limit"},
            signal_statuses={
                COMPONENT_MODEL: SignalStatus.AVAILABLE,
                COMPONENT_FACT_CHECK: SignalStatus.FAILED,
                COMPONENT_NARRATIVE: SignalStatus.UNSCORABLE,
                COMPONENT_RULE_ENGINE: SignalStatus.AVAILABLE,
            },
        )
        verdict_res = _build_nominal_verdict_result(
            overall_status=HybridAnalysisStatus.PARTIAL_FAILURE,
            failed_components=(COMPONENT_FACT_CHECK,),
            error_details={COMPONENT_FACT_CHECK: "Fact check API rate limit"},
        )

        res = self.service.generate_explainability(hybrid_res, verdict_res)
        self.assertEqual(res.overall_status, HybridAnalysisStatus.PARTIAL_FAILURE)
        self.assertIn("fact_check", res.diagnostics["failed_components"])
        self.assertTrue(
            any(
                "Analysis was evaluated under partial component failure: [fact_check]"
                in s
                for s in res.reasoning
            )
        )


class SerializationAndSecurityTests(SimpleTestCase):
    """Verifies immutability, JSON serializability, and public vs internal separation."""

    def setUp(self):
        self.service = ExplainabilityService()
        self.hybrid_res = _build_nominal_hybrid_result(
            failed_components=(COMPONENT_NARRATIVE,),
            error_details={COMPONENT_NARRATIVE: "Secret API token error at 10.0.0.1"},
            signal_statuses={
                COMPONENT_MODEL: SignalStatus.AVAILABLE,
                COMPONENT_FACT_CHECK: SignalStatus.AVAILABLE,
                COMPONENT_NARRATIVE: SignalStatus.FAILED,
                COMPONENT_RULE_ENGINE: SignalStatus.AVAILABLE,
            },
        )
        self.verdict_res = _build_nominal_verdict_result(
            failed_components=(COMPONENT_NARRATIVE,),
            error_details={COMPONENT_NARRATIVE: "Secret API token error at 10.0.0.1"},
        )
        self.res = self.service.generate_explainability(
            self.hybrid_res, self.verdict_res
        )

    def test_explainability_result_is_frozen(self):
        with self.assertRaises(Exception):
            self.res.credibility_score = 90.0  # type: ignore[misc]

    def test_nested_mappings_reject_in_place_mutation(self):
        with self.assertRaises(TypeError):
            self.res.score_breakdown[COMPONENT_MODEL]["score"] = 1.0  # type: ignore[index]

    def test_to_dict_excludes_raw_error_details(self):
        public_data = self.res.to_dict()

        # Public data must not contain internal diagnostics or secret error messages
        self.assertNotIn("diagnostics", public_data)
        self.assertNotIn("Secret API token", json.dumps(public_data))
        self.assertNotIn("thresholds", public_data)
        self.assertEqual(public_data["failed_components"], ["narrative"])

    def test_to_internal_dict_preserves_forensic_diagnostics(self):
        internal_data = self.res.to_internal_dict()

        self.assertIn("diagnostics", internal_data)
        self.assertIn("thresholds", internal_data["diagnostics"])
        self.assertIn("error_details", internal_data["diagnostics"])
        self.assertEqual(
            internal_data["diagnostics"]["error_details"]["narrative"],
            "Secret API token error at 10.0.0.1",
        )

    def test_both_serializations_are_json_compatible(self):
        public_json = json.dumps(self.res.to_dict())
        internal_json = json.dumps(self.res.to_internal_dict())

        self.assertIsInstance(public_json, str)
        self.assertIsInstance(internal_json, str)

        deserialized_pub = json.loads(public_json)
        self.assertEqual(deserialized_pub["verdict"], "CREDIBLE")
        self.assertEqual(deserialized_pub["credibility_score"], 88.4)


class ArchitecturalIsolationTests(SimpleTestCase):
    """Verifies that AI-011 makes zero database, network, or ML inference calls."""

    def test_zero_upstream_service_invocations(self):
        service = ExplainabilityService()
        hybrid_res = _build_nominal_hybrid_result()
        verdict_res = _build_nominal_verdict_result()

        with (
            patch("analysis.inference.adapter.ModelAdapterProtocol") as mock_model,
            patch("analysis.services.fact_check.FactCheckService") as mock_fc,
            patch("analysis.services.narrative.NarrativeActivityService") as mock_narr,
            patch("analysis.services.similarity.SimilarityScoringService") as mock_sim,
            patch("analysis.services.rules.RuleEngineService") as mock_rules,
        ):
            res = service.generate_explainability(hybrid_res, verdict_res)

            mock_model.assert_not_called()
            mock_fc.assert_not_called()
            mock_narr.assert_not_called()
            mock_sim.assert_not_called()
            mock_rules.assert_not_called()

        self.assertEqual(res.verdict, Verdict.CREDIBLE)

"""
Tests for Analysis Persistence Service (AI-012).
Verifies input validation, authoritative database soft-deletion checks,
nominal field mapping, null and insufficient evidence handling, genuine zero preservation,
duplicate prevention, transaction rollback, architectural isolation, and PostgreSQL concurrency.
"""

import threading
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from analysis.models import Analysis, Verdict
from analysis.services.explainability import ExplainabilityResult
from analysis.services.hybrid import HybridAnalysisStatus
from analysis.services.persistence import (
    AnalysisAlreadyExistsError,
    AnalysisPersistenceError,
    AnalysisPersistenceInputError,
    AnalysisPersistenceService,
)
from claims.models import Claim, ClaimStatus

User = get_user_model()


def _build_nominal_explainability_result(
    *,
    verdict: Verdict = Verdict.CREDIBLE,
    verdict_label: str = "Likely Credible",
    credibility_score: float | None = 88.4,
    confidence_level: str = "HIGH",
    overall_status: HybridAnalysisStatus = HybridAnalysisStatus.COMPLETED,
    is_definitive: bool = True,
    verdict_reason: str = "Credibility score 88.4 meets or exceeds credible threshold (70.0).",
    reasoning: tuple[str, ...] = (
        "Fine-tuned classification model predicted the claim is credible with 96.0% confidence.",
    ),
    score_breakdown: dict | None = None,
    effective_weights: dict | None = None,
    coverage_ratio: float = 0.85,
    model_explanation: dict | None = None,
    fact_check_explanation: dict | None = None,
    narrative_explanation: dict | None = None,
    rule_explanation: dict | None = None,
    similarity_explanation: dict | None = None,
    diagnostics: dict | None = None,
) -> ExplainabilityResult:
    return ExplainabilityResult(
        verdict=verdict,
        verdict_label=verdict_label,
        credibility_score=credibility_score,
        confidence_level=confidence_level,
        overall_status=overall_status,
        is_definitive=is_definitive,
        verdict_reason=verdict_reason,
        reasoning=reasoning,
        score_breakdown=score_breakdown
        or {
            "model": {
                "component_score": 0.96,
                "effective_weight": 0.41,
                "weighted_contribution": 39.53,
                "status": "AVAILABLE",
            },
            "fact_check": {
                "component_score": 0.80,
                "effective_weight": 0.47,
                "weighted_contribution": 37.65,
                "status": "AVAILABLE",
            },
            "narrative": {
                "component_score": None,
                "effective_weight": 0.0,
                "weighted_contribution": 0.0,
                "status": "UNSCORABLE",
            },
            "rule_engine": {
                "component_score": 0.95,
                "effective_weight": 0.12,
                "weighted_contribution": 11.18,
                "status": "AVAILABLE",
            },
        },
        effective_weights=effective_weights
        or {
            "model": 0.41,
            "fact_check": 0.47,
            "narrative": 0.0,
            "rule_engine": 0.12,
        },
        coverage_ratio=coverage_ratio,
        model_explanation=model_explanation
        or {
            "detail_status": "FULL",
            "signal_status": "AVAILABLE",
            "component_score": 0.96,
            "effective_weight": 0.41,
            "weighted_contribution": 39.53,
            "prediction": "CREDIBLE",
            "confidence": 0.96,
            "summary": "Fine-tuned classification model predicted the claim is credible with 96.0% confidence.",
        },
        fact_check_explanation=fact_check_explanation
        or {
            "detail_status": "FULL",
            "signal_status": "AVAILABLE",
            "component_score": 0.80,
            "effective_weight": 0.47,
            "weighted_contribution": 37.65,
            "has_conflict": False,
            "matches_count": 2,
            "summary": "External fact-checking evidence confirmed 2 matching review(s).",
            "sources": (),
        },
        narrative_explanation=narrative_explanation
        or {
            "detail_status": "FULL",
            "signal_status": "UNSCORABLE",
            "is_scorable": False,
            "effective_weight": 0.0,
            "weighted_contribution": 0.0,
            "similar_claims_count": 1,
            "activity_level": "LOW",
            "first_seen": "2026-04-15",
            "latest_occurrence": "2026-04-15",
            "summary": "Historical narrative recurrence detected across 1 similar claims.",
        },
        rule_explanation=rule_explanation
        or {
            "detail_status": "FULL",
            "signal_status": "AVAILABLE",
            "component_score": 0.95,
            "effective_weight": 0.12,
            "weighted_contribution": 11.18,
            "penalty_applied": 0.05,
            "flags_triggered": ("sensational_language",),
            "observations": ("Sensational or alarmist language detected.",),
            "summary": "Rule heuristics triggered 1 flag(s) with a 0.05 credibility penalty.",
        },
        similarity_explanation=similarity_explanation
        or {
            "detail_status": "FULL",
            "highest_similarity_score": 0.88,
            "average_similarity_score": 0.88,
            "related_claims_count": 1,
            "has_matches": True,
            "summary": "Semantic similarity analysis identified 1 related claim(s).",
        },
        diagnostics=diagnostics
        or {
            "failed_components": (),
            "error_details": {},
            "thresholds": {"credible": 70.0, "uncertain": 40.0},
            "signal_statuses": {
                "model": "AVAILABLE",
                "fact_check": "AVAILABLE",
                "narrative": "UNSCORABLE",
                "rule_engine": "AVAILABLE",
            },
            "coverage_ratio": 0.85,
        },
    )


class AnalysisPersistenceServiceTests(TestCase):
    """Standard unit and persistence tests covering validation, mapping, nulls, and rollback."""

    def setUp(self):
        self.service = AnalysisPersistenceService()
        self.user = User.objects.create_user(
            email="persistence_test@example.com",
            password="Password123!",
            full_name="Persistence Tester",
        )
        self.claim = Claim.objects.create(
            user=self.user,
            text="Valid test claim for AI-012 persistence testing.",
            status=ClaimStatus.PENDING,
            is_deleted=False,
        )
        self.explainability_res = _build_nominal_explainability_result()

    # -----------------------------------------------------------------------
    # A. Input Validation & Exception Hierarchy
    # -----------------------------------------------------------------------

    def test_exception_hierarchy(self):
        self.assertTrue(
            issubclass(AnalysisPersistenceInputError, AnalysisPersistenceError)
        )
        self.assertTrue(
            issubclass(AnalysisAlreadyExistsError, AnalysisPersistenceError)
        )
        self.assertTrue(issubclass(AnalysisPersistenceError, RuntimeError))

    def test_unsaved_claim_rejected(self):
        unsaved_claim = Claim(
            user=self.user,
            text="Unsaved claim without pk.",
        )
        with self.assertRaises(AnalysisPersistenceInputError):
            self.service.persist_analysis(
                claim=unsaved_claim,
                explainability_result=self.explainability_res,
            )

    def test_unsaved_claim_with_manually_assigned_pk_rejected(self):
        # Manually assigned PK on an unsaved instance where _state.adding is True
        unsaved_with_pk = Claim(
            id=self.claim.id,  # Matches an existing claim ID in the DB
            user=self.user,
            text="Unsaved instance with manually assigned PK.",
        )
        self.assertTrue(unsaved_with_pk._state.adding)
        with self.assertRaises(AnalysisPersistenceInputError):
            self.service.persist_analysis(
                claim=unsaved_with_pk,
                explainability_result=self.explainability_res,
            )

    def test_invalid_claim_object_rejected(self):
        with self.assertRaises(AnalysisPersistenceInputError):
            self.service.persist_analysis(
                claim="not-a-claim-object",  # type: ignore[arg-type]
                explainability_result=self.explainability_res,
            )

    def test_invalid_explainability_result_rejected(self):
        with self.assertRaises(AnalysisPersistenceInputError):
            self.service.persist_analysis(
                claim=self.claim,
                explainability_result={"not": "an-explainability-result"},  # type: ignore[arg-type]
            )

    def test_nonexistent_database_claim_rejected(self):
        # Claim instance that is saved then hard-deleted from database
        claim_to_delete = Claim.objects.create(
            user=self.user,
            text="Claim that will be hard deleted.",
        )
        Claim.objects.filter(pk=claim_to_delete.pk).delete()
        with self.assertRaises(AnalysisPersistenceInputError):
            self.service.persist_analysis(
                claim=claim_to_delete,
                explainability_result=self.explainability_res,
            )

    # -----------------------------------------------------------------------
    # B. Soft Deletion
    # -----------------------------------------------------------------------

    def test_soft_deleted_claim_rejected(self):
        soft_deleted_claim = Claim.objects.create(
            user=self.user,
            text="Soft-deleted claim text.",
            is_deleted=True,
        )
        with self.assertRaises(AnalysisPersistenceInputError):
            self.service.persist_analysis(
                claim=soft_deleted_claim,
                explainability_result=self.explainability_res,
            )

    def test_authoritative_database_soft_deletion_check(self):
        # In-memory claim has is_deleted=False, but database state was concurrently updated to True
        stale_claim = Claim.objects.get(pk=self.claim.pk)
        self.assertFalse(stale_claim.is_deleted)

        Claim.objects.filter(pk=self.claim.pk).update(is_deleted=True)

        with self.assertRaises(AnalysisPersistenceInputError):
            self.service.persist_analysis(
                claim=stale_claim,
                explainability_result=self.explainability_res,
            )

    # -----------------------------------------------------------------------
    # C. Successful Persistence and Mapping
    # -----------------------------------------------------------------------

    def test_successful_nominal_persistence(self):
        analysis = self.service.persist_analysis(
            claim=self.claim,
            explainability_result=self.explainability_res,
        )
        self.assertIsNotNone(analysis)
        self.assertEqual(analysis.credibility_score, 88.4)
        self.assertEqual(analysis.verdict, "CREDIBLE")
        self.assertEqual(analysis.model_prediction, "CREDIBLE")
        self.assertEqual(analysis.model_confidence, 0.96)
        self.assertEqual(
            analysis.fact_check_summary,
            "External fact-checking evidence confirmed 2 matching review(s).",
        )
        self.assertEqual(analysis.fact_check_match_count, 2)
        self.assertEqual(analysis.narrative_match_count, 1)
        self.assertEqual(analysis.highest_similarity_score, 0.88)
        self.assertEqual(analysis.rule_based_flags, {"sensational_language": True})
        self.assertEqual(analysis.final_weighted_score, 88.4)

    def test_claim_relationship_linkage(self):
        analysis = self.service.persist_analysis(
            claim=self.claim,
            explainability_result=self.explainability_res,
        )
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.analysis, analysis)
        self.assertEqual(analysis.claim, self.claim)

    def test_correct_primary_key_relationship(self):
        analysis = self.service.persist_analysis(
            claim=self.claim,
            explainability_result=self.explainability_res,
        )
        self.assertEqual(analysis.pk, self.claim.pk)
        self.assertEqual(analysis.claim_id, self.claim.id)

    def test_exact_internal_json_persistence(self):
        analysis = self.service.persist_analysis(
            claim=self.claim,
            explainability_result=self.explainability_res,
        )
        expected_json = self.explainability_res.to_internal_dict()
        self.assertEqual(analysis.explainability_json, expected_json)
        self.assertIn("diagnostics", analysis.explainability_json)
        self.assertEqual(
            analysis.explainability_json["diagnostics"]["thresholds"],
            {"credible": 70.0, "uncertain": 40.0},
        )

    def test_component_metrics_mapping(self):
        analysis = self.service.persist_analysis(
            claim=self.claim,
            explainability_result=self.explainability_res,
        )
        self.assertEqual(analysis.fact_check_match_count, 2)
        self.assertEqual(analysis.narrative_match_count, 1)
        self.assertEqual(analysis.highest_similarity_score, 0.88)
        self.assertEqual(analysis.rule_based_flags, {"sensational_language": True})

    def test_timestamp_auto_generated(self):
        before = timezone.now()
        analysis = self.service.persist_analysis(
            claim=self.claim,
            explainability_result=self.explainability_res,
        )
        after = timezone.now()
        self.assertIsNotNone(analysis.analysis_timestamp)
        self.assertTrue(before <= analysis.analysis_timestamp <= after)

    # -----------------------------------------------------------------------
    # D. Null and Score Handling
    # -----------------------------------------------------------------------

    def test_insufficient_evidence_persistence(self):
        insufficient_res = _build_nominal_explainability_result(
            verdict=Verdict.UNCERTAIN,
            verdict_label="Uncertain",
            credibility_score=None,
            confidence_level="NONE",
            overall_status=HybridAnalysisStatus.INSUFFICIENT_EVIDENCE,
            is_definitive=False,
            model_explanation={
                "detail_status": "NO_EVIDENCE",
                "signal_status": "NO_EVIDENCE",
                "component_score": None,
                "effective_weight": 0.0,
                "weighted_contribution": 0.0,
                "prediction": None,
                "confidence": None,
                "summary": "AI classification model inference was not provided for this claim.",
            },
            fact_check_explanation={
                "detail_status": "NO_EVIDENCE",
                "signal_status": "NO_EVIDENCE",
                "component_score": None,
                "effective_weight": 0.0,
                "weighted_contribution": 0.0,
                "has_conflict": False,
                "matches_count": None,
                "summary": "No external fact-check reviews were found for this claim.",
                "sources": (),
            },
            narrative_explanation={
                "detail_status": "NO_EVIDENCE",
                "signal_status": "NO_EVIDENCE",
                "is_scorable": False,
                "effective_weight": 0.0,
                "weighted_contribution": 0.0,
                "similar_claims_count": None,
                "activity_level": "NONE",
                "first_seen": None,
                "latest_occurrence": None,
                "summary": "Narrative evaluation was not performed or provided no evidence.",
            },
            rule_explanation={
                "detail_status": "FULL",
                "signal_status": "AVAILABLE",
                "component_score": 0.95,
                "effective_weight": 0.12,
                "weighted_contribution": 11.18,
                "penalty_applied": 0.0,
                "flags_triggered": (),
                "observations": (),
                "summary": "Deterministic rule heuristics detected no sensationalism.",
            },
            similarity_explanation={
                "detail_status": "NO_EVIDENCE",
                "highest_similarity_score": None,
                "average_similarity_score": None,
                "related_claims_count": None,
                "has_matches": None,
                "summary": "Similarity metrics are unavailable.",
            },
        )
        analysis = self.service.persist_analysis(
            claim=self.claim,
            explainability_result=insufficient_res,
        )
        analysis.refresh_from_db()
        self.assertIsNone(analysis.credibility_score)
        self.assertIsNone(analysis.final_weighted_score)
        self.assertEqual(analysis.verdict, "UNCERTAIN")
        self.assertIsNone(analysis.model_prediction)
        self.assertIsNone(analysis.model_confidence)
        self.assertIsNone(analysis.fact_check_match_count)
        self.assertIsNone(analysis.narrative_match_count)
        self.assertIsNone(analysis.highest_similarity_score)

    def test_genuine_zero_score_preserved(self):
        zero_res = _build_nominal_explainability_result(
            verdict=Verdict.MISINFORMATION,
            verdict_label="Likely Misinformation",
            credibility_score=0.0,
            confidence_level="HIGH",
            overall_status=HybridAnalysisStatus.COMPLETED,
            is_definitive=True,
        )
        analysis = self.service.persist_analysis(
            claim=self.claim,
            explainability_result=zero_res,
        )
        analysis.refresh_from_db()
        self.assertEqual(analysis.credibility_score, 0.0)
        self.assertEqual(analysis.final_weighted_score, 0.0)
        self.assertIsNotNone(analysis.credibility_score)

    def test_partial_failure_diagnostics_preserved(self):
        partial_res = _build_nominal_explainability_result(
            overall_status=HybridAnalysisStatus.PARTIAL_FAILURE,
            diagnostics={
                "failed_components": ("fact_check",),
                "error_details": {"fact_check": "FactCheck API timeout at 10.0.0.1"},
                "thresholds": {"credible": 70.0, "uncertain": 40.0},
                "signal_statuses": {
                    "model": "AVAILABLE",
                    "fact_check": "FAILED",
                    "narrative": "UNSCORABLE",
                    "rule_engine": "AVAILABLE",
                },
                "coverage_ratio": 0.53,
            },
        )
        analysis = self.service.persist_analysis(
            claim=self.claim,
            explainability_result=partial_res,
        )
        diag = analysis.explainability_json["diagnostics"]
        self.assertIn("fact_check", diag["failed_components"])
        self.assertEqual(
            diag["error_details"]["fact_check"],
            "FactCheck API timeout at 10.0.0.1",
        )

    # -----------------------------------------------------------------------
    # E. Duplicate Prevention, Rollback, and Isolation
    # -----------------------------------------------------------------------

    def test_sequential_duplicate_persistence_rejected(self):
        self.service.persist_analysis(
            claim=self.claim,
            explainability_result=self.explainability_res,
        )
        with self.assertRaises(AnalysisAlreadyExistsError):
            self.service.persist_analysis(
                claim=self.claim,
                explainability_result=self.explainability_res,
            )

    def test_transaction_rollback_on_failure(self):
        original_create = Analysis.objects.create

        def create_and_raise(*args, **kwargs):
            # 1. Successfully execute the actual database INSERT inside the service atomic transaction
            instance = original_create(*args, **kwargs)
            self.assertIsNotNone(instance.pk)
            # 2. Deliberately raise RuntimeError before atomic block exits
            raise RuntimeError("Simulated failure after actual database write")

        with patch.object(Analysis.objects, "create", side_effect=create_and_raise):
            with self.assertRaises(RuntimeError) as ctx:
                self.service.persist_analysis(
                    claim=self.claim,
                    explainability_result=self.explainability_res,
                )
            self.assertIn(
                "Simulated failure after actual database write", str(ctx.exception)
            )

        # Assert that the transaction rolled back and no Analysis record was committed
        self.assertFalse(Analysis.objects.filter(claim=self.claim).exists())

    def test_claim_status_remains_unchanged(self):
        self.assertEqual(self.claim.status, ClaimStatus.PENDING)
        self.service.persist_analysis(
            claim=self.claim,
            explainability_result=self.explainability_res,
        )
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.PENDING)

    def test_zero_upstream_service_invocations(self):
        with (
            patch("analysis.inference.adapter.ModelAdapterProtocol") as mock_model,
            patch("analysis.services.fact_check.FactCheckService") as mock_fc,
            patch("analysis.services.narrative.NarrativeActivityService") as mock_narr,
            patch("analysis.services.similarity.SimilarityScoringService") as mock_sim,
            patch("analysis.services.rules.RuleEngineService") as mock_rules,
            patch("analysis.services.hybrid.HybridCredibilityEngine") as mock_hybrid,
            patch("analysis.services.verdict.VerdictService") as mock_verdict,
            patch(
                "analysis.services.explainability.ExplainabilityService"
            ) as mock_explain,
        ):
            analysis = self.service.persist_analysis(
                claim=self.claim,
                explainability_result=self.explainability_res,
            )
            self.assertIsNotNone(analysis)
            mock_model.assert_not_called()
            mock_fc.assert_not_called()
            mock_narr.assert_not_called()
            mock_sim.assert_not_called()
            mock_rules.assert_not_called()
            mock_hybrid.assert_not_called()
            mock_verdict.assert_not_called()
            mock_explain.assert_not_called()


class AnalysisPersistenceConcurrencyTests(TransactionTestCase):
    """
    Verifies that concurrent persistence calls targeting the same Claim row
    are deterministically serialized on PostgreSQL using select_for_update().
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="concurrency_test@example.com",
            password="Password123!",
            full_name="Concurrency Tester",
        )
        self.claim = Claim.objects.create(
            user=self.user,
            text="Claim for PostgreSQL concurrency testing with select_for_update().",
            status=ClaimStatus.PENDING,
            is_deleted=False,
        )
        self.explainability_res = _build_nominal_explainability_result()

    def test_concurrent_persistence_serialization_postgresql(self):
        self.assertEqual(
            connection.vendor,
            "postgresql",
            "This concurrency test specifically verifies PostgreSQL row locking behavior.",
        )
        barrier = threading.Barrier(2)
        results: list[Analysis] = []
        errors: list[Exception] = []

        def worker():
            close_old_connections()
            try:
                # Synchronize workers at the exact invocation boundary
                barrier.wait(timeout=5)
                service = AnalysisPersistenceService()
                res = service.persist_analysis(
                    claim=self.claim,
                    explainability_result=self.explainability_res,
                )
                results.append(res)
            except Exception as e:
                errors.append(e)
            finally:
                close_old_connections()

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)

        t1.start()
        t2.start()

        t1.join(timeout=10)
        t2.join(timeout=10)

        # Assert that both threads finished cleanly
        self.assertFalse(t1.is_alive(), "Worker thread 1 hung during execution.")
        self.assertFalse(t2.is_alive(), "Worker thread 2 hung during execution.")

        # Exactly one worker must succeed
        self.assertEqual(
            len(results),
            1,
            f"Expected exactly 1 success, got {len(results)}. Errors: {errors}",
        )
        self.assertEqual(results[0].pk, self.claim.pk)

        # Exactly one worker must fail with AnalysisAlreadyExistsError
        self.assertEqual(
            len(errors),
            1,
            f"Expected exactly 1 error, got {len(errors)}. Results: {results}",
        )
        self.assertIsInstance(errors[0], AnalysisAlreadyExistsError)

        # Confirm exactly one Analysis row exists in the database
        self.assertEqual(Analysis.objects.filter(claim=self.claim).count(), 1)

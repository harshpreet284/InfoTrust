"""
Comprehensive test suite for Analysis Pipeline Orchestration and Dispatcher (AI-014).
Validates:
1. Nominal lifecycle progression (PENDING -> PROCESSING -> COMPLETED).
2. Component resilience (operational errors absorbed via HybridCredibilityEngine).
3. Fatal pre-persistence errors (mark claim FAILED without creating Analysis).
4. Post-persistence safeguards (Zone 2 failures preserve Analysis and do not mark FAILED).
5. Lock-based ambiguous persistence reconciliation (TransactionTestCase with select_for_update).
6. Dispatcher bounded capacity control (semaphore admission, permit leak prevention, shutdown).
7. Submit claim on_commit dispatch integration (contract consistency, dispatch rejection).
8. Concurrency CAS invariants (race prevention and soft-deletion protection).
"""

import json
import math
import threading
import time
import uuid
from concurrent.futures import Future
from unittest.mock import MagicMock, patch

import numpy as np
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import (
    DatabaseError,
    OperationalError,
    close_old_connections,
    connection,
    transaction,
)
from django.test import Client, TestCase, TransactionTestCase

from analysis.inference.mock import MockModelAdapter
from analysis.models import Analysis, ModelPrediction, Verdict
from analysis.preprocessing import ClaimPreprocessingError
from analysis.services.dispatcher import (
    AnalysisPipelineDispatcher,
    set_pipeline_dispatcher,
)
from analysis.services.explainability import (
    ExplainabilityService,
)
from analysis.services.fact_check import (
    FactCheckAuthError,
    FactCheckConfigError,
    FactCheckEvidenceItem,
    FactCheckInputError,
    FactCheckResult,
    FactCheckService,
    FactCheckServiceError,
    FactCheckTimeoutError,
)
from analysis.services.hybrid import (
    HybridCredibilityEngine,
)
from analysis.services.inference import (
    InferenceServiceError,
    InvalidModelInputError,
    InvalidModelOutputError,
    ModelInferenceService,
)
from analysis.services.narrative import (
    NarrativeActivityService,
    NarrativeConfigError,
    NarrativeModelUnavailableError,
)
from analysis.services.persistence import (
    AnalysisPersistenceInputError,
    AnalysisPersistenceService,
)
from analysis.services.pipeline import AnalysisPipelineService
from analysis.services.rules import (
    RuleConfigError,
    RuleEngineError,
    RuleEngineService,
)
from analysis.services.similarity import (
    SimilarityCalculationError,
    SimilarityInputError,
    SimilarityScoringService,
)
from analysis.services.verdict import (
    VerdictService,
)
from claims.models import Claim, ClaimStatus
from claims.schemas import ClaimCreateSchema
from claims.services import submit_claim

User = get_user_model()


class MockEmbeddingGenerator:
    """Mock embedder to avoid loading PyTorch / SentenceTransformer."""

    def __init__(self, mapping: dict | None = None, dim: int = 4):
        self.mapping = mapping or {}
        self.dim = dim

    def embed(self, text: str):
        if text in self.mapping:
            return self.mapping[text]
        return np.ones(self.dim, dtype=np.float32)

    def embed_batch(self, texts, batch_size: int = 32):
        if self.mapping:
            out = [
                (
                    self.mapping[t]
                    if t in self.mapping
                    else np.ones(self.dim, dtype=np.float32)
                )
                for t in texts
            ]
            return np.array(out, dtype=np.float32)
        return np.ones((len(texts), self.dim), dtype=np.float32)


def _build_test_pipeline(
    *,
    model_service: ModelInferenceService | None = None,
    fact_check_service: FactCheckService | None = None,
    narrative_service: NarrativeActivityService | None = None,
    similarity_service: SimilarityScoringService | None = None,
    rule_service: RuleEngineService | None = None,
    hybrid_engine: HybridCredibilityEngine | None = None,
    verdict_service: VerdictService | None = None,
    explainability_service: ExplainabilityService | None = None,
    persistence_service: AnalysisPersistenceService | None = None,
) -> AnalysisPipelineService:
    """Constructs an AnalysisPipelineService with fast deterministic mock adapters."""
    if model_service is None:
        model_service = ModelInferenceService(
            adapter=MockModelAdapter(
                default_prediction=ModelPrediction.CREDIBLE,
                default_confidence=0.92,
            )
        )
    if fact_check_service is None:
        mock_fc = MagicMock(spec=FactCheckService)
        mock_fc.query.return_value = FactCheckResult.empty()
        fact_check_service = mock_fc
    if narrative_service is None:
        narrative_service = NarrativeActivityService(embedder=MockEmbeddingGenerator())
    if similarity_service is None:
        similarity_service = SimilarityScoringService()
    if rule_service is None:
        rule_service = RuleEngineService()
    if hybrid_engine is None:
        hybrid_engine = HybridCredibilityEngine()
    if verdict_service is None:
        verdict_service = VerdictService()
    if explainability_service is None:
        explainability_service = ExplainabilityService()
    if persistence_service is None:
        persistence_service = AnalysisPersistenceService()

    return AnalysisPipelineService(
        model_service=model_service,
        fact_check_service=fact_check_service,
        narrative_service=narrative_service,
        similarity_service=similarity_service,
        rule_service=rule_service,
        hybrid_engine=hybrid_engine,
        verdict_service=verdict_service,
        explainability_service=explainability_service,
        persistence_service=persistence_service,
    )


class NominalPipelineLifecycleTests(TestCase):
    """Verifies standard nominal progression PENDING -> PROCESSING -> COMPLETED."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="nominal_user@example.com",
            password="Password123!",
            full_name="Nominal User",
        )
        self.claim = Claim.objects.create(
            user=self.user,
            text="This is a fully valid claim text that passes text preprocessing.",
            status=ClaimStatus.PENDING,
            is_deleted=False,
        )
        self.service = _build_test_pipeline()

    def test_nominal_execution_progresses_pending_to_completed(self):
        self.assertEqual(self.claim.status, ClaimStatus.PENDING)
        self.service.run_pipeline(self.claim.id)

        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.COMPLETED)

        analysis = Analysis.objects.get(claim=self.claim)
        self.assertIsNotNone(analysis)
        self.assertEqual(analysis.verdict, Verdict.CREDIBLE.value)
        self.assertGreater(analysis.credibility_score, 0.0)
        self.assertIn("score_breakdown", analysis.explainability_json)
        self.assertIn("reasoning", analysis.explainability_json)

    def test_pipeline_skips_when_claim_is_already_processing(self):
        self.claim.status = ClaimStatus.PROCESSING
        self.claim.save()

        self.service.run_pipeline(self.claim.id)
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.PROCESSING)
        self.assertFalse(Analysis.objects.filter(claim=self.claim).exists())

    def test_pipeline_skips_when_claim_is_already_completed(self):
        self.claim.status = ClaimStatus.COMPLETED
        self.claim.save()

        self.service.run_pipeline(self.claim.id)
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.COMPLETED)
        self.assertFalse(Analysis.objects.filter(claim=self.claim).exists())

    def test_pipeline_skips_when_claim_is_already_failed(self):
        self.claim.status = ClaimStatus.FAILED
        self.claim.save()

        self.service.run_pipeline(self.claim.id)
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.FAILED)
        self.assertFalse(Analysis.objects.filter(claim=self.claim).exists())

    def test_pipeline_skips_when_claim_is_soft_deleted(self):
        self.claim.is_deleted = True
        self.claim.save()

        self.service.run_pipeline(self.claim.id)
        self.claim.refresh_from_db()
        self.assertTrue(self.claim.is_deleted)
        self.assertEqual(self.claim.status, ClaimStatus.PENDING)
        self.assertFalse(Analysis.objects.filter(claim=self.claim).exists())

    def test_pipeline_aborts_cleanly_on_nonexistent_claim(self):
        non_existent_id = uuid.uuid4()
        # Should not raise exception
        self.service.run_pipeline(non_existent_id)


class ComponentResiliencePipelineTests(TestCase):
    """Verifies that operational component errors are degraded via HybridCredibilityEngine."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="resilience_user@example.com",
            password="Password123!",
            full_name="Resilience User",
        )
        self.claim = Claim.objects.create(
            user=self.user,
            text="Valid claim statement submitted for resilience evaluation.",
            status=ClaimStatus.PENDING,
            is_deleted=False,
        )

    def test_model_operational_error_degrades_gracefully(self):
        mock_model = MagicMock(spec=ModelInferenceService)
        mock_model.predict.side_effect = InferenceServiceError(
            "Model inference timeout"
        )

        service = _build_test_pipeline(model_service=mock_model)
        service.run_pipeline(self.claim.id)

        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.COMPLETED)

        analysis = Analysis.objects.get(claim=self.claim)
        failed = analysis.explainability_json["diagnostics"]["failed_components"]
        self.assertIn("model", failed)

    def test_fact_check_timeout_degrades_gracefully(self):
        mock_fc = MagicMock(spec=FactCheckService)
        mock_fc.query.side_effect = FactCheckTimeoutError(
            "Google API request timed out"
        )

        service = _build_test_pipeline(fact_check_service=mock_fc)
        service.run_pipeline(self.claim.id)

        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.COMPLETED)

        analysis = Analysis.objects.get(claim=self.claim)
        failed = analysis.explainability_json["diagnostics"]["failed_components"]
        self.assertIn("fact_check", failed)

    def test_fact_check_auth_error_degrades_gracefully(self):
        mock_fc = MagicMock(spec=FactCheckService)
        mock_fc.query.side_effect = FactCheckAuthError("API key rejected 403")

        service = _build_test_pipeline(fact_check_service=mock_fc)
        service.run_pipeline(self.claim.id)

        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.COMPLETED)

        analysis = Analysis.objects.get(claim=self.claim)
        failed = analysis.explainability_json["diagnostics"]["failed_components"]
        self.assertIn("fact_check", failed)

    def test_narrative_model_unavailable_degrades_gracefully(self):
        mock_narrative = MagicMock(spec=NarrativeActivityService)
        mock_narrative.evaluate.side_effect = NarrativeModelUnavailableError(
            "Embedding unavailable"
        )

        service = _build_test_pipeline(narrative_service=mock_narrative)
        service.run_pipeline(self.claim.id)

        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.COMPLETED)

        analysis = Analysis.objects.get(claim=self.claim)
        self.assertIsNone(analysis.highest_similarity_score)

    def test_similarity_calculation_error_degrades_gracefully(self):
        mock_similarity = MagicMock(spec=SimilarityScoringService)
        mock_similarity.calculate_from_activity.side_effect = (
            SimilarityCalculationError("NaN score")
        )

        service = _build_test_pipeline(similarity_service=mock_similarity)
        service.run_pipeline(self.claim.id)

        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.COMPLETED)

        analysis = Analysis.objects.get(claim=self.claim)
        self.assertIsNone(analysis.highest_similarity_score)

    def test_rule_engine_error_degrades_gracefully(self):
        mock_rules = MagicMock(spec=RuleEngineService)
        mock_rules.evaluate.side_effect = RuleEngineError("Regex eval timed out")

        service = _build_test_pipeline(rule_service=mock_rules)
        service.run_pipeline(self.claim.id)

        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.COMPLETED)

        analysis = Analysis.objects.get(claim=self.claim)
        failed = analysis.explainability_json["diagnostics"]["failed_components"]
        self.assertIn("rule_engine", failed)

    def test_all_truth_signals_failing_produces_insufficient_evidence_verdict(self):
        mock_model = MagicMock(spec=ModelInferenceService)
        mock_model.predict.side_effect = InferenceServiceError("Model down")

        mock_fc = MagicMock(spec=FactCheckService)
        mock_fc.query.side_effect = FactCheckTimeoutError("Fact check timed out")

        service = _build_test_pipeline(
            model_service=mock_model,
            fact_check_service=mock_fc,
        )
        service.run_pipeline(self.claim.id)

        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.COMPLETED)

        analysis = Analysis.objects.get(claim=self.claim)
        self.assertEqual(analysis.verdict, Verdict.UNCERTAIN.value)
        self.assertIsNone(analysis.credibility_score)


class FatalErrorPipelineTests(TestCase):
    """Verifies that contract or configuration errors mark the claim FAILED without persisting Analysis."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="fatal_user@example.com",
            password="Password123!",
            full_name="Fatal User",
        )
        self.claim = Claim.objects.create(
            user=self.user,
            text="Valid initial claim text destined to trigger fatal failure.",
            status=ClaimStatus.PENDING,
            is_deleted=False,
        )

    def test_claim_preprocessing_error_marks_claim_failed(self):
        with patch("analysis.services.pipeline.preprocess_claim_text") as mock_prep:
            mock_prep.side_effect = ClaimPreprocessingError("Text too short")
            service = _build_test_pipeline()
            service.run_pipeline(self.claim.id)

        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.FAILED)
        self.assertFalse(Analysis.objects.filter(claim=self.claim).exists())

    def test_invalid_model_input_error_marks_claim_failed(self):
        mock_model = MagicMock(spec=ModelInferenceService)
        mock_model.predict.side_effect = InvalidModelInputError(
            "Input validation failed"
        )

        service = _build_test_pipeline(model_service=mock_model)
        service.run_pipeline(self.claim.id)

        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.FAILED)
        self.assertFalse(Analysis.objects.filter(claim=self.claim).exists())

    def test_invalid_model_output_error_marks_claim_failed(self):
        mock_model = MagicMock(spec=ModelInferenceService)
        mock_model.predict.side_effect = InvalidModelOutputError(
            "Malformed adapter output"
        )

        service = _build_test_pipeline(model_service=mock_model)
        service.run_pipeline(self.claim.id)

        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.FAILED)
        self.assertFalse(Analysis.objects.filter(claim=self.claim).exists())

    def test_fact_check_config_error_marks_claim_failed(self):
        mock_fc = MagicMock(spec=FactCheckService)
        mock_fc.query.side_effect = FactCheckConfigError(
            "Invalid API key configuration"
        )

        service = _build_test_pipeline(fact_check_service=mock_fc)
        service.run_pipeline(self.claim.id)

        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.FAILED)
        self.assertFalse(Analysis.objects.filter(claim=self.claim).exists())

    def test_fact_check_input_error_marks_claim_failed(self):
        mock_fc = MagicMock(spec=FactCheckService)
        mock_fc.query.side_effect = FactCheckInputError("Empty query")

        service = _build_test_pipeline(fact_check_service=mock_fc)
        service.run_pipeline(self.claim.id)

        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.FAILED)
        self.assertFalse(Analysis.objects.filter(claim=self.claim).exists())

    def test_narrative_config_error_marks_claim_failed(self):
        mock_narrative = MagicMock(spec=NarrativeActivityService)
        mock_narrative.evaluate.side_effect = NarrativeConfigError(
            "Misconfigured threshold"
        )

        service = _build_test_pipeline(narrative_service=mock_narrative)
        service.run_pipeline(self.claim.id)

        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.FAILED)
        self.assertFalse(Analysis.objects.filter(claim=self.claim).exists())

    def test_rule_config_error_marks_claim_failed(self):
        mock_rules = MagicMock(spec=RuleEngineService)
        mock_rules.evaluate.side_effect = RuleConfigError("Misconfigured penalty")

        service = _build_test_pipeline(rule_service=mock_rules)
        service.run_pipeline(self.claim.id)

        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.FAILED)
        self.assertFalse(Analysis.objects.filter(claim=self.claim).exists())

    def test_similarity_input_error_marks_claim_failed(self):
        mock_similarity = MagicMock(spec=SimilarityScoringService)
        mock_similarity.calculate_from_activity.side_effect = SimilarityInputError(
            "Malformed input"
        )

        service = _build_test_pipeline(similarity_service=mock_similarity)
        service.run_pipeline(self.claim.id)

        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.FAILED)
        self.assertFalse(Analysis.objects.filter(claim=self.claim).exists())

    def test_persistence_input_error_marks_claim_failed(self):
        mock_persistence = MagicMock(spec=AnalysisPersistenceService)
        mock_persistence.persist_analysis.side_effect = AnalysisPersistenceInputError(
            "Claim unsaved"
        )

        service = _build_test_pipeline(persistence_service=mock_persistence)
        service.run_pipeline(self.claim.id)

        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.FAILED)

    def test_unexpected_exception_during_persistence_marks_claim_failed(self):
        mock_persistence = MagicMock(spec=AnalysisPersistenceService)
        mock_persistence.persist_analysis.side_effect = TypeError(
            "Unexpected argument error during persistence"
        )

        service = _build_test_pipeline(persistence_service=mock_persistence)
        service.run_pipeline(self.claim.id)

        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.FAILED)
        self.assertFalse(Analysis.objects.filter(claim=self.claim).exists())


class PostPersistenceSafeguardsTests(TestCase):
    """Verifies that Zone 2 failures never mark the claim FAILED and preserve the Analysis record."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="post_persist_user@example.com",
            password="Password123!",
            full_name="Post Persist User",
        )
        self.claim = Claim.objects.create(
            user=self.user,
            text="Claim for post-persistence safeguard verification.",
            status=ClaimStatus.PENDING,
            is_deleted=False,
        )

    def test_completed_transition_affecting_zero_rows_does_not_mark_failed(self):
        service = _build_test_pipeline()

        original_persist = service.persistence_service.persist_analysis

        def side_effect_persist(*args, **kwargs):
            analysis = original_persist(*args, **kwargs)
            # Simulate admin soft-deleting the claim while pipeline is running
            Claim.objects.filter(id=self.claim.id).update(is_deleted=True)
            return analysis

        with patch.object(
            service.persistence_service,
            "persist_analysis",
            side_effect=side_effect_persist,
        ):
            service.run_pipeline(self.claim.id)

        self.claim.refresh_from_db()
        # Must retain soft-delete and NOT be changed to FAILED
        self.assertTrue(self.claim.is_deleted)
        self.assertNotEqual(self.claim.status, ClaimStatus.FAILED)
        # Analysis record must exist
        self.assertTrue(Analysis.objects.filter(claim=self.claim).exists())

    def test_database_error_during_post_persistence_transition_preserves_analysis(self):
        service = _build_test_pipeline()

        with patch("analysis.services.pipeline.Claim.objects.filter") as mock_filter:
            # Let step 1 succeed:
            mock_filter.return_value.update.side_effect = [
                1,
                DatabaseError("DB connection lost"),
            ]
            service.run_pipeline(self.claim.id)

        # Analysis must have been persisted
        self.assertTrue(Analysis.objects.filter(claim=self.claim).exists())
        self.claim.refresh_from_db()
        self.assertNotEqual(self.claim.status, ClaimStatus.FAILED)


class ReconciliationPipelineTransactionTests(TransactionTestCase):
    """
    Verifies lock-based reconciliation for ambiguous persistence outcomes against
    real PostgreSQL row-lock contention.
    """

    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest(
                "Row-lock contention tests require PostgreSQL database backend."
            )

        self.user = User.objects.create_user(
            email="reconcile_user@example.com",
            password="Password123!",
            full_name="Reconcile User",
        )
        self.claim = Claim.objects.create(
            user=self.user,
            text="Claim testing ambiguous persistence reconciliation.",
            status=ClaimStatus.PENDING,
            is_deleted=False,
        )

    @staticmethod
    def _get_connection_backend_pid(conn) -> int:
        """
        Extracts the PostgreSQL backend PID from a Django database connection.
        Supports psycopg3 (conn.connection.info.backend_pid), psycopg2 (conn.connection.get_backend_pid()),
        and fallback to SELECT pg_backend_pid().
        """
        if conn.connection is None:
            conn.connect()
        raw_conn = getattr(conn, "connection", None)
        if raw_conn is not None:
            if hasattr(raw_conn, "get_backend_pid"):
                return raw_conn.get_backend_pid()
            if hasattr(raw_conn, "info") and hasattr(raw_conn.info, "backend_pid"):
                return raw_conn.info.backend_pid
        with conn.cursor() as cursor:
            cursor.execute("SELECT pg_backend_pid();")
            return cursor.fetchone()[0]

    def _wait_for_blocked_db_lock(self, pid: int, timeout: float = 5.0) -> dict:
        """
        Polls PostgreSQL catalogs (pg_locks and pg_stat_activity) to verify
        that Thread B's backend process (identified by its captured PID) is physically
        blocked on an ungranted lock (granted = false, wait_event_type = 'Lock')
        executing the expected Claim row-lock query (on claims_claim with FOR UPDATE).
        Returns lock details dict once contention is established, or raises TimeoutError.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT a.pid, l.locktype, l.mode, l.granted, a.wait_event_type, a.wait_event, a.query
                    FROM pg_locks l
                    JOIN pg_stat_activity a ON l.pid = a.pid
                    WHERE l.pid = %s
                      AND NOT l.granted
                      AND a.wait_event_type = 'Lock'
                      AND a.query LIKE %s
                      AND a.query LIKE %s
                    """,
                    [pid, "%claims_claim%", "%FOR UPDATE%"],
                )
                row = cursor.fetchone()
                if row is not None:
                    return {
                        "pid": row[0],
                        "locktype": row[1],
                        "mode": row[2],
                        "granted": row[3],
                        "wait_event_type": row[4],
                        "wait_event": row[5],
                        "query": row[6],
                    }
            time.sleep(0.02)
        raise TimeoutError(
            f"Backend PID {pid} was not observed blocked on an ungranted lock executing Claim row-lock query within {timeout}s."
        )

    def test_reconciliation_waits_for_unresolved_commit_and_completes(self):
        """
        Genuine PostgreSQL lock-contention test (Commit):
        1. Thread A opens transaction.atomic().
        2. Thread A acquires Claim row lock via select_for_update().
        3. Thread A signals that lock is held.
        4. Thread B captures its backend PID and publishes it before calling _reconcile_ambiguous_persistence().
        5. Verify Thread B's exact PID is physically blocked in PostgreSQL on ungranted row lock (granted = false).
        6. Thread A creates Analysis record and commits transaction.
        7. Thread B unblocks, acquires lock, observes Analysis, and transitions PROCESSING -> COMPLETED.
        """
        self.claim.status = ClaimStatus.PROCESSING
        self.claim.save()

        service = _build_test_pipeline()

        lock_held_by_a = threading.Event()
        release_a = threading.Event()
        thread_b_pid = []
        thread_b_pid_ready = threading.Event()
        thread_b_finished = threading.Event()
        thread_a_committed = threading.Event()
        errors = []

        def thread_a_worker():
            close_old_connections()
            try:
                with transaction.atomic():
                    locked_claim = Claim.objects.select_for_update().get(
                        pk=self.claim.id
                    )
                    lock_held_by_a.set()
                    if not release_a.wait(timeout=5.0):
                        raise TimeoutError(
                            "Thread A timed out waiting for release signal."
                        )
                    Analysis.objects.create(
                        claim=locked_claim,
                        verdict=Verdict.CREDIBLE.value,
                        credibility_score=85.0,
                        explainability_json={"reasoning": ()},
                    )
                thread_a_committed.set()
            except Exception as exc:
                errors.append(f"Thread A error: {exc}")
            finally:
                close_old_connections()

        def thread_b_worker():
            close_old_connections()
            try:
                with patch("analysis.services.pipeline.close_old_connections"):
                    connection.connect()
                    connection.close_at = None
                    pid = self._get_connection_backend_pid(connection)
                    thread_b_pid.append(pid)
                    thread_b_pid_ready.set()
                    service._reconcile_ambiguous_persistence(self.claim.id)
                    thread_b_finished.set()
            except Exception as exc:
                errors.append(f"Thread B error: {exc}")
            finally:
                close_old_connections()

        t_a = threading.Thread(target=thread_a_worker, name="thread-a-lock-holder")
        t_b = threading.Thread(target=thread_b_worker, name="thread-b-reconciliation")

        try:
            # 1 & 2: Thread A starts and acquires lock
            t_a.start()
            self.assertTrue(
                lock_held_by_a.wait(timeout=5.0),
                "Thread A failed to acquire Claim row lock within timeout.",
            )

            # 4: Thread B starts, captures PID, and initiates reconciliation
            t_b.start()
            self.assertTrue(
                thread_b_pid_ready.wait(timeout=5.0),
                "Thread B failed to capture and publish its PID within timeout.",
            )
            b_pid = thread_b_pid[0]

            # 5: Conclusively prove Thread B is physically blocked on PostgreSQL row lock
            lock_info = self._wait_for_blocked_db_lock(b_pid, timeout=5.0)
            self.assertEqual(lock_info["pid"], b_pid)
            self.assertFalse(lock_info["granted"])
            self.assertIn(lock_info["locktype"], ("tuple", "transactionid"))
            self.assertEqual(lock_info["wait_event_type"], "Lock")
            self.assertIn("claims_claim", lock_info["query"])
            self.assertIn("FOR UPDATE", lock_info["query"])
            self.assertFalse(
                thread_b_finished.is_set(),
                "Thread B unexpectedly completed while Thread A holds row lock.",
            )
            self.assertFalse(
                thread_a_committed.is_set(),
                "Thread A unexpectedly committed before release signal.",
            )

            # 6: Signal Thread A to create Analysis and commit
            release_a.set()
            t_a.join(timeout=5.0)
            self.assertFalse(t_a.is_alive(), "Thread A failed to join.")
            self.assertTrue(thread_a_committed.is_set(), "Thread A failed to commit.")

            # 7: Thread B unblocks, acquires lock, and finishes
            t_b.join(timeout=5.0)
            self.assertFalse(t_b.is_alive(), "Thread B failed to join.")
            self.assertTrue(thread_b_finished.is_set(), "Thread B failed to finish.")

            self.assertEqual(errors, [])

            # Verify outcome: claim transitioned to COMPLETED
            self.claim.refresh_from_db()
            self.assertEqual(self.claim.status, ClaimStatus.COMPLETED)
            self.assertTrue(Analysis.objects.filter(claim=self.claim).exists())
        finally:
            release_a.set()
            if t_a.is_alive():
                t_a.join(timeout=2.0)
            if t_b.is_alive():
                t_b.join(timeout=2.0)
            close_old_connections()

    def test_reconciliation_waits_for_unresolved_rollback_and_fails(self):
        """
        Genuine PostgreSQL lock-contention test (Rollback):
        1. Thread A opens transaction.atomic().
        2. Thread A acquires Claim row lock via select_for_update().
        3. Thread A signals that lock is held.
        4. Thread B captures its backend PID and publishes it before calling _reconcile_ambiguous_persistence().
        5. Verify Thread B's exact PID is physically blocked in PostgreSQL on ungranted row lock (granted = false).
        6. Thread A rolls back transaction without creating Analysis.
        7. Thread B unblocks, acquires lock, observes no Analysis, and transitions PROCESSING -> FAILED.
        """
        self.claim.status = ClaimStatus.PROCESSING
        self.claim.save()

        service = _build_test_pipeline()

        lock_held_by_a = threading.Event()
        release_a = threading.Event()
        thread_b_pid = []
        thread_b_pid_ready = threading.Event()
        thread_b_finished = threading.Event()
        thread_a_rolled_back = threading.Event()
        errors = []

        def thread_a_worker():
            close_old_connections()
            try:
                try:
                    with transaction.atomic():
                        Claim.objects.select_for_update().get(pk=self.claim.id)
                        lock_held_by_a.set()
                        if not release_a.wait(timeout=5.0):
                            raise TimeoutError(
                                "Thread A timed out waiting for release signal."
                            )
                        # Force rollback by raising exception
                        raise RuntimeError(
                            "Intentional rollback to simulate uncommitted persistence."
                        )
                except RuntimeError:
                    thread_a_rolled_back.set()
            except Exception as exc:
                errors.append(f"Thread A error: {exc}")
            finally:
                close_old_connections()

        def thread_b_worker():
            close_old_connections()
            try:
                with patch("analysis.services.pipeline.close_old_connections"):
                    connection.connect()
                    connection.close_at = None
                    pid = self._get_connection_backend_pid(connection)
                    thread_b_pid.append(pid)
                    thread_b_pid_ready.set()
                    service._reconcile_ambiguous_persistence(self.claim.id)
                    thread_b_finished.set()
            except Exception as exc:
                errors.append(f"Thread B error: {exc}")
            finally:
                close_old_connections()

        t_a = threading.Thread(target=thread_a_worker, name="thread-a-rollback-holder")
        t_b = threading.Thread(target=thread_b_worker, name="thread-b-reconciliation")

        try:
            # 1 & 2: Thread A starts and acquires lock
            t_a.start()
            self.assertTrue(
                lock_held_by_a.wait(timeout=5.0),
                "Thread A failed to acquire Claim row lock within timeout.",
            )

            # 4: Thread B starts, captures PID, and initiates reconciliation
            t_b.start()
            self.assertTrue(
                thread_b_pid_ready.wait(timeout=5.0),
                "Thread B failed to capture and publish its PID within timeout.",
            )
            b_pid = thread_b_pid[0]

            # 5: Conclusively prove Thread B is physically blocked on PostgreSQL row lock
            lock_info = self._wait_for_blocked_db_lock(b_pid, timeout=5.0)
            self.assertEqual(lock_info["pid"], b_pid)
            self.assertFalse(lock_info["granted"])
            self.assertIn(lock_info["locktype"], ("tuple", "transactionid"))
            self.assertEqual(lock_info["wait_event_type"], "Lock")
            self.assertIn("claims_claim", lock_info["query"])
            self.assertIn("FOR UPDATE", lock_info["query"])
            self.assertFalse(
                thread_b_finished.is_set(),
                "Thread B unexpectedly completed while Thread A holds row lock.",
            )
            self.assertFalse(
                thread_a_rolled_back.is_set(),
                "Thread A unexpectedly rolled back before release signal.",
            )

            # 6: Signal Thread A to roll back
            release_a.set()
            t_a.join(timeout=5.0)
            self.assertFalse(t_a.is_alive(), "Thread A failed to join.")
            self.assertTrue(
                thread_a_rolled_back.is_set(), "Thread A failed to roll back."
            )

            # 7: Thread B unblocks, acquires lock, and finishes
            t_b.join(timeout=5.0)
            self.assertFalse(t_b.is_alive(), "Thread B failed to join.")
            self.assertTrue(thread_b_finished.is_set(), "Thread B failed to finish.")

            self.assertEqual(errors, [])

            # Verify outcome: claim transitioned to FAILED and no Analysis exists
            self.claim.refresh_from_db()
            self.assertEqual(self.claim.status, ClaimStatus.FAILED)
            self.assertFalse(Analysis.objects.filter(claim=self.claim).exists())
        finally:
            release_a.set()
            if t_a.is_alive():
                t_a.join(timeout=2.0)
            if t_b.is_alive():
                t_b.join(timeout=2.0)
            close_old_connections()

    def test_reconciliation_preserves_soft_deletion(self):
        service = _build_test_pipeline()
        # Set claim to PROCESSING and soft-delete it
        self.claim.status = ClaimStatus.PROCESSING
        self.claim.is_deleted = True
        self.claim.save()

        service._reconcile_ambiguous_persistence(self.claim.id)

        self.claim.refresh_from_db()
        self.assertTrue(self.claim.is_deleted)
        self.assertEqual(self.claim.status, ClaimStatus.PROCESSING)

    def test_reconciliation_database_failure_leaves_claim_in_processing(self):
        service = _build_test_pipeline()
        self.claim.status = ClaimStatus.PROCESSING
        self.claim.save()

        with patch(
            "analysis.services.pipeline.Claim.objects.select_for_update"
        ) as mock_sfu:
            mock_sfu.side_effect = OperationalError("DB is currently unavailable")
            service._reconcile_ambiguous_persistence(self.claim.id)

        self.claim.refresh_from_db()
        # Must remain in PROCESSING to prevent false failure marking
        self.assertEqual(self.claim.status, ClaimStatus.PROCESSING)


class DispatcherCapacityAndAccountingTests(TestCase):
    """Verifies BoundedSemaphore admission control, permit accounting, and clean shutdown."""

    def test_dispatcher_sync_mode_execution(self):
        dispatcher = AnalysisPipelineDispatcher(sync_mode=True)
        claim_id = uuid.uuid4()

        with patch.object(dispatcher, "_execute_task") as mock_exec:
            res = dispatcher.dispatch(claim_id)
            self.assertTrue(res)
            mock_exec.assert_called_once_with(claim_id)

    def test_real_asynchronous_dispatch_does_not_deadlock(self):
        """
        Regression test: Verifies that a real asynchronous dispatch without mocks
        initializes the ThreadPoolExecutor and completes without recursive mutex deadlock,
        waiting for complete worker execution and Future permit restoration.
        """
        dispatcher = AnalysisPipelineDispatcher(
            max_workers=1,
            max_outstanding_tasks=2,
            sync_mode=False,
        )
        task_executed = threading.Event()

        def mock_execute(cid):
            task_executed.set()

        with patch.object(dispatcher, "_execute_task", side_effect=mock_execute):
            claim_id = uuid.uuid4()
            dispatched = dispatcher.dispatch(claim_id)
            self.assertTrue(dispatched)
            # Ensure worker thread runs and completes without deadlocking
            completed = task_executed.wait(timeout=5.0)
            self.assertTrue(
                completed,
                "Asynchronous dispatch deadlocked or worker failed to execute within timeout.",
            )

            # Explicitly wait for the Future completion and semaphore permit restoration
            deadline = time.monotonic() + 5.0
            permit_restored = False
            while time.monotonic() < deadline:
                with dispatcher._lock:
                    if dispatcher._semaphore._value == 2:
                        permit_restored = True
                        break
                time.sleep(0.02)
            self.assertTrue(
                permit_restored,
                "Semaphore permit was not restored following Future completion callback.",
            )

        dispatcher.shutdown(wait=True, cancel_futures=False)

    def test_dispatcher_permit_released_on_executor_submit_failure(self):
        """
        Verifies that if executor.submit() raises an exception during dispatch:
        1. The exception is propagated to the caller.
        2. The acquired semaphore permit is immediately released (no leak).
        3. A subsequent dispatch can successfully acquire the restored permit.
        """
        dispatcher = AnalysisPipelineDispatcher(
            max_workers=1,
            max_outstanding_tasks=1,
            sync_mode=False,
        )
        claim_id_1 = uuid.uuid4()
        claim_id_2 = uuid.uuid4()

        with patch.object(dispatcher, "_get_executor_unlocked") as mock_exec_getter:
            mock_executor = MagicMock()
            mock_executor.submit.side_effect = RuntimeError(
                "Executor submission failure"
            )
            mock_exec_getter.return_value = mock_executor

            # Assert dispatch() propagates the exception from executor.submit()
            with self.assertRaises(RuntimeError) as ctx:
                dispatcher.dispatch(claim_id_1)
            self.assertIn("Executor submission failure", str(ctx.exception))

            # Verify permit was released and is NOT leaked:
            # Reconfigure mock to succeed on subsequent dispatch
            mock_future = Future()
            mock_executor.submit.side_effect = None
            mock_executor.submit.return_value = mock_future

            # Verify subsequent dispatch can acquire the restored permit
            self.assertTrue(dispatcher.dispatch(claim_id_2))

            # And capacity is now saturated (since max_outstanding_tasks=1)
            self.assertFalse(dispatcher.dispatch(uuid.uuid4()))

    def test_dispatcher_get_executor_raises_after_shutdown(self):
        """
        Verifies that _get_executor_unlocked() and _get_executor() reject
        initialization once the dispatcher has shut down.
        """
        dispatcher = AnalysisPipelineDispatcher(max_workers=1, max_outstanding_tasks=5)
        dispatcher.shutdown(wait=False, cancel_futures=True)

        with self.assertRaises(RuntimeError) as ctx:
            dispatcher._get_executor()
        self.assertIn(
            "Cannot initialize executor after dispatcher shutdown",
            str(ctx.exception),
        )

    def test_dispatcher_capacity_saturation_rejects_dispatch(self):
        dispatcher = AnalysisPipelineDispatcher(
            max_workers=1,
            max_outstanding_tasks=2,
            sync_mode=False,
        )

        claim_id_1 = uuid.uuid4()
        claim_id_2 = uuid.uuid4()
        claim_id_3 = uuid.uuid4()

        with patch.object(dispatcher, "_get_executor_unlocked") as mock_exec_getter:
            mock_executor = MagicMock()
            mock_future = Future()
            mock_executor.submit.return_value = mock_future
            mock_exec_getter.return_value = mock_executor

            # First two submissions acquire the two permits
            self.assertTrue(dispatcher.dispatch(claim_id_1))
            self.assertTrue(dispatcher.dispatch(claim_id_2))

            # Third submission is rejected due to capacity saturation
            self.assertFalse(dispatcher.dispatch(claim_id_3))

    def test_dispatcher_permit_released_on_future_done_callback(self):
        dispatcher = AnalysisPipelineDispatcher(
            max_workers=1,
            max_outstanding_tasks=1,
            sync_mode=False,
        )

        with patch.object(dispatcher, "_get_executor_unlocked") as mock_exec_getter:
            mock_executor = MagicMock()
            future = Future()
            mock_executor.submit.return_value = future
            mock_exec_getter.return_value = mock_executor

            # First dispatch acquires the sole permit
            self.assertTrue(dispatcher.dispatch(uuid.uuid4()))
            # Second dispatch rejected
            self.assertFalse(dispatcher.dispatch(uuid.uuid4()))

            # Task completes, resolving future and triggering callbacks
            future.set_result(None)

            # Permit is released; next dispatch succeeds
            self.assertTrue(dispatcher.dispatch(uuid.uuid4()))

    def test_dispatcher_permit_released_on_future_exception(self):
        dispatcher = AnalysisPipelineDispatcher(
            max_workers=1,
            max_outstanding_tasks=1,
            sync_mode=False,
        )

        with patch.object(dispatcher, "_get_executor_unlocked") as mock_exec_getter:
            mock_executor = MagicMock()
            future = Future()
            mock_executor.submit.return_value = future
            mock_exec_getter.return_value = mock_executor

            self.assertTrue(dispatcher.dispatch(uuid.uuid4()))
            self.assertFalse(dispatcher.dispatch(uuid.uuid4()))

            # Task failed with exception
            future.set_exception(RuntimeError("Worker crashed"))

            # Permit is released
            self.assertTrue(dispatcher.dispatch(uuid.uuid4()))

    def test_dispatcher_shutdown_rejects_subsequent_dispatch(self):
        dispatcher = AnalysisPipelineDispatcher(max_workers=1, max_outstanding_tasks=5)
        dispatcher.shutdown(wait=False, cancel_futures=True)

        self.assertFalse(dispatcher.dispatch(uuid.uuid4()))


class SubmitClaimDispatchIntegrationTests(TransactionTestCase):
    """Verifies transaction.on_commit integration from submit_claim service."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="submit_claim_user@example.com",
            password="Password123!",
            full_name="Submit Claim User",
        )

    def test_submit_claim_dispatches_via_on_commit(self):
        mock_dispatcher = MagicMock(spec=AnalysisPipelineDispatcher)
        mock_dispatcher.dispatch.return_value = True

        set_pipeline_dispatcher(mock_dispatcher)
        try:
            payload = ClaimCreateSchema(
                claim_text="New pending claim submitted for background verification."
            )
            claim = submit_claim(self.user, payload)

            self.assertEqual(claim.status, ClaimStatus.PENDING)
            mock_dispatcher.dispatch.assert_called_once_with(claim.id)
        finally:
            set_pipeline_dispatcher(None)

    def test_submit_claim_marks_failed_when_dispatcher_rejects(self):
        mock_dispatcher = MagicMock(spec=AnalysisPipelineDispatcher)
        mock_dispatcher.dispatch.return_value = (
            False  # Capacity saturated or shutting down
        )

        set_pipeline_dispatcher(mock_dispatcher)
        try:
            payload = ClaimCreateSchema(
                claim_text="Claim rejected by dispatcher due to saturation."
            )
            claim = submit_claim(self.user, payload)

            # In-memory claim returned from submit_claim remains PENDING
            self.assertEqual(claim.status, ClaimStatus.PENDING)

            # Claim row in database transitioned to FAILED via on_commit rejection handler
            claim_in_db = Claim.objects.get(id=claim.id)
            self.assertEqual(claim_in_db.status, ClaimStatus.FAILED)
        finally:
            set_pipeline_dispatcher(None)


class ConcurrencyCASInvariantsTests(TransactionTestCase):
    """Verifies that atomic compare-and-set guards prevent race conditions."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="cas_user@example.com",
            password="Password123!",
            full_name="CAS User",
        )
        self.claim = Claim.objects.create(
            user=self.user,
            text="Claim testing concurrent CAS worker admission.",
            status=ClaimStatus.PENDING,
            is_deleted=False,
        )

    def test_concurrent_workers_only_one_acquires_processing(self):
        service = _build_test_pipeline()

        results = []

        def worker():
            service.run_pipeline(self.claim.id)
            results.append(True)

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(len(results), 2)
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.COMPLETED)
        # Exactly one Analysis record should exist
        self.assertEqual(Analysis.objects.filter(claim=self.claim).count(), 1)


class EndToEndPipelineIntegrationTests(TestCase):
    """
    End-to-End Pipeline Test Suite (AI-019).
    Verifies the complete claim analysis lifecycle across all 11 workflow stages:
    HTTP submission -> preprocessing -> inference -> fact-check -> narrative -> rules
    -> hybrid aggregation -> verdict -> explainability -> persistence -> HTTP retrieval.
    """

    def setUp(self):
        cache.clear()
        self.client = Client()

        # Users
        self.user = User.objects.create_user(
            email="e2e_user@example.com",
            password="Password123!",
            full_name="E2E Regular User",
            role="USER",
        )
        self.other_user = User.objects.create_user(
            email="e2e_other@example.com",
            password="Password123!",
            full_name="E2E Other User",
            role="USER",
        )
        self.admin = User.objects.create_user(
            email="e2e_admin@example.com",
            password="Password123!",
            full_name="E2E Admin",
            role="ADMIN",
        )

        # JWT auth headers via real /api/v1/auth/login endpoint
        resp_user = self.client.post(
            "/api/v1/auth/login",
            data=json.dumps(
                {"email": "e2e_user@example.com", "password": "Password123!"}
            ),
            content_type="application/json",
        )
        self.token = resp_user.json()["data"]["access_token"]
        self.headers = {"HTTP_AUTHORIZATION": f"Bearer {self.token}"}

        resp_other = self.client.post(
            "/api/v1/auth/login",
            data=json.dumps(
                {"email": "e2e_other@example.com", "password": "Password123!"}
            ),
            content_type="application/json",
        )
        self.other_token = resp_other.json()["data"]["access_token"]
        self.other_headers = {"HTTP_AUTHORIZATION": f"Bearer {self.other_token}"}

        resp_admin = self.client.post(
            "/api/v1/auth/login",
            data=json.dumps(
                {"email": "e2e_admin@example.com", "password": "Password123!"}
            ),
            content_type="application/json",
        )
        self.admin_token = resp_admin.json()["data"]["access_token"]
        self.admin_headers = {"HTTP_AUTHORIZATION": f"Bearer {self.admin_token}"}

        # Dispatcher in sync mode for deterministic inline execution
        self.sync_dispatcher = AnalysisPipelineDispatcher(sync_mode=True)
        set_pipeline_dispatcher(self.sync_dispatcher)

        # Default components for pipeline builder
        self.mock_adapter = MockModelAdapter(
            default_prediction=ModelPrediction.CREDIBLE,
            default_confidence=0.80,
        )
        self.model_service = ModelInferenceService(adapter=self.mock_adapter)

        self.fact_check_item = FactCheckEvidenceItem(
            publisher="PolitiFact",
            rating="Mostly True",
            url="https://politifact.com/factchecks/123",
        )
        self.fact_check_result = FactCheckResult(
            matches=1,
            sources=(self.fact_check_item,),
            summary="PolitiFact rated this Mostly True.",
            evidence_urls=(self.fact_check_item.url,),
        )
        self.mock_fact_check_service = MagicMock(spec=FactCheckService)
        self.mock_fact_check_service.query.return_value = self.fact_check_result

        self.mock_embedder = MockEmbeddingGenerator()
        self.narrative_service = NarrativeActivityService(embedder=self.mock_embedder)
        self.rule_service = None

        # Patch AnalysisPipelineService in pipeline.py so dispatcher instantiates our configured pipeline
        self.pipeline_patcher = patch(
            "analysis.services.pipeline.AnalysisPipelineService",
            side_effect=self._build_pipeline,
        )
        self.pipeline_patcher.start()

    def tearDown(self):
        self.pipeline_patcher.stop()
        set_pipeline_dispatcher(None)
        cache.clear()

    def _build_pipeline(self):
        return _build_test_pipeline(
            model_service=self.model_service,
            fact_check_service=self.mock_fact_check_service,
            narrative_service=self.narrative_service,
            rule_service=self.rule_service,
        )

    def test_e2e_nominal_submission_to_analysis_retrieval(self):
        claim_text = "The international scientific consortium confirmed solar flares do not cause earthquakes."

        with self.captureOnCommitCallbacks(execute=True):
            resp_post = self.client.post(
                "/api/v1/claims",
                data=json.dumps({"claim_text": claim_text}),
                content_type="application/json",
                **self.headers,
            )

        self.assertEqual(resp_post.status_code, 201)
        post_data = resp_post.json()
        self.assertTrue(post_data["success"])
        self.assertEqual(post_data["message"], "Claim submitted successfully.")
        claim_id = post_data["data"]["id"]

        # 1. Database State Verification
        claim = Claim.objects.get(id=claim_id)
        self.assertEqual(claim.status, ClaimStatus.COMPLETED)
        self.assertFalse(claim.is_deleted)

        analysis = Analysis.objects.get(claim=claim)
        self.assertEqual(analysis.verdict, Verdict.CREDIBLE.value)
        self.assertEqual(analysis.credibility_score, 82.4)
        self.assertEqual(analysis.fact_check_match_count, 1)
        self.assertEqual(analysis.narrative_match_count, 0)

        # 2. Status API Retrieval (GET /api/v1/analysis/{claim_id}/status)
        resp_status = self.client.get(
            f"/api/v1/analysis/{claim_id}/status", **self.headers
        )
        self.assertEqual(resp_status.status_code, 200)
        status_data = resp_status.json()["data"]
        self.assertEqual(status_data["claim_id"], claim_id)
        self.assertEqual(status_data["status"], "COMPLETED")
        self.assertIsNone(status_data["error_code"])
        self.assertIsNone(status_data["error_message"])
        self.assertIsNone(status_data["retryable"])

        # 3. Core Summary API Retrieval (GET /api/v1/analysis/{claim_id})
        resp_summary = self.client.get(f"/api/v1/analysis/{claim_id}", **self.headers)
        self.assertEqual(resp_summary.status_code, 200)
        summary_data = resp_summary.json()["data"]
        self.assertEqual(summary_data["claim_id"], claim_id)
        self.assertEqual(summary_data["analysis_status"], "COMPLETED")
        self.assertEqual(summary_data["verdict"], "CREDIBLE")
        self.assertEqual(summary_data["credibility_score"], 82.4)
        self.assertIsNotNone(summary_data["created_at"])

        # 4. Explainability API Retrieval (GET /api/v1/analysis/{claim_id}/explanation)
        resp_exp = self.client.get(
            f"/api/v1/analysis/{claim_id}/explanation", **self.headers
        )
        self.assertEqual(resp_exp.status_code, 200)
        exp_data = resp_exp.json()["data"]
        self.assertEqual(exp_data["verdict"], "CREDIBLE")
        self.assertEqual(exp_data["credibility_score"], 82.4)
        self.assertAlmostEqual(
            exp_data["score_breakdown"]["classification_model"], 32.9, places=1
        )
        self.assertAlmostEqual(
            exp_data["score_breakdown"]["fact_check"], 37.6, places=1
        )
        self.assertAlmostEqual(
            exp_data["score_breakdown"]["rule_engine"], 11.8, places=1
        )
        self.assertEqual(exp_data["score_breakdown"]["narrative"], 0.0)
        self.assertIsInstance(exp_data["reasoning"], list)
        self.assertGreater(len(exp_data["reasoning"]), 0)

        # 5. Fact-Check API Retrieval (GET /api/v1/analysis/{claim_id}/fact-check)
        resp_fc = self.client.get(
            f"/api/v1/analysis/{claim_id}/fact-check", **self.headers
        )
        self.assertEqual(resp_fc.status_code, 200)
        fc_data = resp_fc.json()["data"]
        self.assertEqual(fc_data["matches_found"], 1)
        self.assertEqual(len(fc_data["sources"]), 1)
        self.assertEqual(fc_data["sources"][0]["publisher"], "PolitiFact")
        self.assertEqual(fc_data["sources"][0]["rating"], "Mostly True")
        self.assertEqual(
            fc_data["sources"][0]["url"], "https://politifact.com/factchecks/123"
        )

        # 6. Narrative Activity API Retrieval (GET /api/v1/analysis/{claim_id}/narrative)
        resp_narrative = self.client.get(
            f"/api/v1/analysis/{claim_id}/narrative", **self.headers
        )
        self.assertEqual(resp_narrative.status_code, 200)
        narrative_data = resp_narrative.json()["data"]
        self.assertEqual(narrative_data["similar_claims"], 0)
        self.assertEqual(narrative_data["highest_similarity"], 0.0)
        self.assertEqual(narrative_data["activity_level"], "LOW")

    def test_e2e_status_polling_and_conflict_prior_to_completion(self):
        claim_text = "The international scientific consortium confirmed solar flares do not cause earthquakes."

        # Submit claim WITHOUT capturing on_commit -> claim is committed as PENDING in DB
        resp_post = self.client.post(
            "/api/v1/claims",
            data=json.dumps({"claim_text": claim_text}),
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(resp_post.status_code, 201)
        claim_id = resp_post.json()["data"]["id"]

        # Verify claim in DB is PENDING
        claim = Claim.objects.get(id=claim_id)
        self.assertEqual(claim.status, ClaimStatus.PENDING)

        # 1. Status endpoint returns 200 with status PENDING
        resp_status = self.client.get(
            f"/api/v1/analysis/{claim_id}/status", **self.headers
        )
        self.assertEqual(resp_status.status_code, 200)
        self.assertEqual(resp_status.json()["data"]["status"], "PENDING")

        # 2. Incompleted analysis endpoints must return 409 Conflict
        resp_summary = self.client.get(f"/api/v1/analysis/{claim_id}", **self.headers)
        self.assertEqual(resp_summary.status_code, 409)

        resp_exp = self.client.get(
            f"/api/v1/analysis/{claim_id}/explanation", **self.headers
        )
        self.assertEqual(resp_exp.status_code, 409)

        resp_fc = self.client.get(
            f"/api/v1/analysis/{claim_id}/fact-check", **self.headers
        )
        self.assertEqual(resp_fc.status_code, 409)

        resp_narrative = self.client.get(
            f"/api/v1/analysis/{claim_id}/narrative", **self.headers
        )
        self.assertEqual(resp_narrative.status_code, 409)

        # 3. Now trigger dispatcher explicitly to complete the analysis
        dispatched = self.sync_dispatcher.dispatch(uuid.UUID(claim_id))
        self.assertTrue(dispatched)

        claim.refresh_from_db()
        self.assertEqual(claim.status, ClaimStatus.COMPLETED)

        # 4. Now summary retrieval returns 200 OK
        resp_completed = self.client.get(f"/api/v1/analysis/{claim_id}", **self.headers)
        self.assertEqual(resp_completed.status_code, 200)
        self.assertEqual(resp_completed.json()["data"]["analysis_status"], "COMPLETED")

    def test_e2e_preprocessing_rejection_lifecycle(self):
        # 10 raw chars passes ClaimCreateSchema (min_length=10), but collapses to 9 chars in cleaner
        raw_text = "123456789\u200B"

        with self.captureOnCommitCallbacks(execute=True):
            resp_post = self.client.post(
                "/api/v1/claims",
                data=json.dumps({"claim_text": raw_text}),
                content_type="application/json",
                **self.headers,
            )
        self.assertEqual(resp_post.status_code, 201)
        claim_id = resp_post.json()["data"]["id"]

        # Database assertions: claim marked FAILED, no Analysis created
        claim = Claim.objects.get(id=claim_id)
        self.assertEqual(claim.status, ClaimStatus.FAILED)
        self.assertFalse(Analysis.objects.filter(claim=claim).exists())

        # Failure diagnostic created
        diagnostic = claim.failure_diagnostic
        self.assertEqual(diagnostic.error_code, "PREPROCESSING_REJECTED")
        self.assertEqual(diagnostic.failure_stage, "PREPROCESSING")
        self.assertFalse(diagnostic.retryable)

        # Status API returns FAILED with diagnostics
        resp_status = self.client.get(
            f"/api/v1/analysis/{claim_id}/status", **self.headers
        )
        self.assertEqual(resp_status.status_code, 200)
        status_data = resp_status.json()["data"]
        self.assertEqual(status_data["status"], "FAILED")
        self.assertEqual(status_data["error_code"], "PREPROCESSING_REJECTED")
        self.assertFalse(status_data["retryable"])

        # Summary API returns 409 Conflict
        resp_summary = self.client.get(f"/api/v1/analysis/{claim_id}", **self.headers)
        self.assertEqual(resp_summary.status_code, 409)

    def test_e2e_fact_check_failure_graceful_degradation(self):
        # Simulate fact check provider timeout
        self.mock_fact_check_service.query.side_effect = FactCheckTimeoutError(
            "Google Fact Check API connection timed out"
        )
        claim_text = "Daily physical activity and balanced diet reduce risk of cardiovascular illness."

        with self.captureOnCommitCallbacks(execute=True):
            resp_post = self.client.post(
                "/api/v1/claims",
                data=json.dumps({"claim_text": claim_text}),
                content_type="application/json",
                **self.headers,
            )
        self.assertEqual(resp_post.status_code, 201)
        claim_id = resp_post.json()["data"]["id"]

        # Database assertions: claim completed with degraded score 84.4
        claim = Claim.objects.get(id=claim_id)
        self.assertEqual(claim.status, ClaimStatus.COMPLETED)

        analysis = Analysis.objects.get(claim=claim)
        self.assertEqual(analysis.verdict, Verdict.CREDIBLE.value)
        self.assertEqual(analysis.credibility_score, 84.4)
        self.assertIsNone(analysis.fact_check_match_count)

        # Summary API returns 200 OK with valid degraded score
        resp_summary = self.client.get(f"/api/v1/analysis/{claim_id}", **self.headers)
        self.assertEqual(resp_summary.status_code, 200)
        summary_data = resp_summary.json()["data"]
        self.assertEqual(summary_data["analysis_status"], "COMPLETED")
        self.assertEqual(summary_data["verdict"], "CREDIBLE")
        self.assertEqual(summary_data["credibility_score"], 84.4)

        # Fact-check endpoint returns 200 with empty sources
        resp_fc = self.client.get(
            f"/api/v1/analysis/{claim_id}/fact-check", **self.headers
        )
        self.assertEqual(resp_fc.status_code, 200)
        fc_data = resp_fc.json()["data"]
        self.assertIsNone(fc_data["matches_found"])
        self.assertEqual(fc_data["sources"], [])

    def test_e2e_insufficient_evidence_null_score(self):
        # Both model inference and fact checking fail
        mock_model = MagicMock(spec=ModelInferenceService)
        mock_model.predict.side_effect = InferenceServiceError(
            "Model inference failed: GPU crash"
        )
        mock_model.get_provenance_snapshot.return_value = (None, None)
        mock_model.model_version = None
        mock_model.artifact_fingerprint = None
        self.model_service = mock_model

        self.mock_fact_check_service.query.side_effect = FactCheckServiceError(
            "Fact check provider network down"
        )
        claim_text = "Daily physical activity and balanced diet reduce risk of cardiovascular illness."

        with self.captureOnCommitCallbacks(execute=True):
            resp_post = self.client.post(
                "/api/v1/claims",
                data=json.dumps({"claim_text": claim_text}),
                content_type="application/json",
                **self.headers,
            )
        self.assertEqual(resp_post.status_code, 201)
        claim_id = resp_post.json()["data"]["id"]

        # Database assertions: claim completed with NULL credibility score and UNCERTAIN verdict
        claim = Claim.objects.get(id=claim_id)
        self.assertEqual(claim.status, ClaimStatus.COMPLETED)

        analysis = Analysis.objects.get(claim=claim)
        self.assertIsNone(analysis.credibility_score)
        self.assertEqual(analysis.verdict, Verdict.UNCERTAIN.value)

        # API assertions: verdict UNCERTAIN, credibility_score is None
        resp_summary = self.client.get(f"/api/v1/analysis/{claim_id}", **self.headers)
        self.assertEqual(resp_summary.status_code, 200)
        summary_data = resp_summary.json()["data"]
        self.assertEqual(summary_data["analysis_status"], "COMPLETED")
        self.assertEqual(summary_data["verdict"], "UNCERTAIN")
        self.assertIsNone(summary_data["credibility_score"])

        # Explanation endpoint
        resp_exp = self.client.get(
            f"/api/v1/analysis/{claim_id}/explanation", **self.headers
        )
        self.assertEqual(resp_exp.status_code, 200)
        exp_data = resp_exp.json()["data"]
        self.assertEqual(exp_data["verdict"], "UNCERTAIN")
        self.assertIsNone(exp_data["credibility_score"])
        self.assertEqual(exp_data["score_breakdown"]["classification_model"], 0.0)
        self.assertEqual(exp_data["score_breakdown"]["fact_check"], 0.0)

    def test_e2e_narrative_activity_history_detection(self):
        text_1 = (
            "Electric vehicles reduce lifetime greenhouse gas emissions substantially."
        )
        text_2 = (
            "Electric cars reduce lifecycle greenhouse gas emissions significantly."
        )

        vec_1 = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        vec_2 = np.array([0.88, math.sqrt(1 - 0.88**2), 0.0], dtype=np.float32)

        embed_mapping = {
            text_1: vec_1,
            text_2: vec_2,
        }
        self.mock_embedder = MockEmbeddingGenerator(mapping=embed_mapping, dim=3)
        self.narrative_service = NarrativeActivityService(embedder=self.mock_embedder)

        # 1. Submit Claim 1 and run pipeline to completion
        with self.captureOnCommitCallbacks(execute=True):
            resp_1 = self.client.post(
                "/api/v1/claims",
                data=json.dumps({"claim_text": text_1}),
                content_type="application/json",
                **self.headers,
            )
        self.assertEqual(resp_1.status_code, 201)
        claim_1_id = resp_1.json()["data"]["id"]
        c1 = Claim.objects.get(id=claim_1_id)
        self.assertEqual(c1.status, ClaimStatus.COMPLETED)

        # 2. Submit Claim 2 and run pipeline to completion
        with self.captureOnCommitCallbacks(execute=True):
            resp_2 = self.client.post(
                "/api/v1/claims",
                data=json.dumps({"claim_text": text_2}),
                content_type="application/json",
                **self.headers,
            )
        self.assertEqual(resp_2.status_code, 201)
        claim_2_id = resp_2.json()["data"]["id"]
        c2 = Claim.objects.get(id=claim_2_id)
        self.assertEqual(c2.status, ClaimStatus.COMPLETED)

        # Database check on Claim 2: found Claim 1 with 0.88 similarity
        analysis_2 = Analysis.objects.get(claim=c2)
        self.assertEqual(analysis_2.narrative_match_count, 1)
        self.assertAlmostEqual(analysis_2.highest_similarity_score, 0.88, places=4)

        # Narrative API check on Claim 2
        resp_narrative = self.client.get(
            f"/api/v1/analysis/{claim_2_id}/narrative", **self.headers
        )
        self.assertEqual(resp_narrative.status_code, 200)
        narrative_data = resp_narrative.json()["data"]
        self.assertEqual(narrative_data["similar_claims"], 1)
        self.assertEqual(narrative_data["highest_similarity"], 88.0)
        self.assertEqual(narrative_data["activity_level"], "LOW")
        self.assertIsNotNone(narrative_data["first_seen"])
        self.assertIsNotNone(narrative_data["latest_occurrence"])

    def test_e2e_authorization_and_ownership_boundaries(self):
        claim_text = "The international scientific consortium confirmed solar flares do not cause earthquakes."

        with self.captureOnCommitCallbacks(execute=True):
            resp_post = self.client.post(
                "/api/v1/claims",
                data=json.dumps({"claim_text": claim_text}),
                content_type="application/json",
                **self.headers,
            )
        self.assertEqual(resp_post.status_code, 201)
        claim_id = resp_post.json()["data"]["id"]

        # 1. Owner can access completed analysis -> 200 OK
        resp_owner = self.client.get(f"/api/v1/analysis/{claim_id}", **self.headers)
        self.assertEqual(resp_owner.status_code, 200)
        self.assertEqual(resp_owner.json()["data"]["analysis_status"], "COMPLETED")

        # 2. Other authenticated regular user receives 403 Forbidden
        resp_other = self.client.get(
            f"/api/v1/analysis/{claim_id}", **self.other_headers
        )
        self.assertEqual(resp_other.status_code, 403)
        self.assertFalse(resp_other.json()["success"])
        self.assertEqual(resp_other.json()["error_code"], "PERMISSION_DENIED")
        self.assertEqual(resp_other.json()["message"], "Forbidden")

        # 3. Admin user has cross-user access -> 200 OK
        resp_admin = self.client.get(
            f"/api/v1/analysis/{claim_id}", **self.admin_headers
        )
        self.assertEqual(resp_admin.status_code, 200)
        self.assertEqual(resp_admin.json()["data"]["analysis_status"], "COMPLETED")

        # 4. Unauthenticated request receives 401 Unauthorized
        resp_anon = self.client.get(f"/api/v1/analysis/{claim_id}")
        self.assertEqual(resp_anon.status_code, 401)

    def test_e2e_soft_deletion_during_pipeline_processing(self):
        claim_text = "The international scientific consortium confirmed solar flares do not cause earthquakes."

        real_rule_engine = RuleEngineService()

        def hooked_evaluate(text):
            # Mid-pipeline hook: claim is in PROCESSING state
            in_flight = Claim.objects.get(
                status=ClaimStatus.PROCESSING, is_deleted=False
            )
            # Admin user soft-deletes the claim
            del_resp = self.client.delete(
                f"/api/v1/claims/{in_flight.id}", **self.admin_headers
            )
            self.assertEqual(del_resp.status_code, 204)
            in_flight.refresh_from_db()
            self.assertTrue(in_flight.is_deleted)
            return real_rule_engine.evaluate(text)

        mock_rule_service = MagicMock(spec=RuleEngineService)
        mock_rule_service.evaluate.side_effect = hooked_evaluate
        self.rule_service = mock_rule_service

        with self.captureOnCommitCallbacks(execute=True):
            resp_post = self.client.post(
                "/api/v1/claims",
                data=json.dumps({"claim_text": claim_text}),
                content_type="application/json",
                **self.headers,
            )
        self.assertEqual(resp_post.status_code, 201)
        claim_id = resp_post.json()["data"]["id"]

        # Database assertions: claim is soft-deleted and remains in PROCESSING (not transitioned to COMPLETED)
        claim = Claim.objects.get(id=claim_id)
        self.assertTrue(claim.is_deleted)
        self.assertEqual(claim.status, ClaimStatus.PROCESSING)
        self.assertFalse(Analysis.objects.filter(claim=claim).exists())

        # API Assertions: All endpoints return 404 Not Found for soft-deleted claims
        resp_summary = self.client.get(f"/api/v1/analysis/{claim_id}", **self.headers)
        self.assertEqual(resp_summary.status_code, 404)

        resp_status = self.client.get(
            f"/api/v1/analysis/{claim_id}/status", **self.headers
        )
        self.assertEqual(resp_status.status_code, 404)

        resp_claim = self.client.get(f"/api/v1/claims/{claim_id}", **self.headers)
        self.assertEqual(resp_claim.status_code, 404)

        # Even admin receives 404 on deleted analysis
        resp_admin = self.client.get(
            f"/api/v1/analysis/{claim_id}", **self.admin_headers
        )
        self.assertEqual(resp_admin.status_code, 404)

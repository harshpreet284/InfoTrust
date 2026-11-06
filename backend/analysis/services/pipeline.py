"""
Core analysis pipeline orchestration service for InfoTrust (AI-014).
Coordinates preprocessing, evidence gathering across ML model, Google Fact Check,
narrative activity, similarity scoring, and rule engine, synthesizes hybrid credibility,
verdict, and explainability results, and persists analysis with strict pre/post persistence
failure boundaries and lock-based ambiguous outcome reconciliation.
"""

import logging
import uuid
from typing import Optional

from django.db import DatabaseError, close_old_connections, connection, transaction
from django.utils import timezone

from analysis.models import Analysis, AnalysisFailureDiagnostic
from analysis.preprocessing import ClaimPreprocessingError, preprocess_claim_text
from analysis.services.explainability import (
    ExplainabilityEngineError,
    ExplainabilityInputError,
    ExplainabilityService,
)
from analysis.services.fact_check import (
    FactCheckConfigError,
    FactCheckInputError,
    FactCheckService,
    FactCheckServiceError,
)
from analysis.services.hybrid import (
    HybridConfigError,
    HybridCredibilityEngine,
    HybridEngineError,
    HybridInputError,
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
    NarrativeInputError,
    NarrativeServiceError,
)
from analysis.services.persistence import (
    AnalysisAlreadyExistsError,
    AnalysisPersistenceError,
    AnalysisPersistenceInputError,
    AnalysisPersistenceService,
)
from analysis.services.rules import (
    RuleConfigError,
    RuleEngineError,
    RuleEngineService,
    RuleInputError,
)
from analysis.services.similarity import (
    SimilarityCalculationError,
    SimilarityInputError,
    SimilarityScoringService,
    SimilarityServiceError,
)
from analysis.services.verdict import (
    VerdictConfigError,
    VerdictEngineError,
    VerdictInputError,
    VerdictService,
)
from claims.models import Claim, ClaimStatus

logger = logging.getLogger(__name__)

VALID_FAILURE_STAGES = frozenset({"PREPROCESSING", "SYNTHESIS", "PERSISTENCE"})
DEFAULT_FALLBACK_STAGE = "SYNTHESIS"
DEFAULT_FALLBACK_ERROR_CODE = "ANALYSIS_FAILED"

PUBLIC_ERROR_MAPPINGS = {
    "PREPROCESSING_REJECTED": {
        "error_code": "PREPROCESSING_REJECTED",
        "error_message": "Claim text could not be processed due to invalid or unparsable content.",
        "retryable": False,
    },
    "INVALID_INPUT_CONTRACT": {
        "error_code": "INVALID_INPUT_CONTRACT",
        "error_message": "Claim input violates system processing requirements.",
        "retryable": False,
    },
    "SERVICE_UNAVAILABLE": {
        "error_code": "SERVICE_UNAVAILABLE",
        "error_message": "Analysis service is temporarily unavailable. Please retry later.",
        "retryable": True,
    },
    "ANALYSIS_FAILED": {
        "error_code": "ANALYSIS_FAILED",
        "error_message": "An unexpected error occurred during claim analysis.",
        "retryable": False,
    },
}


class AnalysisPipelineService:
    """
    Orchestrates the claim analysis pipeline end-to-end.
    Enforces atomic lifecycle transitions: PENDING -> PROCESSING -> COMPLETED (or FAILED).
    """

    def __init__(
        self,
        model_service: Optional[ModelInferenceService] = None,
        fact_check_service: Optional[FactCheckService] = None,
        narrative_service: Optional[NarrativeActivityService] = None,
        similarity_service: Optional[SimilarityScoringService] = None,
        rule_service: Optional[RuleEngineService] = None,
        hybrid_engine: Optional[HybridCredibilityEngine] = None,
        verdict_service: Optional[VerdictService] = None,
        explainability_service: Optional[ExplainabilityService] = None,
        persistence_service: Optional[AnalysisPersistenceService] = None,
    ) -> None:
        self.model_service = model_service or ModelInferenceService()
        self.fact_check_service = fact_check_service or FactCheckService()
        self.narrative_service = narrative_service or NarrativeActivityService()
        self.similarity_service = similarity_service or SimilarityScoringService()
        self.rule_service = rule_service or RuleEngineService()
        self.hybrid_engine = hybrid_engine or HybridCredibilityEngine()
        self.verdict_service = verdict_service or VerdictService()
        self.explainability_service = explainability_service or ExplainabilityService()
        self.persistence_service = persistence_service or AnalysisPersistenceService()

    def run_pipeline(self, claim_id: uuid.UUID) -> None:
        """
        Executes the analysis pipeline for the given claim ID.

        Lifecycle Progression:
        1. Atomically transitions PENDING -> PROCESSING via conditional compare-and-set (CAS).
           If 0 rows are updated, execution aborts cleanly.
        2. Retrieves active Claim record.
        3. Sanitizes and validates claim text via preprocess_claim_text.
        4. Gathers signals across inference, fact-check, narrative, similarity, and rule engine.
           Operational component failures are routed into HybridCredibilityEngine.
        5. Computes hybrid credibility, verdict, and explainability results.
        6. Persists Analysis via AnalysisPersistenceService within Zone 1 failure boundary.
        7. On ambiguous persistence exception, performs lock-based reconciliation.
        8. On persistence success, enters Zone 2 and marks claim COMPLETED.
        """
        if not isinstance(claim_id, uuid.UUID):
            try:
                claim_id = uuid.UUID(str(claim_id))
            except (ValueError, AttributeError, TypeError):
                logger.error(
                    "Invalid claim_id format provided to run_pipeline: %s", claim_id
                )
                return

        # Step 1: Transition PENDING -> PROCESSING via atomic CAS
        updated = Claim.objects.filter(
            id=claim_id,
            status=ClaimStatus.PENDING,
            is_deleted=False,
        ).update(
            status=ClaimStatus.PROCESSING,
            updated_at=timezone.now(),
        )
        if updated == 0:
            logger.info(
                "Claim %s is not in active PENDING state; skipping pipeline execution.",
                claim_id,
            )
            return

        # Step 2: Fetch active Claim record
        try:
            claim = Claim.objects.get(id=claim_id, is_deleted=False)
        except Claim.DoesNotExist:
            logger.warning(
                "Claim %s not found or soft-deleted immediately after PROCESSING transition.",
                claim_id,
            )
            return

        # Step 3: Text Preprocessing (Pre-persistence Zone 1)
        try:
            cleaned_text = preprocess_claim_text(claim.text)
        except ClaimPreprocessingError as exc:
            logger.warning("Claim %s failed text preprocessing: %s", claim_id, exc)
            self._mark_claim_failed(
                claim_id,
                failure_stage="PREPROCESSING",
                error_code="PREPROCESSING_REJECTED",
            )
            return
        except Exception as exc:
            logger.exception(
                "Unexpected error preprocessing claim %s: %s", claim_id, exc
            )
            self._mark_claim_failed(
                claim_id,
                failure_stage="PREPROCESSING",
                error_code="PREPROCESSING_REJECTED",
            )
            return

        # Step 4: Component Evidence Gathering (Zone 1)
        # 4a. Model Inference
        model_output = None
        model_error = None
        try:
            model_output = self.model_service.predict(cleaned_text)
        except (InvalidModelInputError, InvalidModelOutputError, TypeError) as exc:
            logger.exception(
                "Fatal model inference error for claim %s: %s", claim_id, exc
            )
            self._mark_claim_failed(
                claim_id,
                failure_stage="SYNTHESIS",
                error_code="INVALID_INPUT_CONTRACT",
            )
            return
        except InferenceServiceError as exc:
            logger.warning(
                "Operational model inference failure for claim %s: %s", claim_id, exc
            )
            model_error = exc
        except Exception as exc:
            logger.exception(
                "Unexpected fatal error during model inference for claim %s: %s",
                claim_id,
                exc,
            )
            self._mark_claim_failed(
                claim_id,
                failure_stage="SYNTHESIS",
                error_code="ANALYSIS_FAILED",
            )
            return

        # 4b. Google Fact Check
        fact_check_result = None
        fact_check_error = None
        try:
            fact_check_result = self.fact_check_service.query(cleaned_text)
        except (FactCheckConfigError, FactCheckInputError, TypeError) as exc:
            logger.exception("Fatal fact check error for claim %s: %s", claim_id, exc)
            self._mark_claim_failed(
                claim_id,
                failure_stage="SYNTHESIS",
                error_code="INVALID_INPUT_CONTRACT",
            )
            return
        except FactCheckServiceError as exc:
            logger.warning(
                "Operational fact check failure for claim %s: %s", claim_id, exc
            )
            fact_check_error = exc
        except Exception as exc:
            logger.exception(
                "Unexpected fatal error during fact check for claim %s: %s",
                claim_id,
                exc,
            )
            self._mark_claim_failed(
                claim_id,
                failure_stage="SYNTHESIS",
                error_code="ANALYSIS_FAILED",
            )
            return

        # 4c. Narrative Activity
        narrative_activity = None
        narrative_error = None
        try:
            narrative_activity = self.narrative_service.evaluate(
                cleaned_text, current_claim_id=claim.id
            )
        except (NarrativeConfigError, NarrativeInputError, TypeError) as exc:
            logger.exception(
                "Fatal narrative activity error for claim %s: %s", claim_id, exc
            )
            self._mark_claim_failed(
                claim_id,
                failure_stage="SYNTHESIS",
                error_code="INVALID_INPUT_CONTRACT",
            )
            return
        except NarrativeServiceError as exc:
            logger.warning(
                "Operational narrative activity failure for claim %s: %s", claim_id, exc
            )
            narrative_error = exc
        except Exception as exc:
            logger.exception(
                "Unexpected fatal error during narrative activity for claim %s: %s",
                claim_id,
                exc,
            )
            self._mark_claim_failed(
                claim_id,
                failure_stage="SYNTHESIS",
                error_code="ANALYSIS_FAILED",
            )
            return

        # 4d. Similarity Scoring
        similarity_metrics = None
        if narrative_activity is not None:
            try:
                similarity_metrics = self.similarity_service.calculate_from_activity(
                    narrative_activity
                )
            except (SimilarityInputError, TypeError) as exc:
                logger.exception(
                    "Fatal similarity input error for claim %s: %s", claim_id, exc
                )
                self._mark_claim_failed(
                    claim_id,
                    failure_stage="SYNTHESIS",
                    error_code="INVALID_INPUT_CONTRACT",
                )
                return
            except (SimilarityCalculationError, SimilarityServiceError) as exc:
                logger.warning(
                    "Operational similarity scoring failure for claim %s: %s",
                    claim_id,
                    exc,
                )
                similarity_metrics = None
            except Exception as exc:
                logger.exception(
                    "Unexpected fatal error during similarity scoring for claim %s: %s",
                    claim_id,
                    exc,
                )
                self._mark_claim_failed(
                    claim_id,
                    failure_stage="SYNTHESIS",
                    error_code="ANALYSIS_FAILED",
                )
                return

        # 4e. Rule Engine
        rule_validation_result = None
        rule_error = None
        try:
            rule_validation_result = self.rule_service.evaluate(cleaned_text)
        except (RuleConfigError, RuleInputError, TypeError) as exc:
            logger.exception("Fatal rule engine error for claim %s: %s", claim_id, exc)
            self._mark_claim_failed(
                claim_id,
                failure_stage="SYNTHESIS",
                error_code="INVALID_INPUT_CONTRACT",
            )
            return
        except RuleEngineError as exc:
            logger.warning(
                "Operational rule engine failure for claim %s: %s", claim_id, exc
            )
            rule_error = exc
        except Exception as exc:
            logger.exception(
                "Unexpected fatal error during rule evaluation for claim %s: %s",
                claim_id,
                exc,
            )
            self._mark_claim_failed(
                claim_id,
                failure_stage="SYNTHESIS",
                error_code="ANALYSIS_FAILED",
            )
            return

        # Step 5: Synthesis (Hybrid Credibility -> Verdict -> Explainability)
        try:
            hybrid_result = self.hybrid_engine.aggregate(
                model_output=model_output,
                fact_check_result=fact_check_result,
                rule_validation_result=rule_validation_result,
                narrative_activity=narrative_activity,
                model_error=model_error,
                fact_check_error=fact_check_error,
                rule_error=rule_error,
                narrative_error=narrative_error,
            )
        except (
            HybridConfigError,
            HybridInputError,
            HybridEngineError,
            TypeError,
        ) as exc:
            logger.exception(
                "Hybrid aggregation failure for claim %s: %s", claim_id, exc
            )
            self._mark_claim_failed(
                claim_id,
                failure_stage="SYNTHESIS",
                error_code="ANALYSIS_FAILED",
            )
            return
        except Exception as exc:
            logger.exception(
                "Unexpected error in hybrid aggregation for claim %s: %s", claim_id, exc
            )
            self._mark_claim_failed(
                claim_id,
                failure_stage="SYNTHESIS",
                error_code="ANALYSIS_FAILED",
            )
            return

        try:
            verdict_result = self.verdict_service.generate_verdict(hybrid_result)
        except (
            VerdictConfigError,
            VerdictInputError,
            VerdictEngineError,
            TypeError,
        ) as exc:
            logger.exception(
                "Verdict generation failure for claim %s: %s", claim_id, exc
            )
            self._mark_claim_failed(
                claim_id,
                failure_stage="SYNTHESIS",
                error_code="ANALYSIS_FAILED",
            )
            return
        except Exception as exc:
            logger.exception(
                "Unexpected error in verdict generation for claim %s: %s", claim_id, exc
            )
            self._mark_claim_failed(
                claim_id,
                failure_stage="SYNTHESIS",
                error_code="ANALYSIS_FAILED",
            )
            return

        model_version = None
        artifact_fingerprint = None
        get_provenance = getattr(self.model_service, "get_provenance_snapshot", None)
        if callable(get_provenance):
            try:
                snapshot = get_provenance()
                if isinstance(snapshot, tuple) and len(snapshot) == 2:
                    raw_version, raw_fingerprint = snapshot
                    model_version = (
                        raw_version if isinstance(raw_version, str) else None
                    )
                    artifact_fingerprint = (
                        raw_fingerprint if isinstance(raw_fingerprint, str) else None
                    )
            except Exception:
                logger.warning(
                    "Failed to retrieve model provenance snapshot for claim %s",
                    claim_id,
                    exc_info=True,
                )
        else:
            try:
                raw_v = getattr(self.model_service, "model_version", None)
                if isinstance(raw_v, str):
                    model_version = raw_v
            except Exception:
                pass
            try:
                raw_f = getattr(self.model_service, "artifact_fingerprint", None)
                if isinstance(raw_f, str):
                    artifact_fingerprint = raw_f
            except Exception:
                pass
        try:
            explainability_result = self.explainability_service.generate_explainability(
                hybrid_result,
                verdict_result,
                model_output=model_output,
                fact_check_result=fact_check_result,
                narrative_activity=narrative_activity,
                rule_validation_result=rule_validation_result,
                similarity_metrics=similarity_metrics,
                model_version=model_version,
                artifact_fingerprint=artifact_fingerprint,
            )
        except (ExplainabilityEngineError, ExplainabilityInputError, TypeError) as exc:
            logger.exception(
                "Explainability generation failure for claim %s: %s", claim_id, exc
            )
            self._mark_claim_failed(
                claim_id,
                failure_stage="SYNTHESIS",
                error_code="ANALYSIS_FAILED",
            )
            return
        except Exception as exc:
            logger.exception(
                "Unexpected error in explainability for claim %s: %s", claim_id, exc
            )
            self._mark_claim_failed(
                claim_id,
                failure_stage="SYNTHESIS",
                error_code="ANALYSIS_FAILED",
            )
            return

        # Step 6: Persistence Boundary (Strict separation of Zone 1 and Zone 2)
        try:
            self.persistence_service.persist_analysis(
                claim=claim,
                explainability_result=explainability_result,
            )
        except AnalysisPersistenceInputError as exc:
            logger.exception(
                "Persistence input validation failed for claim %s: %s", claim_id, exc
            )
            self._mark_claim_failed(
                claim_id,
                failure_stage="PERSISTENCE",
                error_code="INVALID_INPUT_CONTRACT",
            )
            return
        except (
            AnalysisAlreadyExistsError,
            AnalysisPersistenceError,
            DatabaseError,
        ) as exc:
            logger.warning(
                "Ambiguous persistence exception for claim %s (%s: %s). Initiating lock-based reconciliation.",
                claim_id,
                type(exc).__name__,
                exc,
            )
            self._reconcile_ambiguous_persistence(claim_id)
            return
        except Exception as exc:
            logger.exception(
                "Unexpected fatal error during persistence invocation for claim %s: %s",
                claim_id,
                exc,
            )
            self._mark_claim_failed(
                claim_id,
                failure_stage="PERSISTENCE",
                error_code="ANALYSIS_FAILED",
            )
            return

        # Step 7: Zone 2 - Post-Persistence Completion
        self._complete_pipeline(claim_id)

    def _reconcile_ambiguous_persistence(self, claim_id: uuid.UUID) -> None:
        """
        Reconciles claim status following an ambiguous persistence exception.
        Closes old connections to recover from failed transactions, acquires an exclusive
        row-level lock on Claim (matching AI-012's lock acquisition), inspects Analysis
        existence, and updates status conditionally.
        """
        if not connection.in_atomic_block:
            close_old_connections()
        try:
            with transaction.atomic():
                try:
                    locked_claim = Claim.objects.select_for_update().get(pk=claim_id)
                except Claim.DoesNotExist:
                    logger.warning("Reconciliation: Claim %s does not exist.", claim_id)
                    return

                if locked_claim.is_deleted:
                    logger.warning(
                        "Reconciliation: Claim %s was soft-deleted; skipping status change.",
                        claim_id,
                    )
                    return

                if locked_claim.status != ClaimStatus.PROCESSING:
                    logger.warning(
                        "Reconciliation: Claim %s is in status %s (expected PROCESSING); aborting.",
                        claim_id,
                        locked_claim.status,
                    )
                    return

                analysis_exists = Analysis.objects.filter(claim=locked_claim).exists()
                target_status = (
                    ClaimStatus.COMPLETED if analysis_exists else ClaimStatus.FAILED
                )

                updated = Claim.objects.filter(
                    id=claim_id,
                    status=ClaimStatus.PROCESSING,
                    is_deleted=False,
                ).update(
                    status=target_status,
                    updated_at=timezone.now(),
                )

                if updated == 1:
                    logger.info(
                        "Reconciliation succeeded for claim %s: status transitioned to %s (analysis_exists=%s).",
                        claim_id,
                        target_status,
                        analysis_exists,
                    )
                    if target_status == ClaimStatus.FAILED:
                        mapping = PUBLIC_ERROR_MAPPINGS["SERVICE_UNAVAILABLE"]
                        AnalysisFailureDiagnostic.objects.get_or_create(
                            claim_id=claim_id,
                            defaults={
                                "error_code": "SERVICE_UNAVAILABLE",
                                "error_message": mapping["error_message"],
                                "retryable": mapping["retryable"],
                                "failure_stage": "PERSISTENCE",
                            },
                        )
                else:
                    logger.error(
                        "Reconciliation conditional update unexpected result for claim %s: "
                        "expected exactly 1 row updated, got %d. Analysis exists: %s.",
                        claim_id,
                        updated,
                        analysis_exists,
                    )
        except Exception as exc:
            logger.exception(
                "Database error during reconciliation for claim %s: %s. "
                "Leaving claim in PROCESSING status to prevent false failure marking.",
                claim_id,
                exc,
            )

    def _complete_pipeline(self, claim_id: uuid.UUID) -> None:
        """
        Transitions a successfully analyzed and persisted claim from PROCESSING to COMPLETED.
        Zone 2 invariant: Any failure here must NEVER mark the claim FAILED because an
        Analysis record exists and is committed.
        """
        try:
            updated = Claim.objects.filter(
                id=claim_id,
                status=ClaimStatus.PROCESSING,
                is_deleted=False,
            ).update(
                status=ClaimStatus.COMPLETED,
                updated_at=timezone.now(),
            )
            if updated == 0:
                self._handle_completed_transition_failure(claim_id)
            else:
                logger.info(
                    "Claim %s successfully transitioned to COMPLETED.", claim_id
                )
        except Exception as exc:
            logger.exception(
                "Database error during post-persistence COMPLETED transition for claim %s: %s. "
                "Analysis record exists; preserving row without marking FAILED.",
                claim_id,
                exc,
            )

    def _handle_completed_transition_failure(self, claim_id: uuid.UUID) -> None:
        """
        Diagnoses why the conditional COMPLETED update affected 0 rows.
        Does NOT update status to FAILED.
        """
        try:
            claim = Claim.objects.get(id=claim_id)
            if claim.is_deleted:
                logger.warning(
                    "Post-persistence COMPLETED transition affected 0 rows for claim %s because "
                    "the claim was soft-deleted during analysis. Analysis record is preserved.",
                    claim_id,
                )
            elif claim.status == ClaimStatus.COMPLETED:
                logger.info(
                    "Post-persistence COMPLETED transition affected 0 rows for claim %s because "
                    "it was already marked COMPLETED.",
                    claim_id,
                )
            else:
                logger.error(
                    "Post-persistence state inconsistency for claim %s: expected PROCESSING, "
                    "found status=%s, is_deleted=%s. Preserving Analysis record without marking FAILED.",
                    claim_id,
                    claim.status,
                    claim.is_deleted,
                )
        except Claim.DoesNotExist:
            logger.error(
                "Post-persistence state inconsistency for claim %s: Claim record no longer exists. "
                "Analysis record is preserved.",
                claim_id,
            )
        except Exception as exc:
            logger.exception(
                "Failed to inspect claim %s after COMPLETED transition affected 0 rows: %s",
                claim_id,
                exc,
            )

    def _mark_claim_failed(
        self,
        claim_id: uuid.UUID,
        *,
        failure_stage: str,
        error_code: str = DEFAULT_FALLBACK_ERROR_CODE,
    ) -> None:
        """
        Atomically transitions a claim from PROCESSING to FAILED via conditional CAS
        and persists an AnalysisFailureDiagnostic record.

        Raises:
            ValueError: If failure_stage is not one of PREPROCESSING, SYNTHESIS, PERSISTENCE.
                        Raised BEFORE opening any database transaction or updating status.
        """
        if (
            not isinstance(failure_stage, str)
            or failure_stage.strip().upper() not in VALID_FAILURE_STAGES
        ):
            raise ValueError(
                f"Invalid failure_stage: '{failure_stage}'. Must be one of {sorted(VALID_FAILURE_STAGES)}"
            )
        normalized_stage = failure_stage.strip().upper()

        code = (
            error_code.strip().upper()
            if isinstance(error_code, str) and error_code.strip()
            else DEFAULT_FALLBACK_ERROR_CODE
        )
        if code not in PUBLIC_ERROR_MAPPINGS:
            logger.warning(
                "Unrecognized failure error_code '%s' for claim %s; normalizing to %s",
                error_code,
                claim_id,
                DEFAULT_FALLBACK_ERROR_CODE,
            )
            code = DEFAULT_FALLBACK_ERROR_CODE

        mapping = PUBLIC_ERROR_MAPPINGS[code]
        sanitized_message = mapping["error_message"]
        retryable = mapping["retryable"]

        try:
            with transaction.atomic():
                updated = Claim.objects.filter(
                    id=claim_id,
                    status=ClaimStatus.PROCESSING,
                    is_deleted=False,
                ).update(
                    status=ClaimStatus.FAILED,
                    updated_at=timezone.now(),
                )
                if updated == 0:
                    logger.info(
                        "Claim %s was not in active PROCESSING state; skipping FAILED transition.",
                        claim_id,
                    )
                    return

                AnalysisFailureDiagnostic.objects.get_or_create(
                    claim_id=claim_id,
                    defaults={
                        "error_code": code,
                        "error_message": sanitized_message,
                        "retryable": retryable,
                        "failure_stage": normalized_stage,
                    },
                )
                logger.info(
                    "Claim %s transitioned to FAILED: code=%s, stage=%s",
                    claim_id,
                    code,
                    normalized_stage,
                )
        except Exception as exc:
            logger.exception("Failed to mark claim %s as FAILED: %s", claim_id, exc)

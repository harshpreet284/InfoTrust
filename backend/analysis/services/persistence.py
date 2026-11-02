"""
Analysis Persistence Service (AI-012).
Persists standardized analysis outputs and links them to their corresponding claims.
Follows Clean Architecture, ADR-011, and ADR-012 using direct Django ORM writes within an atomic transaction.
"""

from django.db import IntegrityError, transaction

from analysis.models import Analysis
from analysis.services.explainability import ExplainabilityResult
from claims.models import Claim


class AnalysisPersistenceError(RuntimeError):
    """Base exception for all analysis persistence failures."""

    pass


class AnalysisPersistenceInputError(AnalysisPersistenceError):
    """Raised when persistence arguments violate domain contracts, are unsaved, or reference soft-deleted claims."""

    pass


class AnalysisAlreadyExistsError(AnalysisPersistenceError):
    """Raised when attempting to persist an analysis for a claim that already possesses one."""

    pass


class AnalysisPersistenceService:
    """
    Domain service for persisting standardized analysis outputs and linking them to claims.
    """

    def persist_analysis(
        self,
        *,
        claim: Claim,
        explainability_result: ExplainabilityResult,
    ) -> Analysis:
        """
        Persists an Analysis record for the given claim using the standardized ExplainabilityResult.

        Args:
            claim: An already-persisted Claim instance (with pk and _state.adding=False).
            explainability_result: Standardized ExplainabilityResult produced by AI-011.

        Returns:
            The newly created and persisted Analysis instance.

        Raises:
            AnalysisPersistenceInputError: If arguments fail type/state validation, claim is unsaved,
                claim is not found in database, or claim is soft-deleted.
            AnalysisAlreadyExistsError: If an Analysis record already exists for the given claim.
            AnalysisPersistenceError: If an unclassified database integrity failure occurs.
        """
        # 1. Validate claim instance and persisted state
        if not isinstance(claim, Claim):
            raise AnalysisPersistenceInputError(
                f"claim must be an instance of Claim, got {type(claim).__name__}."
            )
        if claim.pk is None or getattr(getattr(claim, "_state", None), "adding", True):
            raise AnalysisPersistenceInputError(
                "claim must be an already-saved database instance (_state.adding must be False and pk must be present)."
            )

        # 2. Validate explainability_result instance
        if not isinstance(explainability_result, ExplainabilityResult):
            raise AnalysisPersistenceInputError(
                f"explainability_result must be an instance of ExplainabilityResult, "
                f"got {type(explainability_result).__name__}."
            )

        # 3. Enter transaction.atomic boundary
        try:
            with transaction.atomic():
                # 4. Acquire exclusive row lock on PostgreSQL
                try:
                    locked_claim = Claim.objects.select_for_update().get(pk=claim.pk)
                except Claim.DoesNotExist as err:
                    raise AnalysisPersistenceInputError(
                        f"Claim with id {claim.pk} does not exist in the database."
                    ) from err

                # 5 & 6. Authoritative database soft-deletion validation
                if locked_claim.is_deleted:
                    raise AnalysisPersistenceInputError(
                        f"Cannot persist analysis for soft-deleted Claim {claim.pk}."
                    )

                # 7 & 8. Authoritative database duplicate check
                if Analysis.objects.filter(claim=locked_claim).exists():
                    raise AnalysisAlreadyExistsError(
                        f"Analysis already exists for Claim {claim.pk}."
                    )

                # 9. Create Analysis record using verified field mapping
                flags_triggered = (
                    explainability_result.rule_explanation.get("flags_triggered") or ()
                )
                rule_based_flags = {flag: True for flag in flags_triggered}

                verdict_val = (
                    explainability_result.verdict.value
                    if explainability_result.verdict is not None
                    else None
                )

                analysis = Analysis.objects.create(
                    claim=locked_claim,
                    credibility_score=explainability_result.credibility_score,
                    verdict=verdict_val,
                    explainability_json=explainability_result.to_internal_dict(),
                    model_prediction=explainability_result.model_explanation.get(
                        "prediction"
                    ),
                    model_confidence=explainability_result.model_explanation.get(
                        "confidence"
                    ),
                    fact_check_summary=explainability_result.fact_check_explanation.get(
                        "summary"
                    ),
                    fact_check_match_count=explainability_result.fact_check_explanation.get(
                        "matches_count"
                    ),
                    narrative_match_count=explainability_result.narrative_explanation.get(
                        "similar_claims_count"
                    ),
                    highest_similarity_score=explainability_result.similarity_explanation.get(
                        "highest_similarity_score"
                    ),
                    rule_based_flags=rule_based_flags,
                    final_weighted_score=explainability_result.credibility_score,
                )

                # 10. Return persisted instance
                return analysis

        except IntegrityError as err:
            # Step 11: Structured constraint classification strictly outside atomic block
            cause = getattr(err, "__cause__", None)
            diag = getattr(cause, "diag", None)
            constraint_name = getattr(diag, "constraint_name", None)

            if constraint_name == "analysis_analysis_pkey":
                raise AnalysisAlreadyExistsError(
                    f"Analysis already exists for Claim {claim.pk}."
                ) from err

            raise AnalysisPersistenceError(
                f"Database integrity failure while persisting analysis for Claim {claim.pk}: {err}"
            ) from err

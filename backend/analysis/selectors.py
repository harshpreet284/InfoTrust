"""
Analysis Selectors (AI-013).
Handles read-only queries, data access, and authorization checks for Analysis APIs.
Enforces ADR-011 and ADR-012 with single-query pre-fetching and strict field whitelisting.
"""

import uuid
from typing import Any, Dict, List, Optional

from django.http import Http404
from ninja.errors import AuthorizationError, HttpError

from analysis.models import Analysis
from analysis.schemas import (
    AnalysisExplanationData,
    AnalysisStatusData,
    AnalysisSummaryData,
    FactCheckEvidenceData,
    FactCheckSourceSchema,
    NarrativeActivityData,
    ScoreBreakdownSchema,
)
from authentication.models import User
from claims.models import Claim, ClaimStatus
from claims.permissions import is_admin_user


def get_claim_with_analysis_for_user(claim_id: uuid.UUID, user: User) -> Claim:
    """
    Fetches an active (non-soft-deleted) Claim with its linked Analysis record pre-fetched.
    Uses select_related("analysis") to execute a single joined SQL query (LEFT OUTER JOIN).
    Enforces ownership authorization (owner or administrator).
    Raises Http404 if claim does not exist or is soft-deleted.
    Raises AuthorizationError (HTTP 403) if user is not authorized.
    """
    try:
        claim = (
            Claim.objects.filter(id=claim_id, is_deleted=False)
            .select_related("analysis")
            .get()
        )
    except Claim.DoesNotExist:
        raise Http404("Claim not found.")

    if not is_admin_user(user) and claim.user_id != user.id:
        raise AuthorizationError("You do not have permission to view this analysis.")

    return claim


def _require_completed_analysis(claim: Claim) -> Analysis:
    """
    Enforces the approved 6-state completed-analysis validation matrix:
    - PENDING (no analysis): 409 Conflict ("Analysis still processing.")
    - PROCESSING (no analysis): 409 Conflict ("Analysis still processing.")
    - FAILED (no analysis): 409 Conflict ("Analysis could not be completed.")
    - FAILED (analysis exists): 409 Conflict ("Analysis could not be completed.")
    - COMPLETED (no analysis): 409 Conflict ("Analysis data is incomplete.")
    - COMPLETED (analysis exists): Return Analysis instance.
    """
    if claim.status in (ClaimStatus.PENDING, ClaimStatus.PROCESSING):
        raise HttpError(409, "Analysis still processing.")

    if claim.status == ClaimStatus.FAILED:
        raise HttpError(409, "Analysis could not be completed.")

    if claim.status == ClaimStatus.COMPLETED:
        if not hasattr(claim, "analysis") or claim.analysis is None:
            raise HttpError(409, "Analysis data is incomplete.")
        return claim.analysis

    raise HttpError(409, f"Claim is in invalid analysis state: {claim.status}.")


def get_analysis_status_data(claim_id: uuid.UUID, user: User) -> AnalysisStatusData:
    """
    Retrieves the processing status of an analysis for a claim.
    """
    claim = get_claim_with_analysis_for_user(claim_id, user)
    return AnalysisStatusData(claim_id=claim.id, status=claim.status)


def get_analysis_summary_data(claim_id: uuid.UUID, user: User) -> AnalysisSummaryData:
    """
    Retrieves the core analysis summary for a completed claim.
    Explicitly maps analysis.analysis_timestamp to created_at.
    """
    claim = get_claim_with_analysis_for_user(claim_id, user)
    analysis = _require_completed_analysis(claim)
    return AnalysisSummaryData(
        claim_id=claim.id,
        analysis_status=claim.status,
        verdict=analysis.verdict,
        credibility_score=analysis.credibility_score,
        created_at=analysis.analysis_timestamp,
    )


def _to_float_or_none(val: Any) -> Optional[float]:
    """Helper to safely convert numeric values to float while strictly preserving None."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def get_analysis_explanation_data(
    claim_id: uuid.UUID, user: User
) -> AnalysisExplanationData:
    """
    Retrieves explainability report for a completed claim.
    Constructs public response strictly from whitelisted fields; never exposes internal diagnostics.
    """
    claim = get_claim_with_analysis_for_user(claim_id, user)
    analysis = _require_completed_analysis(claim)
    exp: Dict[str, Any] = analysis.explainability_json or {}

    raw_sb = exp.get("score_breakdown") or {}
    score_breakdown = ScoreBreakdownSchema(
        classification_model=_to_float_or_none(
            (raw_sb.get("model") or {}).get("weighted_contribution")
        ),
        fact_check=_to_float_or_none(
            (raw_sb.get("fact_check") or {}).get("weighted_contribution")
        ),
        narrative=_to_float_or_none(
            (raw_sb.get("narrative") or {}).get("weighted_contribution")
        ),
        rule_engine=_to_float_or_none(
            (raw_sb.get("rule_engine") or {}).get("weighted_contribution")
        ),
    )

    reasoning_list = exp.get("reasoning") or []
    if not isinstance(reasoning_list, (list, tuple)):
        reasoning_list = []

    return AnalysisExplanationData(
        verdict=analysis.verdict,
        credibility_score=analysis.credibility_score,
        score_breakdown=score_breakdown,
        reasoning=[str(r) for r in reasoning_list],
    )


def get_analysis_narrative_data(
    claim_id: uuid.UUID, user: User
) -> NarrativeActivityData:
    """
    Retrieves narrative recurrence metrics for a completed claim.
    Preserves NULL vs. genuine zero counts and activity levels.
    """
    claim = get_claim_with_analysis_for_user(claim_id, user)
    analysis = _require_completed_analysis(claim)
    exp: Dict[str, Any] = analysis.explainability_json or {}
    narrative_comp = (exp.get("components") or {}).get("narrative") or {}

    # 1. Preserving NULL vs. genuine zero for similar_claims
    similar_claims = analysis.narrative_match_count
    if similar_claims is None and "similar_claims_count" in narrative_comp:
        similar_claims = narrative_comp.get("similar_claims_count")

    # 2. Highest similarity percentage
    raw_sim = analysis.highest_similarity_score
    if raw_sim is None:
        raw_sim = (
            (exp.get("components") or {})
            .get("similarity", {})
            .get("highest_similarity_score")
        )

    highest_sim = None
    if raw_sim is not None:
        try:
            val = float(raw_sim)
            highest_sim = round(val * 100, 1) if val <= 1.0 else val
        except (ValueError, TypeError):
            highest_sim = None

    # 3. Activity level resolution: preserve evaluated activity level only
    detail_status = narrative_comp.get("detail_status")
    raw_activity = narrative_comp.get("activity_level")
    if detail_status == "FULL" and raw_activity in ("LOW", "MEDIUM", "HIGH"):
        activity_level = raw_activity
    else:
        activity_level = None

    return NarrativeActivityData(
        similar_claims=similar_claims,
        highest_similarity=highest_sim,
        first_seen=narrative_comp.get("first_seen"),
        latest_occurrence=narrative_comp.get("latest_occurrence"),
        activity_level=activity_level,
    )


def get_analysis_fact_check_data(
    claim_id: uuid.UUID, user: User
) -> FactCheckEvidenceData:
    """
    Retrieves fact-check reviews and matched sources for a completed claim.
    Preserves NULL vs. genuine zero counts and exposes only verified source fields.
    """
    claim = get_claim_with_analysis_for_user(claim_id, user)
    analysis = _require_completed_analysis(claim)
    exp: Dict[str, Any] = analysis.explainability_json or {}
    fc_comp = (exp.get("components") or {}).get("fact_check") or {}

    # 1. Preserving NULL vs. genuine zero for matches_found
    matches_found = analysis.fact_check_match_count
    if matches_found is None and "matches_count" in fc_comp:
        matches_found = fc_comp.get("matches_count")

    summary = analysis.fact_check_summary
    if summary is None:
        summary = fc_comp.get("summary")

    raw_sources = fc_comp.get("sources") or []
    sources: List[FactCheckSourceSchema] = []
    if isinstance(raw_sources, (list, tuple)):
        for s in raw_sources:
            if isinstance(s, dict):
                pub = s.get("publisher")
                rat = s.get("rating")
                u = s.get("url")
                if (
                    isinstance(pub, str)
                    and bool(pub.strip())
                    and isinstance(rat, str)
                    and bool(rat.strip())
                    and isinstance(u, str)
                    and bool(u.strip())
                ):
                    rev_date = s.get("review_date")
                    clean_date = (
                        str(rev_date).strip()
                        if rev_date is not None and bool(str(rev_date).strip())
                        else None
                    )
                    sources.append(
                        FactCheckSourceSchema(
                            publisher=pub.strip(),
                            rating=rat.strip(),
                            url=u.strip(),
                            review_date=clean_date,
                        )
                    )

    return FactCheckEvidenceData(
        matches_found=matches_found,
        summary=summary,
        sources=sources,
    )

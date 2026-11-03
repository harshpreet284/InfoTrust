"""
Analysis API Endpoints (AI-013).
Exposes RESTful GET endpoints for analysis status, summary, explainability,
narrative activity, and fact-check evidence according to API_SPEC.md.
"""

import uuid

from ninja import Router

from analysis.permissions import AnalysisEndpointAuth
from analysis.schemas import (
    AnalysisExplanationOut,
    AnalysisStatusOut,
    AnalysisSummaryOut,
    FactCheckEvidenceOut,
    NarrativeActivityOut,
)
from analysis.selectors import (
    get_analysis_explanation_data,
    get_analysis_fact_check_data,
    get_analysis_narrative_data,
    get_analysis_status_data,
    get_analysis_summary_data,
)
from shared.schemas import ErrorResponse

router = Router(tags=["Analysis"], auth=AnalysisEndpointAuth())


@router.get(
    "/{claim_id}/status",
    response={
        200: AnalysisStatusOut,
        401: ErrorResponse,
        403: ErrorResponse,
        404: ErrorResponse,
        422: ErrorResponse,
    },
    summary="Get analysis status",
    description="Retrieve the current processing status of an AI analysis for a submitted claim.",
)
def get_analysis_status_endpoint(request, claim_id: uuid.UUID):
    data = get_analysis_status_data(claim_id=claim_id, user=request.user)
    return 200, {
        "success": True,
        "message": "Analysis status retrieved successfully.",
        "data": data,
    }


@router.get(
    "/{claim_id}",
    response={
        200: AnalysisSummaryOut,
        401: ErrorResponse,
        403: ErrorResponse,
        404: ErrorResponse,
        409: ErrorResponse,
        422: ErrorResponse,
    },
    summary="Get analysis result",
    description="Retrieve the completed AI analysis summary for a submitted claim.",
)
def get_analysis_summary_endpoint(request, claim_id: uuid.UUID):
    data = get_analysis_summary_data(claim_id=claim_id, user=request.user)
    return 200, {
        "success": True,
        "message": "Analysis retrieved successfully.",
        "data": data,
    }


@router.get(
    "/{claim_id}/explanation",
    response={
        200: AnalysisExplanationOut,
        401: ErrorResponse,
        403: ErrorResponse,
        404: ErrorResponse,
        409: ErrorResponse,
        422: ErrorResponse,
    },
    summary="Get explainability report",
    description="Retrieve the complete explainability report including score breakdown and reasoning statements.",
)
def get_analysis_explanation_endpoint(request, claim_id: uuid.UUID):
    data = get_analysis_explanation_data(claim_id=claim_id, user=request.user)
    return 200, {
        "success": True,
        "message": "Explainability data retrieved successfully.",
        "data": data,
    }


@router.get(
    "/{claim_id}/narrative",
    response={
        200: NarrativeActivityOut,
        401: ErrorResponse,
        403: ErrorResponse,
        404: ErrorResponse,
        409: ErrorResponse,
        422: ErrorResponse,
    },
    summary="Get narrative activity",
    description="Retrieve narrative recurrence metrics and historical similarity data.",
)
def get_analysis_narrative_endpoint(request, claim_id: uuid.UUID):
    data = get_analysis_narrative_data(claim_id=claim_id, user=request.user)
    return 200, {
        "success": True,
        "message": "Narrative activity retrieved successfully.",
        "data": data,
    }


@router.get(
    "/{claim_id}/fact-check",
    response={
        200: FactCheckEvidenceOut,
        401: ErrorResponse,
        403: ErrorResponse,
        404: ErrorResponse,
        409: ErrorResponse,
        422: ErrorResponse,
    },
    summary="Get fact-check evidence",
    description="Retrieve external fact-checking reviews and matched sources used during analysis.",
)
def get_analysis_fact_check_endpoint(request, claim_id: uuid.UUID):
    data = get_analysis_fact_check_data(claim_id=claim_id, user=request.user)
    return 200, {
        "success": True,
        "message": "Fact-check evidence retrieved successfully.",
        "data": data,
    }

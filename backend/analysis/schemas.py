"""
Analysis API Schemas (AI-013).
Defines Django Ninja response schemas for analysis status, summary, explainability,
narrative activity, and fact-check evidence endpoints.
Preserves strict NULL vs. zero semantics and enforces field whitelisting.
"""

import uuid
from datetime import datetime
from typing import List, Optional

from ninja import Schema
from pydantic import Field


# ---------------------------------------------------------------------------
# ANALYSIS-001: Analysis Status Schemas
# ---------------------------------------------------------------------------
class AnalysisStatusData(Schema):
    claim_id: uuid.UUID = Field(..., description="Unique claim identifier.")
    status: str = Field(
        ..., description="Current status: PENDING, PROCESSING, COMPLETED, or FAILED."
    )


class AnalysisStatusOut(Schema):
    success: bool = Field(True, description="Indicates request success.")
    message: str = Field(
        "Analysis status retrieved successfully.", description="Status message."
    )
    data: AnalysisStatusData


# ---------------------------------------------------------------------------
# ANALYSIS-002: Core Analysis Summary Schemas
# ---------------------------------------------------------------------------
class AnalysisSummaryData(Schema):
    claim_id: uuid.UUID = Field(..., description="Unique claim identifier.")
    analysis_status: str = Field(..., description="Lifecycle status of the claim.")
    verdict: Optional[str] = Field(
        None,
        description="Final credibility verdict (CREDIBLE, UNCERTAIN, MISINFORMATION).",
    )
    credibility_score: Optional[float] = Field(
        None, description="Composite credibility score (0.0 to 100.0)."
    )
    created_at: datetime = Field(
        ...,
        description="Timestamp when analysis was persisted (mapped from analysis_timestamp).",
    )


class AnalysisSummaryOut(Schema):
    success: bool = Field(True, description="Indicates request success.")
    message: str = Field(
        "Analysis retrieved successfully.", description="Status message."
    )
    data: AnalysisSummaryData


# ---------------------------------------------------------------------------
# ANALYSIS-003: Explainability Schemas
# ---------------------------------------------------------------------------
class ScoreBreakdownSchema(Schema):
    classification_model: Optional[float] = Field(
        None, description="Weighted contribution from AI classification model."
    )
    fact_check: Optional[float] = Field(
        None, description="Weighted contribution from external fact-check reviews."
    )
    narrative: Optional[float] = Field(
        None, description="Weighted contribution from historical narrative recurrence."
    )
    rule_engine: Optional[float] = Field(
        None, description="Weighted contribution from deterministic rule heuristics."
    )


class AnalysisExplanationData(Schema):
    verdict: Optional[str] = Field(None, description="Final credibility verdict.")
    credibility_score: Optional[float] = Field(
        None, description="Composite credibility score."
    )
    score_breakdown: ScoreBreakdownSchema = Field(
        ..., description="Component weighted score contributions."
    )
    reasoning: List[str] = Field(
        ..., description="Synthesized deterministic reasoning statements."
    )


class AnalysisExplanationOut(Schema):
    success: bool = Field(True, description="Indicates request success.")
    message: str = Field(
        "Explainability data retrieved successfully.", description="Status message."
    )
    data: AnalysisExplanationData


# ---------------------------------------------------------------------------
# ANALYSIS-004: Narrative Activity Schemas
# ---------------------------------------------------------------------------
class NarrativeActivityData(Schema):
    similar_claims: Optional[int] = Field(
        None,
        description="Count of similar historical claims found (None if unperformed, 0 if zero matches).",
    )
    highest_similarity: Optional[float] = Field(
        None, description="Highest similarity score percentage (0.0 to 100.0)."
    )
    first_seen: Optional[str] = Field(
        None, description="Earliest occurrence ISO timestamp of matching narrative."
    )
    latest_occurrence: Optional[str] = Field(
        None, description="Most recent occurrence ISO timestamp of matching narrative."
    )
    activity_level: Optional[str] = Field(
        None,
        description="Evaluated activity level (LOW, MEDIUM, HIGH) or None if unperformed/failed.",
    )


class NarrativeActivityOut(Schema):
    success: bool = Field(True, description="Indicates request success.")
    message: str = Field(
        "Narrative activity retrieved successfully.", description="Status message."
    )
    data: NarrativeActivityData


# ---------------------------------------------------------------------------
# ANALYSIS-005: Fact-check Evidence Schemas
# ---------------------------------------------------------------------------
class FactCheckSourceSchema(Schema):
    publisher: str = Field(..., description="Name of external fact-checking publisher.")
    rating: str = Field(..., description="Publisher rating or verdict label.")
    url: str = Field(..., description="Canonical URL to fact-check review article.")
    review_date: Optional[str] = Field(
        None, description="Publication date of fact-check review."
    )


class FactCheckEvidenceData(Schema):
    matches_found: Optional[int] = Field(
        None,
        description="Total matching fact-check reviews found (None if unperformed, 0 if zero matches).",
    )
    summary: Optional[str] = Field(
        None, description="High-level summary of fact-check evidence."
    )
    sources: List[FactCheckSourceSchema] = Field(
        ..., description="List of verified fact-check sources."
    )


class FactCheckEvidenceOut(Schema):
    success: bool = Field(True, description="Indicates request success.")
    message: str = Field(
        "Fact-check evidence retrieved successfully.", description="Status message."
    )
    data: FactCheckEvidenceData

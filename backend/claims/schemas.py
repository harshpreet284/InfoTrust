import uuid
from datetime import date, datetime
from typing import List, Optional

from ninja import ModelSchema, Schema
from pydantic import Field, field_validator, model_validator

from analysis.models import Verdict
from claims.models import Claim, ClaimStatus
from shared.pagination import PaginationParamsSchema


import re

ALLOWED_CLAIM_ORDERING_FIELDS = frozenset({
    "-created_at",
    "created_at",
    "-credibility_score",
    "credibility_score",
    "-status",
    "status",
})


def _validate_ordering(v: Optional[str]) -> Optional[str]:
    if v is not None and v not in ALLOWED_CLAIM_ORDERING_FIELDS:
        allowed = ", ".join(sorted(ALLOWED_CLAIM_ORDERING_FIELDS))
        raise ValueError(f"Invalid ordering '{v}'. Allowed fields: {allowed}")
    return v

class ClaimCreateSchema(Schema):
    claim_text: str = Field(
        ...,
        min_length=10,
        max_length=2000,
        description="The full textual content of the claim to be analyzed (10 to 2000 characters). Leading and trailing whitespace is stripped; plain text only, HTML tags are not allowed.",
        examples=["The World Health Organization announced the eradication of a new viral strain in Geneva today."],
    )

    @field_validator("claim_text", mode="before")
    @classmethod
    def strip_whitespace(cls, v):
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("claim_text", mode="after")
    @classmethod
    def reject_html(cls, v: str) -> str:
        if re.search(r"<[a-zA-Z\/][^>]*>", v):
            raise ValueError("Claim text must be plain text only. HTML is not allowed.")
        return v


class ClaimResponseSchema(ModelSchema):
    claim_text: str
    created_at: datetime

    class Meta:
        model = Claim
        fields = ["id", "status"]

    @staticmethod
    def resolve_claim_text(obj: Claim) -> str:
        return obj.text

    @staticmethod
    def resolve_created_at(obj: Claim) -> datetime:
        return obj.submitted_at


class ClaimSubmitSuccessOut(Schema):
    success: bool = True
    message: str = "Claim submitted successfully."
    data: ClaimResponseSchema


class ClaimDetailResponseSchema(Schema):
    id: uuid.UUID
    claim_text: str
    status: str
    created_at: datetime
    updated_at: datetime
    analysis_available: bool

    @staticmethod
    def resolve_claim_text(obj: Claim) -> str:
        return obj.text

    @staticmethod
    def resolve_created_at(obj: Claim) -> datetime:
        return obj.submitted_at

    @staticmethod
    def resolve_analysis_available(obj: Claim) -> bool:
        return hasattr(obj, 'analysis')


class ClaimDetailSuccessOut(Schema):
    success: bool = True
    message: str = "Claim retrieved successfully."
    data: ClaimDetailResponseSchema


def _normalize_and_validate_status(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, str):
        v_cleaned = v.strip().upper()
        if not v_cleaned:
            return None
        if v_cleaned not in ClaimStatus.values:
            allowed = ", ".join(ClaimStatus.values)
            raise ValueError(f"Invalid status '{v}'. Allowed values: {allowed}")
        return v_cleaned
    raise ValueError("Status must be a string.")


def _normalize_and_validate_verdict(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, str):
        v_cleaned = v.strip().upper()
        if not v_cleaned:
            return None
        if v_cleaned not in Verdict.values:
            allowed = ", ".join(Verdict.values)
            raise ValueError(f"Invalid verdict '{v}'. Allowed values: {allowed}")
        return v_cleaned
    raise ValueError("Verdict must be a string.")


def _validate_date_range(date_from: Optional[date], date_to: Optional[date]):
    if date_from and date_to and date_from > date_to:
        raise ValueError(f"date_from ({date_from}) cannot be after date_to ({date_to}).")


class ClaimHistoryFilterSchema(Schema):
    page: int = Field(1, ge=1, description="Page number (1-based)")
    page_size: int = Field(10, ge=1, le=100, description="Page size (1-100)")
    ordering: Optional[str] = Field(None, description="Sort field (e.g. -created_at, credibility_score)")
    search: Optional[str] = Field(None, description="Search query string")
    status: Optional[str] = Field(None, description="Filter by claim analysis status (e.g. PENDING, PROCESSING, COMPLETED, FAILED)")
    verdict: Optional[str] = Field(None, description="Filter by analysis verdict (e.g. CREDIBLE, UNCERTAIN, MISINFORMATION)")
    date_from: Optional[date] = Field(None, description="Filter claims submitted on or after this date (YYYY-MM-DD)")
    date_to: Optional[date] = Field(None, description="Filter claims submitted on or before this date (YYYY-MM-DD)")

    @field_validator("ordering")
    @classmethod
    def validate_ordering(cls, v: Optional[str]) -> Optional[str]:
        return _validate_ordering(v)

    @field_validator("status", mode="before")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        return _normalize_and_validate_status(v)

    @field_validator("verdict", mode="before")
    @classmethod
    def validate_verdict(cls, v: Optional[str]) -> Optional[str]:
        return _normalize_and_validate_verdict(v)

    @model_validator(mode="after")
    def validate_date_range(self):
        _validate_date_range(self.date_from, self.date_to)
        return self


class ClaimHistoryItemSchema(Schema):
    id: uuid.UUID
    claim_text: str
    status: str
    verdict: Optional[str] = None
    credibility_score: Optional[float] = None
    created_at: datetime

    @staticmethod
    def resolve_claim_text(obj: Claim) -> str:
        return obj.text

    @staticmethod
    def resolve_created_at(obj: Claim) -> datetime:
        return obj.submitted_at

    @staticmethod
    def resolve_verdict(obj: Claim) -> Optional[str]:
        if hasattr(obj, "analysis") and obj.analysis is not None:
            return obj.analysis.verdict
        return None

    @staticmethod
    def resolve_credibility_score(obj: Claim) -> Optional[float]:
        if hasattr(obj, "analysis") and obj.analysis is not None:
            return obj.analysis.credibility_score
        return None


class ClaimHistoryPaginationOut(Schema):
    count: int
    next: Optional[str] = None
    previous: Optional[str] = None
    results: List[ClaimHistoryItemSchema]


class ClaimUpdateSchema(ClaimCreateSchema):
    """
    Schema for updating claim text.
    Reuses existing validation: min 10, max 2000, whitespace stripping, and HTML rejection.
    """
    pass


class ClaimUpdateDataOut(Schema):
    id: uuid.UUID


class ClaimUpdateSuccessOut(Schema):
    success: bool = True
    message: str = "Claim updated successfully."
    data: ClaimUpdateDataOut


class AdminClaimItemSchema(Schema):
    claim_id: uuid.UUID
    claim_text: str
    submitted_by: str
    analysis_status: str
    verdict: Optional[str] = None
    created_at: datetime

    @staticmethod
    def resolve_claim_id(obj: Claim) -> uuid.UUID:
        return obj.id

    @staticmethod
    def resolve_claim_text(obj: Claim) -> str:
        return obj.text

    @staticmethod
    def resolve_submitted_by(obj: Claim) -> str:
        return obj.user.full_name or obj.user.email

    @staticmethod
    def resolve_analysis_status(obj: Claim) -> str:
        return obj.status

    @staticmethod
    def resolve_verdict(obj: Claim) -> Optional[str]:
        if hasattr(obj, "analysis") and obj.analysis is not None:
            return obj.analysis.verdict
        return None

    @staticmethod
    def resolve_created_at(obj: Claim) -> datetime:
        return obj.submitted_at


class AdminClaimPaginationOut(Schema):
    count: int
    next: Optional[str] = None
    previous: Optional[str] = None
    results: List[AdminClaimItemSchema]


class AdminClaimFilterSchema(PaginationParamsSchema):
    ordering: Optional[str] = Field(None, description="Sort field (e.g. -created_at, credibility_score)")
    search: Optional[str] = Field(None, description="Search query string")
    status: Optional[str] = Field(None, description="Filter by claim analysis status (e.g. PENDING, PROCESSING, COMPLETED, FAILED)")
    verdict: Optional[str] = Field(None, description="Filter by analysis verdict (e.g. CREDIBLE, UNCERTAIN, MISINFORMATION)")
    date_from: Optional[date] = Field(None, description="Filter claims submitted on or after this date (YYYY-MM-DD)")
    date_to: Optional[date] = Field(None, description="Filter claims submitted on or before this date (YYYY-MM-DD)")
    user_id: Optional[uuid.UUID] = Field(None, description="Filter claims submitted by a specific user UUID")

    @field_validator("ordering")
    @classmethod
    def validate_ordering(cls, v: Optional[str]) -> Optional[str]:
        return _validate_ordering(v)

    @field_validator("status", mode="before")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        return _normalize_and_validate_status(v)

    @field_validator("verdict", mode="before")
    @classmethod
    def validate_verdict(cls, v: Optional[str]) -> Optional[str]:
        return _normalize_and_validate_verdict(v)

    @model_validator(mode="after")
    def validate_date_range(self):
        _validate_date_range(self.date_from, self.date_to)
        return self

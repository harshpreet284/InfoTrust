import uuid
from datetime import datetime
from typing import List, Optional

from ninja import ModelSchema, Schema
from pydantic import Field, field_validator

from claims.models import Claim
from claims.selectors import ORDERING_MAP


import re

class ClaimCreateSchema(Schema):
    claim_text: str = Field(..., min_length=10, max_length=2000)

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


class ClaimHistoryFilterSchema(Schema):
    page: int = Field(1, ge=1, description="Page number (1-based)")
    page_size: int = Field(10, ge=1, le=100, description="Page size (1-100)")
    ordering: Optional[str] = Field(None, description="Sort field (e.g. -created_at, credibility_score)")

    @field_validator("ordering")
    @classmethod
    def validate_ordering(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ORDERING_MAP:
            allowed = ", ".join(sorted(ORDERING_MAP.keys()))
            raise ValueError(f"Invalid ordering '{v}'. Allowed fields: {allowed}")
        return v


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



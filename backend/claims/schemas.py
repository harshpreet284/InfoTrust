from datetime import datetime

from ninja import ModelSchema, Schema
from pydantic import Field, field_validator

from claims.models import Claim


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

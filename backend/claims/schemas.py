from datetime import datetime

from ninja import ModelSchema, Schema
from pydantic import Field

from claims.models import Claim


class ClaimCreateSchema(Schema):
    claim_text: str = Field(..., min_length=10, max_length=2000)


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

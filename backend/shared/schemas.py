from typing import Generic, Optional, TypeVar
from ninja import Schema
from pydantic import Field

T = TypeVar("T")


class SuccessResponse(Schema, Generic[T]):
    success: bool = True
    data: Optional[T] = None


class ErrorResponse(Schema):
    success: bool = Field(False, description="Indicates request failure.")
    message: str = Field(..., description="Human-readable explanation of the error.")
    error_code: str = Field(..., description="Standardized error code identifying the error type.")


class RateLimitErrorOut(Schema):
    success: bool = Field(False, description="Indicates request failure.")
    message: str = Field(
        "Rate limit exceeded. Please try again later.",
        description="Rate limit explanation message.",
    )


class ServiceUnavailableErrorOut(Schema):
    success: bool = Field(False, description="Indicates service unavailability.")
    message: str = Field(
        "Service temporarily unavailable. Please try again later.",
        description="Fail-closed temporary unavailability message.",
    )

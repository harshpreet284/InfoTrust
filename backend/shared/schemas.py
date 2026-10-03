from typing import Generic, TypeVar, Optional
from ninja import Schema

T = TypeVar("T")


class SuccessResponse(Schema, Generic[T]):
    success: bool = True
    data: Optional[T] = None


class ErrorResponse(Schema):
    success: bool = False
    message: str
    error_code: str

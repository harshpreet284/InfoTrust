import re
import uuid
from datetime import datetime

from ninja import Schema
from pydantic import EmailStr, Field, field_validator, model_validator


class AuthErrorOut(Schema):
    success: bool = Field(False, description="Indicates request failure.")
    message: str = Field(..., description="Authentication or authorization error message.")


class RegistrationConflictOut(Schema):
    success: bool = Field(False, description="Indicates conflict failure.")
    message: str = Field("Email already exists.", description="Conflict error summary.")
    errors: dict[str, list[str]] = Field(..., description="Field-specific conflict details.")


class RegistrationIn(Schema):
    full_name: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Full name of the user (2 to 100 characters).",
        examples=["Jane Doe"],
    )
    email: EmailStr = Field(
        ...,
        description="Valid user email address.",
        examples=["jane.doe@example.com"],
    )
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Account password (8-128 chars, at least 1 uppercase, 1 lowercase, 1 number, 1 special char).",
        examples=["StrongPass123!"],
    )
    confirm_password: str = Field(
        ...,
        description="Password confirmation matching password.",
        examples=["StrongPass123!"],
    )

    @field_validator("full_name", mode="before")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("email")
    @classmethod
    def lowercase_email(cls, v: str) -> str:
        return v.lower()

    @field_validator("password")
    @classmethod
    def validate_password_complexity(cls, v: str) -> str:
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter.")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter.")
        if not re.search(r"[0-9]", v):
            raise ValueError("Password must contain at least one number.")
        if not re.search(r"[^A-Za-z0-9]", v):
            raise ValueError("Password must contain at least one special character.")
        return v

    @model_validator(mode="after")
    def check_passwords_match(self) -> "RegistrationIn":
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match.")
        return self


class UserOut(Schema):
    id: uuid.UUID
    full_name: str
    email: str
    role: str
    created_at: datetime


class RegistrationSuccessOut(Schema):
    success: bool = True
    message: str = "Registration successful."
    data: UserOut


class LoginIn(Schema):
    email: EmailStr = Field(
        ...,
        description="User account email address.",
        examples=["jane.doe@example.com"],
    )
    password: str = Field(
        ...,
        description="User account password.",
        examples=["StrongPass123!"],
    )

    @field_validator("email")
    @classmethod
    def lowercase_email(cls, v: str) -> str:
        return v.lower()


class LoginDataOut(Schema):
    access_token: str
    refresh_token: str
    user: UserOut


class LoginSuccessOut(Schema):
    success: bool = True
    message: str = "Login successful."
    data: LoginDataOut


class RefreshTokenIn(Schema):
    refresh_token: str = Field(
        ...,
        description="Valid JWT refresh token issued by login or token refresh.",
        examples=["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."],
    )



class RefreshDataOut(Schema):
    access_token: str
    refresh_token: str


class RefreshSuccessOut(Schema):
    success: bool = True
    message: str = "Token refreshed successfully."
    data: RefreshDataOut


class LogoutSuccessOut(Schema):
    success: bool = True
    message: str = "Logged out successfully."
    data: dict = {}


class CurrentUserOut(Schema):
    id: uuid.UUID
    full_name: str
    email: str
    role: str
    created_at: datetime
    is_active: bool


class CurrentUserSuccessOut(Schema):
    success: bool = True
    message: str = "User profile retrieved successfully."
    data: CurrentUserOut

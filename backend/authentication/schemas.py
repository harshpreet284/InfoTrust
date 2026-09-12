import re
import uuid
from datetime import datetime
from ninja import Schema
from pydantic import EmailStr, field_validator, model_validator, Field

class RegistrationIn(Schema):
    full_name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    confirm_password: str

    @field_validator('full_name', mode='before')
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator('email')
    @classmethod
    def lowercase_email(cls, v: str) -> str:
        return v.lower()

    @field_validator('password')
    @classmethod
    def validate_password_complexity(cls, v: str) -> str:
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter.')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter.')
        if not re.search(r'[0-9]', v):
            raise ValueError('Password must contain at least one number.')
        if not re.search(r'[^A-Za-z0-9]', v):
            raise ValueError('Password must contain at least one special character.')
        return v

    @model_validator(mode='after')
    def check_passwords_match(self) -> 'RegistrationIn':
        if self.password != self.confirm_password:
            raise ValueError('Passwords do not match.')
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
    email: EmailStr
    password: str

    @field_validator('email')
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
    refresh_token: str

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

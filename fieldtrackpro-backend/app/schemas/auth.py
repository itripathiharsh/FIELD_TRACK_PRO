"""
Auth request/response schemas.
"""
from __future__ import annotations

from pydantic import BaseModel, EmailStr, field_validator, model_validator


class LoginRequest(BaseModel):
    """Login with email or mobile number + password."""

    email: str | None = None
    mobile_number: str | None = None
    password: str

    @model_validator(mode="after")
    def require_email_or_mobile(self) -> "LoginRequest":
        if not self.email and not self.mobile_number:
            raise ValueError("Either email or mobile_number is required")
        return self


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

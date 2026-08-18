"""
Auth request/response schemas.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LoginRequest(BaseModel):
    """
    Login with email or mobile number + password.

    FT-010: `extra="forbid"` is deliberate. The web client previously sent
    `mobile` instead of `mobile_number`; with the default `ignore` behaviour
    pydantic silently discarded it and the request failed as "no identity
    supplied" for reasons invisible to the caller. Rejecting unknown keys turns
    a silent contract mismatch into an explicit 422.
    """

    model_config = ConfigDict(extra="forbid")

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


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    email: str
    otp: str
    new_password: str = Field(min_length=8, max_length=128)

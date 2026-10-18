"""
Auth request/response schemas.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LoginRequest(BaseModel):
    """
    Login with email, mobile number, or unified identifier + password.
    """

    model_config = ConfigDict(extra="forbid")

    identifier: str | None = Field(default=None, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    mobile_number: str | None = Field(default=None, max_length=255)
    password: str = Field(max_length=128)

    @model_validator(mode="after")
    def resolve_identity(self) -> "LoginRequest":
        if self.identifier:
            cleaned = self.identifier.strip()
            if "@" in cleaned:
                self.email = cleaned
            else:
                self.mobile_number = cleaned

        if not self.email and not self.mobile_number:
            raise ValueError("Either email, mobile_number, or identifier is required")
        return self


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    # True when the account still has a temporary/default password. Clients must send the
    # user to the change-password screen; with ENFORCE_PASSWORD_CHANGE the server also
    # answers 403 PASSWORD_CHANGE_REQUIRED on every other endpoint until it is changed.
    must_change_password: bool = False


class RefreshRequest(BaseModel):
    refresh_token: str | None = Field(default=None, max_length=512)


class ForgotPasswordRequest(BaseModel):
    identifier: str | None = Field(default=None, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    mobile_number: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def resolve_identifier(self) -> "ForgotPasswordRequest":
        if self.identifier:
            cleaned = self.identifier.strip()
            if "@" in cleaned:
                self.email = cleaned
            else:
                self.mobile_number = cleaned

        if not self.email and not self.mobile_number:
            raise ValueError("Either email, mobile_number, or identifier is required")
        return self


class ForgotPasswordResponse(BaseModel):
    message: str
    destination: str | None = None
    delivery_channel: str | None = None


class VerifyOtpRequest(BaseModel):
    identifier: str | None = Field(default=None, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    mobile_number: str | None = Field(default=None, max_length=255)
    otp: str = Field(min_length=6, max_length=8)

    @model_validator(mode="after")
    def resolve_identifier(self) -> "VerifyOtpRequest":
        if self.identifier:
            cleaned = self.identifier.strip()
            if "@" in cleaned:
                self.email = cleaned
            else:
                self.mobile_number = cleaned

        if not self.email and not self.mobile_number:
            raise ValueError("Either email, mobile_number, or identifier is required")
        return self


class VerifyOtpResponse(BaseModel):
    valid: bool = True
    message: str = "Code verified successfully"


class ResetPasswordRequest(BaseModel):
    identifier: str | None = Field(default=None, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    mobile_number: str | None = Field(default=None, max_length=255)
    otp: str = Field(min_length=6, max_length=8)
    new_password: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def resolve_identifier(self) -> "ResetPasswordRequest":
        if self.identifier:
            cleaned = self.identifier.strip()
            if "@" in cleaned:
                self.email = cleaned
            else:
                self.mobile_number = cleaned

        if not self.email and not self.mobile_number:
            raise ValueError("Either email, mobile_number, or identifier is required")
        return self

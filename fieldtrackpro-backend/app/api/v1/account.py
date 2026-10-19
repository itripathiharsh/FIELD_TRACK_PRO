"""
Account router — self-service account deletion.

Lives in its own module (instead of auth.py) and is mounted with the /auth
prefix so the path is DELETE /api/v1/auth/me, next to GET /api/v1/auth/me.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps.auth import CurrentUser
from app.database import get_async_session
from app.services import account_deletion_service

router = APIRouter(prefix="/auth", tags=["auth"])

DbSession = Annotated[AsyncSession, Depends(get_async_session)]


class DeleteAccountRequest(BaseModel):
    # Required re-authentication step: a destructive, irreversible action
    # taken from an already-logged-in session (e.g. an unlocked phone left
    # unattended) must not be one tap away with no further proof of identity.
    password: str = Field(min_length=1, max_length=255)
    reason: str | None = Field(default=None, max_length=500)


class DeleteAccountResponse(BaseModel):
    status: str
    message: str


@router.delete("/me", response_model=DeleteAccountResponse, summary="Delete my account")
async def delete_my_account(
    response: Response,
    current_user: CurrentUser,
    session: DbSession,
    payload: DeleteAccountRequest = Body(...),
) -> DeleteAccountResponse:
    """
    Deactivate the caller's account, revoke all sessions/devices and anonymise
    personal data. Visits, payments, invoices and audit records are retained
    (financial/legal retention); the employee's own visit photos/signatures
    are deleted from storage. Requires re-entering the current password. The
    last active ADMIN cannot delete itself.
    """
    await account_deletion_service.delete_own_account(
        current_user, payload.reason, payload.password, session
    )
    from app.api.v1.auth import _clear_refresh_cookie  # same pattern as users.py (avoids a router import cycle)

    _clear_refresh_cookie(response)
    return DeleteAccountResponse(
        status="DELETED",
        message=(
            "Your account has been deleted. Personal data was removed; "
            "business and financial records are retained as required by law."
        ),
    )

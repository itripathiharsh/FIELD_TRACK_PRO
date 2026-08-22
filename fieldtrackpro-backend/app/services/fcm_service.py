from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.services.device_service import device_service

logger = logging.getLogger("fieldtrackpro")

# Error codes and exception classes indicating a token is permanently invalid or expired
UNREGISTERED_ERROR_CODES = {
    "registration-token-not-registered",
    "invalid-registration-token",
    "invalid-argument",
    "mismatched-credential",
}


class FCMService:
    """
    Firebase Cloud Messaging (FCM) push notification delivery service.
    Handles message formatting, multi-device delivery, dry-run fallback, and stale token pruning.
    """

    def __init__(self) -> None:
        self._initialized = False
        self._init_attempted = False

    def _ensure_firebase_app(self) -> bool:
        """
        Lazily initialize the Firebase Admin SDK singleton.
        Returns True if Firebase is initialized and ready to send, False otherwise.
        """
        if self._initialized:
            return True
        if self._init_attempted:
            return self._initialized

        self._init_attempted = True

        try:
            import firebase_admin
            from firebase_admin import credentials

            if firebase_admin._apps:
                self._initialized = True
                return True

            cred_path = settings.firebase_credentials_path or os.environ.get(
                "GOOGLE_APPLICATION_CREDENTIALS", ""
            )

            if cred_path and os.path.isfile(cred_path):
                cred = credentials.Certificate(cred_path)
                firebase_admin.initialize_app(cred)
                self._initialized = True
                logger.info(f"Firebase Admin SDK initialized successfully with credentials from {cred_path}")
            else:
                # In dev/test environments without credentials, log and operate in dry-run mode
                logger.info(
                    "FCM credentials not configured (FIREBASE_CREDENTIALS_PATH / GOOGLE_APPLICATION_CREDENTIALS). "
                    "Push notifications will operate in mock/dry-run mode."
                )
                self._initialized = False
        except Exception as e:
            logger.warning(f"Failed to initialize Firebase Admin SDK: {e}. Push notifications will operate in dry-run mode.")
            self._initialized = False

        return self._initialized

    async def send_multicast(
        self,
        tokens: Sequence[str],
        title: str,
        body: str,
        data: dict[str, Any] | None = None,
    ) -> tuple[int, int, list[str]]:
        """
        Send a push notification to multiple device tokens via FCM.
        Returns (success_count, failure_count, invalid_tokens).
        """
        if not tokens:
            return 0, 0, []

        valid_tokens = [t.strip() for t in tokens if t and t.strip()]
        if not valid_tokens:
            return 0, 0, []

        # Convert data dictionary to string values only (required by FCM specification)
        string_data: dict[str, str] = {}
        if data:
            for k, v in data.items():
                if v is not None:
                    string_data[str(k)] = str(v)

        if not self._ensure_firebase_app():
            # Dry-run / mock mode for local dev or tests
            logger.info(
                f"[FCM DRY-RUN] Would send push to {len(valid_tokens)} device(s): "
                f"title='{title}', body='{body}', data={string_data}"
            )
            return len(valid_tokens), 0, []

        try:
            from firebase_admin import exceptions, messaging

            android_config = messaging.AndroidConfig(
                priority="high",
                notification=messaging.AndroidNotification(
                    channel_id="fieldtrack_visits",
                    default_sound=True,
                    click_action="FLUTTER_NOTIFICATION_CLICK",
                ),
            )

            message = messaging.MulticastMessage(
                tokens=valid_tokens,
                notification=messaging.Notification(
                    title=title,
                    body=body,
                ),
                data=string_data,
                android=android_config,
            )

            # send_each_for_multicast is the recommended batch method in modern firebase-admin
            batch_response: messaging.BatchResponse = messaging.send_each_for_multicast(message)

            success_count = batch_response.success_count
            failure_count = batch_response.failure_count
            invalid_tokens: list[str] = []

            for idx, resp in enumerate(batch_response.responses):
                if not resp.success:
                    token = valid_tokens[idx]
                    err = resp.exception
                    error_code = getattr(err, "code", "") or str(err)
                    logger.warning(f"FCM delivery failure for token prefix {token[:12]}...: {err}")

                    # Check if the error indicates an unregistered / dead token
                    is_unregistered = (
                        isinstance(
                            err,
                            (
                                exceptions.InvalidArgumentError,
                                messaging.UnregisteredError,
                                messaging.SenderIdMismatchError,
                            ),
                        )
                        or any(code in str(error_code).lower() for code in UNREGISTERED_ERROR_CODES)
                    )

                    if is_unregistered:
                        invalid_tokens.append(token)

            logger.info(
                f"FCM push results: {success_count} succeeded, {failure_count} failed, "
                f"{len(invalid_tokens)} stale tokens identified"
            )
            return success_count, failure_count, invalid_tokens

        except Exception as e:
            logger.error(f"Unexpected error executing FCM push multicast: {e}", exc_info=True)
            return 0, len(valid_tokens), []

    async def send_to_user(
        self,
        user_id: uuid.UUID,
        title: str,
        body: str,
        data: dict[str, Any] | None = None,
        session: AsyncSession = None,
    ) -> int:
        """
        Send a push notification to all active devices registered for a user.
        Automatically deactivates invalid/expired tokens.
        """
        if session is None:
            logger.warning("send_to_user called without session; cannot fetch device tokens")
            return 0

        try:
            tokens = await device_service.get_active_tokens_for_user(user_id, session)
            if not tokens:
                logger.debug(f"No active device tokens found for user={user_id}. Skipping push notification.")
                return 0

            success_count, _, invalid_tokens = await self.send_multicast(
                tokens=tokens,
                title=title,
                body=body,
                data=data,
            )

            # Automatically prune invalid/expired tokens
            if invalid_tokens:
                await device_service.deactivate_stale_tokens(invalid_tokens, session)

            return success_count
        except Exception as e:
            # Shield business operations from push delivery failures
            logger.error(f"Failed to deliver FCM push notification to user {user_id}: {e}", exc_info=True)
            return 0


fcm_service = FCMService()

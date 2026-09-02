import asyncio
import logging
import smtplib
from email.message import EmailMessage

from app.config import settings
from app.services.sms_service import mask_email

logger = logging.getLogger(__name__)


def _send_smtp_email(email: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg.set_content(body)
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from_email
    msg["To"] = email

    masked = mask_email(email)
    logger.info("Connecting to SMTP server at %s:%s...", settings.smtp_host, settings.smtp_port)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
            server.ehlo()
            if settings.smtp_port == 587:
                server.starttls()
            if settings.smtp_user and settings.smtp_password:
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
            logger.info("Password reset email delivered successfully to %s", masked)
    except Exception as e:
        logger.error("Failed to send email to %s (error: %s)", masked, type(e).__name__)
        raise


async def send_password_reset_email(email: str, otp: str) -> None:
    """
    Sends the password reset email.
    If SMTP_HOST is configured, it sends via SMTP asynchronously.
    Otherwise, in development/debug mode, it prints the code for testing.
    In production without SMTP_HOST, it fails safely without leaking OTP.
    """
    subject = "FieldTrack Pro - Password Reset Code"
    body = f"""
Hello,

You have requested to reset your password for FieldTrack Pro.
Your 6-digit password reset code is: {otp}

This code will expire in 15 minutes and can only be used once.
If you did not request this, you can safely ignore this email.

Regards,
FieldTrack Pro Team
    """

    masked = mask_email(email)

    if settings.smtp_host:
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, _send_smtp_email, email, subject, body)
        except Exception:
            # Error already logged with masked email without exposing OTP
            pass
    else:
        # Production safety guard: Never log or print OTP if not strictly in dev/test environment
        if settings.environment == "production":
            logger.error("SMTP_HOST not configured in production environment. Email delivery aborted for %s", masked)
            return

        logger.info("[MOCK EMAIL] Dispatched security code to %s", masked)
        if settings.environment in ("dev", "test") and settings.debug:
            print(
                f"\n=======================================================\n"
                f"[DEV EMAIL] Password Reset OTP for {email}: {otp}\n"
                f"=======================================================\n",
                flush=True,
            )

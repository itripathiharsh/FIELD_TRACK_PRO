import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.config import settings
from app.services.sms_service import mask_email

logger = logging.getLogger(__name__)


class SmtpInsecureError(RuntimeError):
    """Raised instead of sending SMTP credentials over an unencrypted connection."""


def _insecure_allowed() -> bool:
    # Never in production, whatever SMTP_ALLOW_INSECURE says.
    return bool(settings.smtp_allow_insecure) and settings.environment != "production"


def _send_smtp_email(email: str, subject: str, body: str) -> None:
    """
    Deliver one message. Transport rules:
      * port 465 -> implicit TLS (SMTP_SSL);
      * any other port -> plain connect, then STARTTLS whenever the server advertises it
        (587 / 2525 / 25 ...), re-issuing EHLO afterwards;
      * credentials are NEVER sent over an unencrypted channel unless SMTP_ALLOW_INSECURE=true
        (dev only; ignored in production). A refusal is logged and the send is skipped.
    Failures are logged (masked address, exception class only - no secrets, no OTP) and
    re-raised to the caller, which swallows them so the API response never changes.
    """
    msg = EmailMessage()
    msg.set_content(body)
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from_email
    msg["To"] = email

    masked = mask_email(email)
    host, port = settings.smtp_host, settings.smtp_port
    has_credentials = bool(settings.smtp_user and settings.smtp_password)
    logger.info("Connecting to SMTP server at %s:%s...", host, port)
    try:
        context = ssl.create_default_context()
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=10, context=context)
            encrypted = True
        else:
            server = smtplib.SMTP(host, port, timeout=10)
            encrypted = False
        with server:
            server.ehlo()
            if not encrypted and server.has_extn("starttls"):
                server.starttls(context=context)
                server.ehlo()
                encrypted = True
            if has_credentials:
                if not encrypted and not _insecure_allowed():
                    raise SmtpInsecureError(
                        "refusing to send SMTP credentials without TLS (use port 465/587 with STARTTLS, "
                        "or set SMTP_ALLOW_INSECURE=true in development)"
                    )
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
            logger.info("Password reset email delivered successfully to %s", masked)
    except Exception as e:
        logger.error(
            "event=smtp_delivery_failed to=%s smtp=%s:%s error=%s%s",
            masked,
            host,
            port,
            type(e).__name__,
            f" ({e})" if isinstance(e, SmtpInsecureError) else "",
        )
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
        if settings.environment in ("dev", "test") and settings.debug and settings.dev_print_otp:
            print(
                f"\n=======================================================\n"
                f"[DEV EMAIL] Password Reset OTP for {email}: {otp}\n"
                f"=======================================================\n",
                flush=True,
            )

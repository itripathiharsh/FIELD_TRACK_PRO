import logging
import smtplib
from email.message import EmailMessage
import asyncio
from app.config import settings

logger = logging.getLogger(__name__)

def _send_smtp_email(email: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg.set_content(body)
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from_email
    msg["To"] = email

    logger.info(f"Connecting to SMTP server at {settings.smtp_host}:{settings.smtp_port}...")
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
            server.ehlo()
            if settings.smtp_port == 587:
                server.starttls()
            if settings.smtp_user and settings.smtp_password:
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
            logger.info(f"Email sent successfully to {email}")
    except Exception as e:
        logger.error(f"Failed to send email to {email}: {e}")
        raise

async def send_password_reset_email(email: str, otp: str) -> None:
    """
    Sends the password reset email.
    If SMTP_HOST is configured, it sends via SMTP asynchronously.
    Otherwise, it logs the mock email for local development.
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

    if settings.smtp_host:
        loop = asyncio.get_running_loop()
        # Run the blocking SMTP operation in a thread pool
        await loop.run_in_executor(None, _send_smtp_email, email, subject, body)
    else:
        logger.info(f"Mock Email sent to {email}. Subject: {subject}. Body: {otp}")
        print(f"\n=======================================================\n[DEV EMAIL] Password Reset OTP for {email}: {otp}\n=======================================================\n", flush=True)

"""
SMS Service: Isolated provider abstraction for sending transactional SMS / OTPs.
Providers supported: Mock, MSG91, Twilio, Fast2SMS.
Configured via app.config.settings.
"""
from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def mask_mobile(mobile: str) -> str:
    """Mask mobile number for secure UI display (e.g. '9839011014' -> '******1014')."""
    clean = re.sub(r"[^\d+]", "", str(mobile).strip())
    if len(clean) >= 4:
        return f"{'*' * (len(clean) - 4)}{clean[-4:]}"
    return "****"


def mask_email(email: str) -> str:
    """Mask email for secure UI display (e.g. 'deepak.soni@sgrgservices.com' -> 'd*****@sgrgservices.com')."""
    clean = str(email).strip().lower()
    if "@" not in clean:
        return "***@***"
    local, domain = clean.split("@", 1)
    if len(local) <= 2:
        masked_local = f"{local[0]}*" if local else "*"
    else:
        masked_local = f"{local[0]}{'*' * (len(local) - 2)}{local[-1]}"
    return f"{masked_local}@{domain}"


class BaseSmsProvider(ABC):
    @abstractmethod
    async def send_sms(self, mobile_number: str, message: str, otp: Optional[str] = None) -> bool:
        pass


class MockSmsProvider(BaseSmsProvider):
    async def send_sms(self, mobile_number: str, message: str, otp: Optional[str] = None) -> bool:
        masked = mask_mobile(mobile_number)
        if settings.environment == "production":
            logger.error("MockSmsProvider cannot be used when ENVIRONMENT=production. SMS delivery aborted for %s", masked)
            return False

        logger.info("[MOCK SMS] Dispatched security code to %s", masked)
        if settings.environment in ("dev", "test") and settings.debug:
            print(
                f"\n=======================================================\n"
                f"[DEV SMS] Password Reset OTP for {mobile_number}: {otp}\n"
                f"=======================================================\n",
                flush=True,
            )
        return True


class Msg91SmsProvider(BaseSmsProvider):
    async def send_sms(self, mobile_number: str, message: str, otp: Optional[str] = None) -> bool:
        masked = mask_mobile(mobile_number)
        if not settings.sms_api_key:
            logger.error("MSG91 SMS failed: sms_api_key is not configured")
            return False

        clean_mobile = re.sub(r"[^\d]", "", mobile_number)
        if len(clean_mobile) == 10:
            clean_mobile = f"91{clean_mobile}"

        url = "https://control.msg91.com/api/v5/otp"
        headers = {
            "authkey": settings.sms_api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "template_id": settings.sms_template_id or "",
            "mobile": clean_mobile,
            "otp": otp,
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code == 200:
                    logger.info("MSG91 SMS sent successfully to %s", masked)
                    return True
                logger.error("MSG91 SMS delivery rejected: HTTP status %s", resp.status_code)
                return False
        except Exception as exc:
            logger.error("MSG91 SMS request exception: %s", type(exc).__name__)
            return False


class TwilioSmsProvider(BaseSmsProvider):
    async def send_sms(self, mobile_number: str, message: str, otp: Optional[str] = None) -> bool:
        masked = mask_mobile(mobile_number)
        sid = settings.twilio_account_sid
        token = settings.twilio_auth_token
        from_num = settings.twilio_from_number
        if not sid or not token or not from_num:
            logger.error("Twilio SMS failed: Twilio credentials not configured")
            return False

        clean_mobile = mobile_number.strip()
        if not clean_mobile.startswith("+"):
            clean_mobile = f"+91{clean_mobile.lstrip('0')}" if len(clean_mobile) == 10 else f"+{clean_mobile}"

        url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
        data = {
            "To": clean_mobile,
            "From": from_num,
            "Body": message,
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, data=data, auth=(sid, token))
                if resp.status_code in (200, 201):
                    logger.info("Twilio SMS sent successfully to %s", masked)
                    return True
                logger.error("Twilio SMS delivery rejected: HTTP status %s", resp.status_code)
                return False
        except Exception as exc:
            logger.error("Twilio SMS request exception: %s", type(exc).__name__)
            return False


class Fast2SmsProvider(BaseSmsProvider):
    async def send_sms(self, mobile_number: str, message: str, otp: Optional[str] = None) -> bool:
        masked = mask_mobile(mobile_number)
        if not settings.sms_api_key:
            logger.error("Fast2SMS failed: sms_api_key is not configured")
            return False

        clean_mobile = re.sub(r"[^\d]", "", mobile_number)
        if len(clean_mobile) > 10:
            clean_mobile = clean_mobile[-10:]

        url = "https://www.fast2sms.com/dev/bulkV2"
        headers = {
            "authorization": settings.sms_api_key,
        }
        payload = {
            "route": "otp" if otp else "q",
            "variables_values": otp if otp else message,
            "numbers": clean_mobile,
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, data=payload, headers=headers)
                if resp.status_code == 200:
                    logger.info("Fast2SMS sent successfully to %s", masked)
                    return True
                logger.error("Fast2SMS delivery rejected: HTTP status %s", resp.status_code)
                return False
        except Exception as exc:
            logger.error("Fast2SMS request exception: %s", type(exc).__name__)
            return False


def get_sms_provider() -> BaseSmsProvider:
    provider = (settings.sms_provider or "mock").strip().lower()
    if provider == "msg91":
        return Msg91SmsProvider()
    if provider == "twilio":
        return TwilioSmsProvider()
    if provider == "fast2sms":
        return Fast2SmsProvider()
    return MockSmsProvider()


async def send_password_reset_sms(mobile_number: str, otp: str) -> bool:
    """
    Sends a 6-digit password reset OTP to the registered mobile number via configured SMS provider.
    Fails safely without exposing plaintext OTP in logs or exceptions.
    """
    message = (
        f"Your FieldTrack Pro password reset security code is {otp}. "
        f"Valid for 15 minutes. Do not share this OTP with anyone."
    )
    provider = get_sms_provider()
    try:
        return await provider.send_sms(mobile_number=mobile_number, message=message, otp=otp)
    except Exception as exc:
        logger.error("SMS dispatch failure for %s: %s", mask_mobile(mobile_number), type(exc).__name__)
        return False

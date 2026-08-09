"""
Shared validation constants and patterns for phone/contact fields.

Centralizes phone-number validation rules so that customer.contact_number,
user.mobile_number, and any future phone fields share one authoritative
definition and cannot drift apart.

Accepted format:
  - Digits 0-9
  - Plus sign (+) for international prefix
  - Hyphens (-) as visual separators
  - Spaces as visual separators
  - Parentheses () for area codes
  - Length: 1 to PHONE_MAX_LENGTH characters

Rejected:
  - Alphabetic characters
  - Symbols such as @, #, $, %, etc.
  - Values exceeding PHONE_MAX_LENGTH characters
"""
from __future__ import annotations

PHONE_MAX_LENGTH: int = 20

# Regex: only digits, +, -, spaces, parentheses. 1 to PHONE_MAX_LENGTH chars.
# Examples accepted: +919876543210, +1 555-123-4567, 1234567890, (555) 123-4567
# Examples rejected: ABCDEREZ@, hello, 123abc, !@#$%^&*
PHONE_PATTERN: str = r"^[\d+\-\s\(\)]{1,20}$"


def is_valid_phone(value: str | None) -> bool:
    """Return True if value matches the phone pattern. None is valid (optional field)."""
    if value is None:
        return True
    import re
    return bool(re.match(PHONE_PATTERN, value))

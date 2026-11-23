import logging
import re
import sys
from pathlib import Path
from typing import Any

from tally_sync_agent.config.settings import settings

# Sensitive token patterns to redact
REDACT_PATTERNS = [
    (re.compile(r'(["\']?agent_key["\']?\s*[:=]\s*["\'])([^"\']+)(["\'])', re.IGNORECASE), r'\1[REDACTED]\3'),
    (re.compile(r'(["\']?password["\']?\s*[:=]\s*["\'])([^"\']+)(["\'])', re.IGNORECASE), r'\1[REDACTED]\3'),
    (re.compile(r'(["\']?token["\']?\s*[:=]\s*["\'])([^"\']+)(["\'])', re.IGNORECASE), r'\1[REDACTED]\3'),
    (re.compile(r'(X-Agent-Key\s*[:=]\s*)([^\s,]+)', re.IGNORECASE), r'\1[REDACTED]'),
]


class SanitizedFormatter(logging.Formatter):
    """Formatter that strips out sensitive keys/tokens from logs."""
    
    def format(self, record: logging.LogRecord) -> str:
        orig = super().format(record)
        sanitized = orig
        for pattern, repl in REDACT_PATTERNS:
            sanitized = pattern.sub(repl, sanitized)
        return sanitized


def get_logger(name: str = "tally_sync_agent") -> logging.Logger:
    """Configures and returns a structured, sanitized logger."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
        
    logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    formatter = SanitizedFormatter(
        fmt="[%(asctime)s] [%(levelname)s] [%(name)s] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    
    # Console output handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File output handler
    try:
        settings.log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(settings.log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception:
        pass
        
    return logger


logger = get_logger()

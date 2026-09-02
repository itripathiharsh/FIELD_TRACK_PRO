import logging
import sys

from app.core.context import get_current_request_id


class RequestIdLogFilter(logging.Filter):
    """Injects the active correlation request_id into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        req_id = get_current_request_id()
        record.request_id = req_id if req_id else "-"
        return True


def setup_logging(environment: str = "dev") -> logging.Logger:
    log_level = logging.DEBUG if environment == "dev" else logging.INFO

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] [req:%(request_id)s] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.addFilter(RequestIdLogFilter())

    logger = logging.getLogger("fieldtrackpro")
    logger.setLevel(log_level)

    if not logger.handlers:
        logger.addHandler(handler)

    return logger

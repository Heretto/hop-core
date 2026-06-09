"""Structured logging configuration."""

import logging
import sys
from typing import Any, Dict
import json
from datetime import datetime


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_obj: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        if hasattr(record, "extra"):
            log_obj.update(record.extra)

        return json.dumps(log_obj)


def setup_logging(level: str = "INFO", use_json: bool = False) -> None:
    """Configure structured logging.

    Args:
        level: Log level name.
        use_json: Use JSON formatter (typically True in production).
    """
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    if use_json:
        formatter = JSONFormatter()
        for handler in logging.root.handlers:
            handler.setFormatter(formatter)

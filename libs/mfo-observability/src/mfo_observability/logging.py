"""Structured JSON logging configuration.

Provides a JSON log formatter that automatically enriches every record with the current
correlation ID, and a helper to install it on the root logger.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

from mfo_observability.correlation import get_correlation_id

# Standard ``LogRecord`` attributes that must not be duplicated into the JSON "extra" section.
_RESERVED_RECORD_KEYS = frozenset(
    logging.makeLogRecord({}).__dict__.keys() | {"message", "asctime"}
)


class JsonFormatter(logging.Formatter):
    """Format log records as single-line JSON objects.

    Each record includes the timestamp, level, logger name, message, the current correlation ID
    (when present), and any structured fields passed through the logging ``extra`` argument.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Render a log record as a JSON string.

        Args:
            record: The log record to serialize.

        Returns:
            A JSON-encoded representation of the record on a single line.
        """
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        correlation_id = get_correlation_id()
        if correlation_id is not None:
            payload["correlationId"] = correlation_id
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        # Merge user-supplied structured fields provided via ``logger.info(..., extra={...})``.
        for key, value in record.__dict__.items():
            if key not in _RESERVED_RECORD_KEYS:
                payload[key] = value
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    """Install the JSON formatter on the root logger.

    Existing handlers are removed so log output is not duplicated when the function is called more
    than once (for example, in tests).

    Args:
        level: The minimum log level for the root logger.
    """
    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):
        root.removeHandler(handler)
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)

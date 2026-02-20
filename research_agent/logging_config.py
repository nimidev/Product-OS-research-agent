"""Structured JSON logging configuration."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = self.formatException(record.exc_info)
        for key in ("item_id", "source", "error_type", "query", "duration_ms", "count"):
            val = getattr(record, key, None)
            if val is not None:
                log_entry[key] = val
        return json.dumps(log_entry)


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    if root.handlers:
        root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root.addHandler(handler)

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

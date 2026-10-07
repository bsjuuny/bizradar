"""Structured JSON logging for the worker (docs/INFRASTRUCTURE.md, section 36 of the
original spec): timestamp, level, message, plus whatever job-specific fields a call
site passes via `extra=` (job, source, external_id, duration, status, error, ...).
Never log secrets - callers are responsible for not putting them in `extra`; API keys in
query strings are additionally redacted from every line (redact_secrets).
"""

from __future__ import annotations

import json
import logging
import re
import sys

_RESERVED_RECORD_FIELDS = frozenset(vars(logging.LogRecord("", 0, "", 0, "", (), None)).keys()) | {
    "message",
    "asctime",
}

# API keys that travel in query strings. They reach log lines through URLs quoted in
# exception text (httpx HTTPStatusError: "... for url 'https://...?serviceKey=...'") and
# any message that echoes a request. Redacted on the final line, so message, extras and
# traceback are all covered no matter which call site produced them.
_SECRET_QUERY_PARAM = re.compile(r"((?:serviceKey|crtfcKey)=)[^&\s\"'\\]+", re.IGNORECASE)


def redact_secrets(text: str) -> str:
    return _SECRET_QUERY_PARAM.sub(r"\1<redacted>", text)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": self.formatTime(record, "%Y-%m-%d %H:%M:%S"),
            "level": record.levelname,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["error"] = self.formatException(record.exc_info)

        for key, value in record.__dict__.items():
            if key not in _RESERVED_RECORD_FIELDS and key not in payload:
                payload[key] = value

        return redact_secrets(json.dumps(payload, ensure_ascii=False, default=str))


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = [handler]

    # httpx logs every request URL at INFO, and the worker's API keys travel in the query
    # string (data.go.kr serviceKey, 기업마당 crtfcKey) - found 2026-10-07 in the PM2 out
    # log, in plain text. It is also most of that log's volume (every Supabase call).
    # Failures still surface: collectors log their own warnings, httpx WARNING+ passes.
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(max(level, logging.WARNING))

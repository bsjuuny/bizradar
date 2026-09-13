"""Minimal Telegram Bot API sender for the Watch digest (worker/jobs/digest_job.py).
No SDK - a bot's sendMessage is a single POST, not worth a dependency for.
"""

from __future__ import annotations

import contextlib
import logging

import httpx

from worker.config import get_settings

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org"
REQUEST_TIMEOUT_SECONDS = 15.0


def send_telegram_message(chat_id: str, text: str) -> bool:
    """Best-effort send. Returns False (never raises) on missing config or a failed
    request, so a delivery failure for one company never blocks the rest of the
    digest job (same failure-isolation principle as worker/jobs/match_job.py)."""
    settings = get_settings()
    if not settings.telegram_bot_token:
        logger.warning("telegram: TELEGRAM_BOT_TOKEN not configured, skipping send")
        return False

    url = f"{TELEGRAM_API_BASE}/bot{settings.telegram_bot_token}/sendMessage"
    try:
        response = httpx.post(
            url,
            # No parse_mode: the digest embeds opportunity titles/organization names,
            # which are arbitrary third-party text (raw_payload from G2B) - Telegram's
            # Markdown parser 400s the whole send on an unescaped `*_[]` etc., and
            # correctly escaping MarkdownV2 for text we don't control isn't worth it
            # for a plain-text digest. Plain text always sends.
            json={
                "chat_id": chat_id,
                "text": text,
                "disable_web_page_preview": True,
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return True
    except httpx.HTTPStatusError as exc:
        # str(exc) embeds the full request URL, which contains the bot token
        # (https://api.telegram.org/bot<TOKEN>/sendMessage) - worker/logging_config.py
        # says never log secrets, so pull out only the status code and Telegram's own
        # (token-free) error description instead of logging the exception itself.
        # chat_id is a Telegram user identifier (personal data, see docs/PRIVACY.md) -
        # not logged here either; the caller (worker/jobs/digest_job.py) logs its own
        # internal company_id instead if it needs to correlate a failure.
        detail = None
        with contextlib.suppress(Exception):
            detail = exc.response.json().get("description")
        logger.warning(
            "telegram: send failed",
            extra={"status_code": exc.response.status_code, "detail": detail},
        )
        return False
    except httpx.HTTPError as exc:
        # Network-level failures (timeout, connection error) - httpx does not embed
        # the request URL in these, unlike HTTPStatusError above.
        logger.warning("telegram: send failed", extra={"error": str(exc)})
        return False

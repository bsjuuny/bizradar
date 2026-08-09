"""Bounded HTTP retry and an in-process source circuit breaker."""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime

import httpx

from worker.collectors.base import CollectorError

logger = logging.getLogger(__name__)
RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


def _retry_after_seconds(value: str | None, now: datetime | None = None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, min(float(value), 60.0))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
            current = now or datetime.now(UTC)
            return max(0.0, min((parsed - current).total_seconds(), 60.0))
        except (TypeError, ValueError, OverflowError):
            return None


def get_text_with_retry(
    client: httpx.Client,
    url: str,
    *,
    params: dict[str, str | int] | None,
    source: str,
    max_retries: int,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            response = client.get(url, params=params, follow_redirects=True)
            if response.status_code in {403, 404}:
                raise CollectorError(f"{source} HTTP {response.status_code}; retry disabled")
            if response.status_code in RETRYABLE_STATUS:
                response.raise_for_status()
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if "html" not in content_type.lower():
                raise CollectorError(
                    f"{source} unexpected content type: {content_type or 'missing'}"
                )
            if not response.text.strip():
                raise CollectorError(f"{source} returned an empty response")
            return response.text
        except CollectorError:
            raise
        except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as exc:
            last_error = exc
            status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
            if status is not None and status not in RETRYABLE_STATUS:
                raise CollectorError(f"{source} HTTP {status}; retry disabled") from exc
            if attempt >= max_retries:
                break
            retry_after = (
                _retry_after_seconds(exc.response.headers.get("retry-after"))
                if isinstance(exc, httpx.HTTPStatusError) and status == 429
                else None
            )
            delay = (
                retry_after if retry_after is not None else (2**attempt + random.uniform(0, 0.25))
            )
            logger.warning(
                "challenge source request retrying",
                extra={
                    "source": source,
                    "url": url,
                    "status": status,
                    "retry_count": attempt + 1,
                    "error_code": type(exc).__name__,
                },
            )
            sleep(delay)
    raise CollectorError(
        f"{source} request failed after {max_retries + 1} attempts: {last_error}"
    ) from last_error


@dataclass
class _CircuitState:
    failures: int = 0
    disabled_until: datetime | None = None


class SourceCircuitBreaker:
    def __init__(self, threshold: int = 3, cooldown: timedelta = timedelta(minutes=15)) -> None:
        self.threshold = threshold
        self.cooldown = cooldown
        self._states: dict[str, _CircuitState] = {}

    def allow(self, source: str, *, now: datetime | None = None) -> bool:
        current = now or datetime.now(UTC)
        state = self._states.setdefault(source, _CircuitState())
        if state.disabled_until and current < state.disabled_until:
            return False
        if state.disabled_until and current >= state.disabled_until:
            state.failures = 0
            state.disabled_until = None
        return True

    def success(self, source: str) -> None:
        self._states[source] = _CircuitState()

    def failure(self, source: str, *, now: datetime | None = None) -> None:
        current = now or datetime.now(UTC)
        state = self._states.setdefault(source, _CircuitState())
        state.failures += 1
        if state.failures >= self.threshold:
            state.disabled_until = current + self.cooldown


challenge_circuit_breaker = SourceCircuitBreaker()

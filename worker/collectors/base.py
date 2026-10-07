"""Collector interface shared by every public-data source (G2B, BizInfo, K-Startup, ...).

A collector's run() is a template method: collect() may fail as a whole (network down,
rate limited) and that failure must not crash the scheduler - the caller decides whether
to retry or skip this cycle. Per-record failures inside normalize/validate/persist must
not abort the rest of the batch, so they are caught and reported in CollectorRunResult
instead of raised.
"""

from __future__ import annotations

import hashlib
import html
import json
import logging
import re
from abc import ABC, abstractmethod
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)

_ENTITY = re.compile(r"&(?:#\d+|#[xX][0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]*);")


def compute_content_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def decode_entities(text: str) -> str:
    """Decode HTML character references - only the ';'-terminated ones. html.unescape on
    its own also expands legacy references with no ';' (HTML5 parsing rules), so it turns
    a query string like "?schM=view&notice=1" into "?schM=view¬ice=1"."""
    return _ENTITY.sub(lambda match: html.unescape(match.group()), text)


class CollectorError(Exception):
    """Raised when an entire collection run fails (e.g. source unreachable)."""


class RawRecord(BaseModel):
    source: str
    external_id: str
    fetched_at: datetime
    payload: dict[str, Any]


class CollectorRunResult(BaseModel):
    source: str
    collected: int = 0
    persisted: int = 0
    failed: int = 0
    errors: list[str] = []


class BaseCollector[TNormalized: BaseModel](ABC):
    """Subclass per data source. See G2BCollector / BizInfoCollector / KStartupCollector."""

    source: str

    @abstractmethod
    def collect(self) -> Iterable[RawRecord]:
        """Fetch raw records from the upstream API. May raise CollectorError."""

    @abstractmethod
    def normalize(self, raw: RawRecord) -> TNormalized:
        """Convert a raw record into a source-specific normalized model."""

    @abstractmethod
    def validate(self, normalized: TNormalized) -> bool:
        """Return False to skip a record that failed validation (not an exception)."""

    @abstractmethod
    def persist(self, normalized: TNormalized) -> None:
        """Upsert the normalized record, keyed by (source, external_id) for idempotency."""

    def run(self) -> CollectorRunResult:
        result = CollectorRunResult(source=self.source)

        raw_records = self.collect()

        for raw in raw_records:
            result.collected += 1
            try:
                normalized = self.normalize(raw)
                if not self.validate(normalized):
                    result.failed += 1
                    result.errors.append(f"{raw.external_id}: validation failed")
                    continue
                self.persist(normalized)
                result.persisted += 1
            except Exception as exc:  # noqa: BLE001 - isolate per-record failures
                result.failed += 1
                result.errors.append(f"{raw.external_id}: {exc}")
                logger.warning(
                    "collector record failed",
                    extra={
                        "source": self.source,
                        "external_id": raw.external_id,
                        "error": str(exc),
                    },
                )

        return result

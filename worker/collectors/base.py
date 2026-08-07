"""Collector interface shared by every public-data source (G2B, BizInfo, K-Startup, ...).

A collector's run() is a template method: collect() may fail as a whole (network down,
rate limited) and that failure must not crash the scheduler - the caller decides whether
to retry or skip this cycle. Per-record failures inside normalize/validate/persist must
not abort the rest of the batch, so they are caught and reported in CollectorRunResult
instead of raised.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)


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

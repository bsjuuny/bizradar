"""Fault-isolated collection across all enabled Challenge sources."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from worker.challenges.models import ChallengeCollectionSummary
from worker.challenges.resilience import challenge_circuit_breaker
from worker.challenges.sources import CHALLENGE_SOURCES
from worker.collectors.data_go_kr_challenges import DataGoKrChallengeCollector
from worker.config import get_settings
from worker.repositories.challenges import record_source_status

logger = logging.getLogger(__name__)


def run(*, max_records: int | None = None) -> ChallengeCollectionSummary:
    started = datetime.now(UTC)
    settings = get_settings()
    summary = ChallengeCollectionSummary()
    if not settings.feature_challenge or not settings.challenge_collection_enabled:
        logger.info("challenge collection disabled", extra={"job": "challenge:collect"})
        return summary

    for source in (item for item in CHALLENGE_SOURCES if item.enabled):
        summary.sources += 1
        if not challenge_circuit_breaker.allow(source.source_id):
            summary.failed += 1
            summary.errors.append(f"{source.source_id}: circuit open")
            try:
                record_source_status(
                    source_id=source.source_id,
                    source_name=source.source_name,
                    status="TEMP_DISABLED",
                    fetched=0,
                    error="circuit open",
                )
            except Exception:
                logger.exception("failed to persist challenge source circuit status")
            continue
        try:
            with DataGoKrChallengeCollector(
                settings=settings, source_config=source, max_records=max_records
            ) as collector:
                result = collector.run()
            summary.success += 1
            summary.fetched += result.collected
            summary.persisted += result.persisted
            summary.skipped += result.failed
            summary.errors.extend(result.errors)
            challenge_circuit_breaker.success(source.source_id)
            try:
                record_source_status(
                    source_id=source.source_id,
                    source_name=source.source_name,
                    status="SUCCESS" if result.failed == 0 else "PARTIAL_SUCCESS",
                    fetched=result.collected,
                    error="; ".join(result.errors[:5]) or None,
                )
            except Exception:
                # Observability persistence must not turn a successful collection
                # into a source failure or reopen its circuit breaker.
                logger.exception("failed to persist challenge source success status")
        except Exception as exc:  # noqa: BLE001 - one source must not stop the others
            summary.failed += 1
            summary.errors.append(f"{source.source_id}: {exc}")
            challenge_circuit_breaker.failure(source.source_id)
            try:
                record_source_status(
                    source_id=source.source_id,
                    source_name=source.source_name,
                    status="FAILED",
                    fetched=0,
                    error=str(exc),
                )
            except Exception:
                logger.exception("failed to persist challenge source failure status")
            logger.exception(
                "challenge source failed; continuing remaining sources",
                extra={
                    "job": "challenge:collect",
                    "source": source.source_id,
                    "status": "failed",
                    "error_code": type(exc).__name__,
                },
            )

    summary.duration_seconds = (datetime.now(UTC) - started).total_seconds()
    logger.info(
        "Challenge Collection Completed",
        extra={
            "job": "challenge:collect",
            "status": summary.status,
            **summary.model_dump(exclude={"errors"}),
        },
    )
    return summary

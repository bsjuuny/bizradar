"""Scheduled Match Engine job. Deterministic and fast (no LLM - worker/matching/
engine.py), so unlike analyze_job this recomputes every company x every analyzed
opportunity on every run rather than batching. A total failure is caught and logged,
not raised - existing scores stay as they were, nothing else is blocked
(docs/DATA_PIPELINE.md#failure-isolation).

Only changed pairs are written, UPSERT_CHUNK_SIZE per request. Until 2026-10-15 every
pair was its own upsert: 2 companies x 2,949 opportunities = 5,898 requests every 15
minutes (~570k a day, ~97% of the worker's Supabase traffic), while ~95% of the scores
were unchanged - only schedule_score moves as deadlines approach."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from worker.matching.engine import MatchScore, compute_match_score
from worker.repositories.match_scores import (
    ScoreValues,
    get_analyzed_opportunities,
    get_companies_for_matching,
    get_existing_scores,
    score_values,
    upsert_match_scores,
)

logger = logging.getLogger(__name__)

UPSERT_CHUNK_SIZE = 500
# After this many single-row failures in a row the failure is the database, not the rows
# (schema not migrated, Supabase down): the rest are failed without another request.
SYSTEMIC_FAILURE_ROWS = 5


def _write_changed(pending: list[tuple[str, str, MatchScore]]) -> tuple[int, int]:
    """Writes `pending` in chunks; a chunk that fails is retried row by row, so one bad
    pair costs only itself. Returns (written, failed)."""
    written = 0
    failed = 0
    consecutive_failures = 0
    for start in range(0, len(pending), UPSERT_CHUNK_SIZE):
        chunk = pending[start : start + UPSERT_CHUNK_SIZE]
        if consecutive_failures >= SYSTEMIC_FAILURE_ROWS:
            failed += len(chunk)
            continue
        try:
            upsert_match_scores(chunk)
            written += len(chunk)
            consecutive_failures = 0
            continue
        except Exception:  # noqa: BLE001 - fall back to per-pair isolation
            logger.warning("match: chunk upsert failed, retrying row by row", exc_info=True)
        for pair in chunk:
            if consecutive_failures >= SYSTEMIC_FAILURE_ROWS:
                failed += 1
                continue
            try:
                upsert_match_scores([pair])
                written += 1
                consecutive_failures = 0
            except Exception as exc:  # noqa: BLE001 - isolate per-pair failures
                consecutive_failures += 1
                failed += 1
                logger.warning(
                    "match: pair scoring failed",
                    extra={"company_id": pair[0], "opportunity_id": pair[1], "error": str(exc)},
                )
    return written, failed


def run() -> None:
    started_at = datetime.now(UTC)
    try:
        companies = get_companies_for_matching()
        opportunities = get_analyzed_opportunities()

        existing: dict[tuple[str, str], ScoreValues]
        try:
            existing = get_existing_scores()
        except Exception:  # noqa: BLE001 - unknown state only costs extra writes
            logger.warning(
                "match: could not read stored scores - writing every pair this run",
                exc_info=True,
            )
            existing = {}

        computed = 0
        unchanged = 0
        failed = 0
        pending: list[tuple[str, str, MatchScore]] = []
        for company_id, company in companies:
            for opportunity_id, requirements in opportunities:
                try:
                    score = compute_match_score(company, requirements)
                except Exception as exc:  # noqa: BLE001 - isolate per-pair failures
                    logger.warning(
                        "match: pair scoring failed",
                        extra={
                            "company_id": company_id,
                            "opportunity_id": opportunity_id,
                            "error": str(exc),
                        },
                    )
                    failed += 1
                    continue
                computed += 1
                if existing.get((company_id, opportunity_id)) == score_values(score):
                    unchanged += 1
                else:
                    pending.append((company_id, opportunity_id, score))

        written, write_failed = _write_changed(pending)
        failed += write_failed
    except Exception:
        logger.exception(
            "match job failed entirely - existing match_scores are unaffected",
            extra={"job": "match", "status": "failed"},
        )
        return

    duration_seconds = (datetime.now(UTC) - started_at).total_seconds()
    logger.info(
        "match job finished",
        extra={
            "job": "match",
            "status": "ok" if failed == 0 else "partial",
            "duration": duration_seconds,
            "companies": len(companies),
            "opportunities": len(opportunities),
            "computed": computed,
            "written": written,
            "unchanged": unchanged,
            "failed": failed,
        },
    )

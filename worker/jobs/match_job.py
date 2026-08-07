"""Scheduled Match Engine job. Deterministic and fast (no LLM - worker/matching/
engine.py), so unlike analyze_job this recomputes every company x every analyzed
opportunity on every run rather than batching. A total failure is caught and logged,
not raised - existing scores stay as they were, nothing else is blocked
(docs/DATA_PIPELINE.md#failure-isolation)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from worker.matching.engine import compute_match_score
from worker.repositories.match_scores import (
    get_analyzed_opportunities,
    get_companies_for_matching,
    upsert_match_score,
)

logger = logging.getLogger(__name__)


def run() -> None:
    started_at = datetime.now(UTC)
    try:
        companies = get_companies_for_matching()
        opportunities = get_analyzed_opportunities()

        computed = 0
        for company_id, company in companies:
            for opportunity_id, requirements in opportunities:
                score = compute_match_score(company, requirements)
                upsert_match_score(company_id, opportunity_id, score)
                computed += 1
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
            "status": "ok",
            "duration": duration_seconds,
            "companies": len(companies),
            "opportunities": len(opportunities),
            "computed": computed,
        },
    )

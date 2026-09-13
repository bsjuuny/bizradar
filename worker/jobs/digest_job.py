"""Scheduled Telegram Watch digest. For every company with a registered
telegram_chat_id (Settings) and at least one active watch_conditions row, finds
opportunities posted in the last DIGEST_WINDOW_HOURS that match one of their watch
conditions and haven't been sent before, and pushes one Telegram message per company.

`_matches_watch` mirrors matchesWatch in apps/web/src/lib/queue.ts - keep the two in
sync if either changes. This job never recomputes match scores; it only reads what
match_job.py has already written to match_scores.

A total failure is caught and logged, not raised - same failure-isolation rule as
match_job.py. A single company's send failure (bad chat_id, Telegram outage) does not
block the rest, and is simply retried on the next run since mark_sent only records
opportunities that were actually delivered.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from worker.notify.telegram import send_telegram_message
from worker.repositories.watch_digest import (
    get_active_watch_conditions,
    get_already_sent,
    get_companies_with_telegram,
    get_match_scores,
    get_recent_opportunities,
    mark_sent,
)

logger = logging.getLogger(__name__)

DIGEST_WINDOW_HOURS = 24
MAX_ITEMS_PER_MESSAGE = 10


def _matches_watch(
    opportunity: dict[str, Any], watch: dict[str, Any], match_score: float | None
) -> bool:
    # get_active_watch_conditions() already filters active=true at the query level, so
    # this is redundant today - kept so _matches_watch stays a true port of
    # apps/web/src/lib/queue.ts's matchesWatch (`if (!watch.active) return false`)
    # rather than silently depending on the caller having done it.
    if not watch.get("active"):
        return False
    if watch.get("category") and opportunity.get("category") != watch["category"]:
        return False

    budget = opportunity.get("budget_amount")
    if watch.get("min_budget") is not None and (budget or 0) < watch["min_budget"]:
        return False
    if watch.get("max_budget") is not None and budget is not None and budget > watch["max_budget"]:
        return False

    if watch.get("min_match_score") is not None and (match_score or 0) < watch["min_match_score"]:
        return False

    keyword = (watch.get("keyword") or "").strip().lower()
    if keyword:
        haystack = f"{opportunity.get('title', '')} {opportunity.get('organization') or ''}".lower()
        if keyword not in haystack:
            return False

    return True


def _format_message(company_name: str, matches: list[tuple[dict[str, Any], list[str]]]) -> str:
    lines = [
        f"[{company_name}] Watch 다이제스트",
        f"최근 {DIGEST_WINDOW_HOURS}시간 신규 매칭 {len(matches)}건",
        "",
    ]
    for opportunity, watch_names in matches[:MAX_ITEMS_PER_MESSAGE]:
        title = opportunity.get("title", "(제목 없음)")
        org = opportunity.get("organization") or "공고기관 미확인"
        lines.append(f"- {title} ({org}) — {', '.join(watch_names)}")
    remaining = len(matches) - MAX_ITEMS_PER_MESSAGE
    if remaining > 0:
        lines.append(f"...외 {remaining}건")
    return "\n".join(lines)


def run() -> None:
    started_at = datetime.now(UTC)
    sent_count = 0
    try:
        companies = get_companies_with_telegram()
        if not companies:
            logger.info("digest: no companies with telegram_chat_id configured, skipping")
            return

        company_ids = [c["id"] for c in companies]
        watches_by_company = get_active_watch_conditions(company_ids)
        # Only companies with an active watch even need the rest of the pipeline.
        active_company_ids = [cid for cid in company_ids if watches_by_company.get(cid)]
        if not active_company_ids:
            logger.info("digest: no company has an active watch condition, skipping")
            return

        since = started_at - timedelta(hours=DIGEST_WINDOW_HOURS)
        opportunities = get_recent_opportunities(since)
        if not opportunities:
            logger.info("digest: no opportunities posted in the lookback window")
            return

        opportunity_ids = [o["id"] for o in opportunities]
        scores = get_match_scores(active_company_ids, opportunity_ids)

        for company in companies:
            company_id = company["id"]
            watches = watches_by_company.get(company_id)
            if not watches:
                continue

            already_sent = get_already_sent(company_id, opportunity_ids)
            matches: list[tuple[dict[str, Any], list[str]]] = []
            for opportunity in opportunities:
                if opportunity["id"] in already_sent:
                    continue
                score = scores.get((company_id, opportunity["id"]))
                matched_names = [
                    w["name"] for w in watches if _matches_watch(opportunity, w, score)
                ]
                if matched_names:
                    matches.append((opportunity, matched_names))

            if not matches:
                continue

            message = _format_message(company["name"], matches)
            if send_telegram_message(company["telegram_chat_id"], message):
                mark_sent(company_id, [o["id"] for o, _ in matches])
                sent_count += 1
            else:
                # send_telegram_message logs status/detail but not chat_id (a Telegram
                # personal identifier) or company_id - log our own internal id here to
                # correlate the failure, matching worker/jobs/match_job.py's convention
                # of logging company_id, never PII, on a per-item failure.
                logger.warning(
                    "digest: send failed for a company", extra={"company_id": company_id}
                )
    except Exception:
        logger.exception("digest job failed entirely", extra={"job": "digest", "status": "failed"})
        return

    duration_seconds = (datetime.now(UTC) - started_at).total_seconds()
    logger.info(
        "digest job finished",
        extra={
            "job": "digest",
            "status": "ok",
            "duration": duration_seconds,
            "companies_notified": sent_count,
        },
    )

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
# 텔레그램 sendMessage의 상한은 4,096자다. 그 숫자를 그대로 쓰지 않는 이유:
# 상한은 UTF-16 코드 유닛 기준이라 한글에서 파이썬 len()과 어긋나고, 제목·기관명은
# G2B 원문이라 길이를 통제할 수 없다. 넘치면 400으로 메시지 전체가 실패해 한 건도
# 전달되지 않으므로, 여유를 두고 자른 뒤 여러 건으로 나눠 보낸다.
MAX_MESSAGE_CHARS = 3_500


def _has_watch_criteria(watch: dict[str, Any]) -> bool:
    return (
        bool((watch.get("keyword") or "").strip())
        or watch.get("category") is not None
        or watch.get("min_budget") is not None
        or watch.get("max_budget") is not None
        or watch.get("min_match_score") is not None
    )


def _matches_watch(
    opportunity: dict[str, Any], watch: dict[str, Any], match_score: float | None
) -> bool:
    # get_active_watch_conditions() already filters active=true at the query level, so
    # this is redundant today - kept so _matches_watch stays a true port of
    # apps/web/src/lib/queue.ts's matchesWatch (`if (!watch.active) return false`)
    # rather than silently depending on the caller having done it.
    if not watch.get("active"):
        return False
    if not _has_watch_criteria(watch):
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


def _item_line(opportunity: dict[str, Any], watch_names: list[str]) -> str:
    title = opportunity.get("title", "(제목 없음)")
    org = opportunity.get("organization") or "공고기관 미확인"
    return f"- {title} ({org}) — {', '.join(watch_names)}"


def _format_messages(
    company_name: str, matches: list[tuple[dict[str, Any], list[str]]]
) -> list[tuple[str, list[str]]]:
    """(메시지 본문, 그 메시지에 담긴 opportunity_id들) 목록.

    예전에는 상위 10건만 싣고 "...외 N건"으로 뭉갰는데, 호출부가 매칭된 전체를
    mark_sent()에 넘기고 있어서 잘린 건들이 화면에 한 번도 안 나온 채 발송 완료로
    기록됐다 - 그 공고는 영영 다시 안 나온다. 이제 전부 싣되 길이 상한에서 끊고,
    각 메시지가 실제로 담은 id만 호출부가 기록하도록 함께 돌려준다.
    """
    total = len(matches)
    chunks: list[tuple[str, list[str]]] = []
    index = 0
    while index < total:
        header = [f"[{company_name}] Watch 다이제스트"]
        if total > 1:
            header.append(f"최근 {DIGEST_WINDOW_HOURS}시간 신규 매칭 {total}건 (일부 {{part}})")
        else:
            header.append(f"최근 {DIGEST_WINDOW_HOURS}시간 신규 매칭 {total}건")
        header.append("")

        lines: list[str] = []
        ids: list[str] = []
        length = sum(len(line) + 1 for line in header)
        while index < total:
            opportunity, watch_names = matches[index]
            line = _item_line(opportunity, watch_names)
            # 한 건이 통째로 상한을 넘으면 그 건만 담아 보낸다. 그러지 않으면
            # while 루프가 전진하지 못해 무한 루프가 된다.
            if lines and length + len(line) + 1 > MAX_MESSAGE_CHARS:
                break
            lines.append(line)
            ids.append(opportunity["id"])
            length += len(line) + 1
            index += 1
        chunks.append(("\n".join(header + lines), ids))

    if len(chunks) == 1:
        return [(chunks[0][0].replace(" (일부 {part})", ""), chunks[0][1])]
    return [
        (body.replace("{part}", f"{number}/{len(chunks)}"), ids)
        for number, (body, ids) in enumerate(chunks, start=1)
    ]


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

            # 메시지별로 그 메시지가 실제로 담은 id만 기록한다. 3개 중 2개만
            # 전달되면 2개분만 발송 완료가 되고 나머지는 다음 회차에 다시 시도된다
            # (전체를 한 번에 기록하면 못 본 건이 영구 유실된다).
            delivered_any = False
            for message, delivered_ids in _format_messages(company["name"], matches):
                if send_telegram_message(company["telegram_chat_id"], message):
                    mark_sent(company_id, delivered_ids)
                    delivered_any = True
                    continue
                # send_telegram_message logs status/detail but not chat_id (a Telegram
                # personal identifier) or company_id - log our own internal id here to
                # correlate the failure, matching worker/jobs/match_job.py's convention
                # of logging company_id, never PII, on a per-item failure.
                logger.warning(
                    "digest: send failed for a company", extra={"company_id": company_id}
                )
                break
            if delivered_any:
                sent_count += 1
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

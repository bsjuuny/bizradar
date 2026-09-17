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

from worker.config import get_settings
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

# 하루에 텔레그램으로 내보낼 최대 건수. 매칭이 28건까지 나오는데(실측) 그걸 다 보내면
# 훑어보기가 어려워 결국 아무것도 안 읽는다 - 텔레그램은 "오늘 볼 만한 것"만 추리고
# 전체 목록은 웹이 담당한다.
#
# 중요: 상한을 넘겨 못 실은 건들은 mark_sent 하지 않는다. 예전 구현은 10건만 싣고
# 매칭 전체를 발송 완료로 기록해서, 못 본 건이 다음 회차에 already_sent로 걸러지며
# 영구 유실됐다(2026-09-16에 고침). 못 실은 건은 "그 외 N건"으로만 알리고 기록은
# 건드리지 않는다.
MAX_ITEMS_PER_DIGEST = 5


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


def _format_budget(value: Any) -> str:
    """예산을 한국어 단위로 줄여 쓴다. 자릿수가 긴 원 단위는 훑어보기 어렵다."""
    if not isinstance(value, (int, float)) or value <= 0:
        return "예산 미공개"
    if value >= 100_000_000:
        return f"{value / 100_000_000:.1f}억"
    if value >= 10_000:
        return f"{value / 10_000:,.0f}만"
    return f"{value:,.0f}원"


def _parse_deadline(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _format_close(value: Any) -> str | None:
    """마감일 + D-day. 날짜만으로는 급한지 아닌지 바로 안 읽힌다.

    G2B의 마감시각은 수집 시 tz 없이 파싱돼 저장되므로(worker/collectors/g2b.py의
    _parse_datetime), 저장된 값의 날짜가 곧 한국 기준 날짜다. 별도 변환을 하면 오히려
    하루가 밀린다.
    """
    parsed = _parse_deadline(value)
    if parsed is None:
        return None
    label = f"마감 {parsed.strftime('%m-%d')}"
    days = (parsed.date() - datetime.now(UTC).date()).days
    if days < 0:
        return f"{label} (지남)"
    if days == 0:
        return f"{label} (오늘)"
    return f"{label} (D-{days})"


def _is_expired(opportunity: dict[str, Any]) -> bool:
    parsed = _parse_deadline(opportunity.get("bid_close_at"))
    if parsed is None:
        return False
    return parsed.date() < datetime.now(UTC).date()


def _is_open_to_all(opportunity: dict[str, Any]) -> bool:
    """업종제한도 지역제한도 없는 공고인지.

    tri-state에서 `None`은 "공고에 명시 안 됨"이지 "제한 없음"이 아니다 - 명시되지
    않은 것을 "누구나 지원 가능"으로 보여주면 실제로는 자격이 안 되는 공고를 권하게
    된다. 그래서 `is False`로만 인정한다(apps/web/src/lib/market.ts와 같은 규약).
    지역제한은 문자열 컬럼이라 빈 값/공백이면 제한 없음으로 본다.
    """
    if opportunity.get("industry_limited") is not False:
        return False
    return not str(opportunity.get("region_restriction") or "").strip()


def _item_line(
    opportunity: dict[str, Any],
    watch_names: list[str],
    *,
    show_watch_names: bool = True,
    match_score: float | None = None,
) -> str:
    """한 건을 제목 + 메타 2줄 + 링크로 풀어 쓴다.

    하루 5건만 보내므로 건당 깊이를 줄 수 있다. 예전엔 제목·발주처만 한 줄에 붙여서
    예산이나 마감이 제목에 묻혔고, 정작 바로 눌러볼 공고 링크가 빠져 있었다.

    Watch가 하나뿐이면 항목마다 같은 이름이 반복될 뿐 정보가 없어서
    (실측: 28건 전부 "🔔 about_it", 약 280자) 호출부가 헤더로 올리고 여기서는 뺀다.
    """
    title = opportunity.get("title", "(제목 없음)")
    org = opportunity.get("organization") or "공고기관 미확인"

    primary = [f"🏢 {org}", f"💰 {_format_budget(opportunity.get('budget_amount'))}"]
    demand = str(opportunity.get("demand_organization") or "").strip()
    if demand and demand != org:
        primary.append(f"🙋 수요 {demand}")
    if _is_open_to_all(opportunity):
        primary.append("🟢 업종·지역 제한 없음")
    else:
        # 제한이 있을 때 "무엇이" 막는지가 지원 가능 여부를 가르는 정보다.
        region = str(opportunity.get("region_restriction") or "").strip()
        if region:
            primary.append(f"📍 {region}")

    secondary: list[str] = []
    closing = _format_close(opportunity.get("bid_close_at"))
    if closing:
        secondary.append(f"📅 {closing}")
    if match_score is not None:
        secondary.append(f"🎯 매칭 {round(match_score)}점")
    procurement = str(opportunity.get("procurement_category") or "").strip()
    if procurement:
        secondary.append(f"🗂 {procurement}")
    if show_watch_names and watch_names:
        secondary.append(f"🔔 {', '.join(watch_names)}")

    lines = [f"▸ {title}", f"   {' · '.join(primary)}"]
    if secondary:
        lines.append(f"   {' · '.join(secondary)}")
    url = str(opportunity.get("source_url") or "").strip()
    if url:
        lines.append(f"   🔗 {url}")
    return "\n".join(lines)


def _rank_key(match: tuple[dict[str, Any], list[str]]) -> tuple[int, int, str, float]:
    """상한 안에 무엇을 실을지 정하는 순서.

    1) 이미 마감된 공고는 맨 뒤 - get_recent_opportunities는 게시일 기준으로만 가져와서
       마감이 지난 건도 섞여 들어온다. 5칸뿐인데 그게 한 칸을 먹으면 손해다.
    2) 업종·지역 제한이 없는 공고 먼저 - 지원 자체가 가능한 건이 맨 위에 와야 한다.
    3) 마감이 급한 것 먼저 (마감일 없는 건은 뒤로).
    4) 예산 큰 것 먼저.

    매칭 점수는 정렬에 넣지 않는다 - 점수는 analyze/match 파이프라인을 거쳐야 생겨서
    갓 수집된 공고엔 없고(실측: 최근 200건 중 0건), 정렬에 쓰면 새 공고가 구조적으로
    밀린다. 표시만 한다.
    """
    opportunity, _ = match
    expired_last = 1 if _is_expired(opportunity) else 0
    open_first = 0 if _is_open_to_all(opportunity) else 1
    # bid_close_at은 ISO 문자열이라 사전순 비교가 곧 시간순이다. 없으면 맨 뒤로 보낸다.
    closes_at = str(opportunity.get("bid_close_at") or "9999-12-31")
    budget = opportunity.get("budget_amount") or 0
    return (expired_last, open_first, closes_at, -float(budget))


def _format_messages(
    company_name: str,
    matches: list[tuple[dict[str, Any], list[str]]],
    *,
    remaining: int = 0,
    score_by_id: dict[str, float] | None = None,
    web_url: str | None = None,
) -> list[tuple[str, list[str]]]:
    """(메시지 본문, 그 메시지에 담긴 opportunity_id들) 목록.

    호출부는 각 메시지가 실제로 담은 id만 mark_sent()에 넘긴다 - 예전에는 상위 10건만
    싣고 매칭 전체를 기록해서 못 본 건이 영구 유실됐다(2026-09-16에 고침).

    ``remaining``은 상한(MAX_ITEMS_PER_DIGEST) 때문에 못 실은 건수다. 마지막 메시지
    끝에 안내만 덧붙이고, 그 건들의 id는 어디에도 기록하지 않는다.
    """
    total = len(matches)
    # 모든 항목이 같은 Watch 하나에만 걸렸다면 이름을 헤더로 올리고 항목에서는 뺀다.
    distinct_names = sorted({name for _, names in matches for name in names})
    shared_watch = distinct_names[0] if len(distinct_names) == 1 else None

    chunks: list[tuple[str, list[str]]] = []
    index = 0
    while index < total:
        header = [f"[{company_name}] Watch 다이제스트"]
        if total > 1:
            header.append(f"최근 {DIGEST_WINDOW_HOURS}시간 신규 매칭 {total}건 (일부 {{part}})")
        else:
            header.append(f"최근 {DIGEST_WINDOW_HOURS}시간 신규 매칭 {total}건")
        if shared_watch:
            header.append(f"🔔 Watch: {shared_watch}")
        header.append("")

        lines: list[str] = []
        ids: list[str] = []
        length = sum(len(line) + 1 for line in header)
        while index < total:
            opportunity, watch_names = matches[index]
            line = _item_line(
                opportunity,
                watch_names,
                show_watch_names=shared_watch is None,
                match_score=(score_by_id or {}).get(opportunity["id"]),
            )
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
        bodies = [(chunks[0][0].replace(" (일부 {part})", ""), chunks[0][1])]
    else:
        bodies = [
            (body.replace("{part}", f"{number}/{len(chunks)}"), ids)
            for number, (body, ids) in enumerate(chunks, start=1)
        ]
    if remaining > 0:
        last_body, last_ids = bodies[-1]
        notice = f"…오늘 조건에 맞는 공고가 {remaining}건 더 있어요."
        # 링크는 설정(WEB_BASE_URL)이 있을 때만 붙인다 - 배포 주소를 코드에 박아두면
        # 주소가 바뀌는 순간 죽은 링크를 매일 보내게 된다.
        notice += (
            f"\n전체 목록 보기: {web_url}" if web_url else " 전체 목록은 웹에서 확인할 수 있습니다."
        )
        bodies[-1] = (f"{last_body}\n\n{notice}", last_ids)
    return bodies


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

        # 상한에 걸려 못 실은 건들을 볼 수 있는 웹 목록 주소. WEB_BASE_URL이 비어 있으면
        # None으로 두고 링크 없는 문구만 보낸다 - 잘못된 링크보다 없는 게 낫다.
        base_url = (get_settings().web_base_url or "").strip().rstrip("/")
        web_url = f"{base_url}/opportunities" if base_url else None

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

            # 상한만큼만 골라 싣는다. 못 실은 건은 건수만 알리고 mark_sent 하지 않아
            # 발송 완료로 잘못 기록되지 않는다.
            ranked = sorted(matches, key=_rank_key)
            selected = ranked[:MAX_ITEMS_PER_DIGEST]
            remaining = len(ranked) - len(selected)

            # 메시지별로 그 메시지가 실제로 담은 id만 기록한다. 3개 중 2개만
            # 전달되면 2개분만 발송 완료가 되고 나머지는 다음 회차에 다시 시도된다
            # (전체를 한 번에 기록하면 못 본 건이 영구 유실된다).
            delivered_any = False
            score_by_id = {
                opportunity_id: score
                for (scored_company_id, opportunity_id), score in scores.items()
                if scored_company_id == company_id
            }
            for message, delivered_ids in _format_messages(
                company["name"],
                selected,
                remaining=remaining,
                score_by_id=score_by_id,
                web_url=web_url,
            ):
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

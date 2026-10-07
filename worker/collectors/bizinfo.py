"""기업마당(BizInfo) collector - 지원사업정보 API (중앙부처·지자체·유관기관 지원사업 공고).
Lands in the same support_programs table as K-Startup. See
docs/SUPPORT_PROGRAMS.md.

Endpoint and parameters are from the official spec page
(https://www.bizinfo.go.kr/apiDetail.do?id=bizinfoApi, checked 2026-10-07):
  https://www.bizinfo.go.kr/uss/rss/bizinfoApi.do?crtfcKey=...&dataType=json&searchCnt=N
The key is BizInfo's own `crtfcKey` (기업마당 > 활용정보 > 정책정보 개방 > 사용신청), not a
data.go.kr service key. Without a key the API answers HTTP 200 with
`{"reqErr": "인증키를 입력해주세요."}` (verified live 2026-10-07), not an HTTP error status.

Verified with a real key 2026-10-07 (recorded sample: fixtures/bizinfo/api_response_sample.json):
the body is `{"jsonArray": [...]}` - the item list itself - with `totCnt` (a number) on
every item, 1,443 items = totCnt, all `pblanc*` fields present, 신청기간 as
`YYYY-MM-DD ~ YYYY-MM-DD` or a phrase. The official spec page shows other forms -
`{"jsonArray": {"item": [...]}}`, `20220727 ~ 20220930`, RSS-style names (`seq`,
`author`, `reqstDt`) - which are still accepted as fallbacks in case the API drifts back
to what it documents.

One request returns every currently posted announcement, so unlike K-Startup there is
no pagination. That also makes the response a complete list of what is open right now:
`listed_ids` / `complete` let the job mark previously collected announcements that
dropped off the list as no longer recruiting.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import quote, quote_plus, urljoin, urlsplit
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel

from worker.ai.investment_filter import is_investment_linked
from worker.ai.support_it_filter import is_it_related
from worker.collectors.base import (
    BaseCollector,
    CollectorError,
    RawRecord,
    clean_line,
    compute_content_hash,
    decode_entities,
)
from worker.config import Settings, get_settings

logger = logging.getLogger(__name__)

API_URL = "https://www.bizinfo.go.kr/uss/rss/bizinfoApi.do"
SITE_ORIGIN = "https://www.bizinfo.go.kr"
# 공고 상세 페이지. 옛 주소(/web/lay1/bbs/S1T122C128/AS/74/view.do?pblancId=...)는 이 주소로
# 302 된다(2026-10-07 확인). pblancUrl이 비어 있을 때만 이걸로 만든다.
DETAIL_URL = SITE_ORIGIN + "/sii/siia/selectSIIA200Detail.do?pblancId={pblanc_id}"
# Everything in one response. Larger than the ~1,500 currently posted announcements so a
# short response means truncation, which `complete` reports (see module docstring).
SEARCH_COUNT = 5000
REQUEST_TIMEOUT_SECONDS = 60.0
MAX_RETRIES = 3
# Seconds before retry 1, 2, ... after a transport error or 5xx - immediate retries of a
# 5,000-item request just repeat the failure against a struggling server.
RETRY_BACKOFF_SECONDS = (2.0, 5.0)
# Per-item fields that change without the announcement changing: the view counter, and the
# list-wide total (shifts whenever any announcement is added or removed). Left out of
# content_hash so it only moves when the posting itself does.
_VOLATILE_FIELDS = frozenset({"inqireCo", "totCnt"})
SEOUL = ZoneInfo("Asia/Seoul")

# 공고명 맨 앞 [지역] 표시로 쓰이는 값 - 2026-10-07 공개 목록 1,442건에서 실제로 나온 것들.
# 여러 지역은 "대구ㆍ경북"처럼 가운뎃점으로 잇는다. 여기 없는 말이 섞인 태그는 지역으로 읽지
# 않는다(K-Startup 제목의 "[한국도로공사]" 같은 기관명 태그와 구별하려는 것).
_REGION_WORDS = frozenset(
    {
        "전국",
        "서울",
        "부산",
        "대구",
        "인천",
        "광주",
        "대전",
        "울산",
        "세종",
        "경기",
        "강원",
        "충북",
        "충남",
        "전북",
        "전남",
        "경북",
        "경남",
        "제주",
        "전남광주",
        "충청",
        "수도권",
        "비수도권",
        "호남권",
        "영남권",
        "충청권",
    }
)
_REGION_TAG = re.compile(r"^\s*\[([^\]]+)\]")
_REGION_SEPARATORS = re.compile(r"\s*[ㆍ·・,/]\s*")
_PERIOD = re.compile(r"^(\d{4})[.-]?(\d{2})[.-]?(\d{2})\s*~\s*(\d{4})[.-]?(\d{2})[.-]?(\d{2})$")
_BLOCK_END_TAGS = re.compile(r"<\s*(br|/p|/div|/li|/tr|/h\d)\s*/?\s*>", re.IGNORECASE)
_TAGS = re.compile(r"<[^>]+>")


class BizInfoNormalizedProgram(BaseModel):
    external_id: str
    title: str
    organization: str | None = None
    # 소관기관(jrsdInsttNm). K-Startup 행에서는 담당부서가 들어가는 컬럼이라 화면이 출처를
    # 보고 이름표를 바꾼다.
    department: str | None = None
    category: str | None = None
    region: str | None = None
    target: str | None = None
    recruiting: bool | None = None
    investment_linked: bool = False
    it_related: bool = False
    application_start: datetime | None = None
    application_end: datetime | None = None
    application_period_text: str | None = None
    description: str | None = None
    source_url: str | None = None
    content_hash: str
    raw_payload: dict[str, Any]


def _field(item: dict[str, Any], *names: str) -> str:
    """First non-empty value among the spec's name and its RSS-style alias, as clean
    single-line text (HTML entities decoded, whitespace collapsed). Not for URLs - see
    _url_field."""
    for name in names:
        text = clean_line(item.get(name))
        if text:
            return text
    return ""


def _url_field(item: dict[str, Any], *names: str) -> str:
    """Like _field but without entity decoding: a URL's "&" starts a query parameter,
    not a character reference."""
    for name in names:
        value = item.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _total_count(item: dict[str, Any]) -> int | None:
    # A number in the live API (1443); the spec table types it as a string. Tolerates
    # "1,443" too. Anything else -> unknown.
    text = str(item.get("totCnt", "")).replace(",", "").strip()
    return int(text) if text.isdigit() else None


def html_to_text(value: str) -> str:
    """사업개요(bsnsSumryCn)는 HTML이 섞여 온다 - 줄바꿈은 살리고 태그는 지운다."""
    text = _BLOCK_END_TAGS.sub("\n", value)
    text = decode_entities(_TAGS.sub("", text))
    lines = (" ".join(line.split()) for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def parse_period(raw: str) -> tuple[date, date] | None:
    """Only "YYYY-MM-DD ~ YYYY-MM-DD" (or YYYYMMDD / YYYY.MM.DD) reads as dates. Phrases
    like "예산 소진시까지" or "상시 접수" stay text - never guessed into a date."""
    match = _PERIOD.match(raw.strip())
    if not match:
        return None
    y1, m1, d1, y2, m2, d2 = (int(part) for part in match.groups())
    try:
        start, end = date(y1, m1, d1), date(y2, m2, d2)
    except ValueError:
        return None
    if end < start:
        return None
    return start, end


def parse_region(title: str) -> str | None:
    match = _REGION_TAG.match(title)
    if not match:
        return None
    parts = [part for part in _REGION_SEPARATORS.split(match.group(1).strip()) if part]
    if not parts or any(part not in _REGION_WORDS for part in parts):
        return None
    return "·".join(parts)


def _absolute_url(raw: str, pblanc_id: str) -> str:
    if not raw:
        return DETAIL_URL.format(pblanc_id=pblanc_id)
    url = urljoin(SITE_ORIGIN + "/", raw)
    parts = urlsplit(url)
    if parts.scheme == "http" and parts.hostname in ("www.bizinfo.go.kr", "bizinfo.go.kr"):
        url = "https://" + url[len("http://") :]
    return url


def today_kst() -> date:
    return datetime.now(SEOUL).date()


def extract_items(text: str) -> list[dict[str, Any]]:
    """Raises CollectorError for anything that isn't a well-formed successful body -
    non-JSON, the `reqErr` envelope (missing/invalid key), or no announcement list."""
    try:
        body = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CollectorError(f"BizInfo API returned non-JSON response: {text[:200]!r}") from exc

    if not isinstance(body, dict):
        raise CollectorError(f"BizInfo API returned unexpected JSON: {type(body).__name__}")
    if "reqErr" in body:
        raise CollectorError(f"BizInfo API service error: {body['reqErr']}")
    if "jsonArray" not in body:
        raise CollectorError(f"BizInfo API returned unexpected schema: {list(body)[:5]}")

    container = body["jsonArray"]
    if isinstance(container, dict):  # official spec example shape
        container = container.get("item", [])
    if isinstance(container, dict):  # a single item not wrapped in a list
        container = [container]
    if not isinstance(container, list):
        raise CollectorError(
            f"BizInfo API jsonArray is neither a list nor an object: {type(container).__name__}"
        )
    return [item for item in container if isinstance(item, dict)]


class BizInfoCollector(BaseCollector[BizInfoNormalizedProgram]):
    source = "bizinfo"

    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.Client | None = None,
        today: date | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.settings = settings or get_settings()
        self._client = client
        self._owns_client = client is None
        self._today = today
        self._sleep = sleep
        # Filled by collect(), reset at its start: every pblancId in the response, and
        # whether the response held the whole list - only then may the job treat "not
        # listed" as "no longer recruiting".
        self.listed_ids: set[str] = set()
        self.complete = False

    def __enter__(self) -> BizInfoCollector:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS)
        return self._client

    def _mask(self, text: str) -> str:
        # The key travels in the query string, and httpx error messages quote the URL -
        # percent-encoded, so a key with "+", "/" or "=" appears in that form, not raw.
        key = self.settings.bizinfo_api_key
        if not key:
            return text
        for form in {key, quote_plus(key), quote(key, safe="")}:
            text = text.replace(form, "***")
        return text

    def _fetch(self) -> list[dict[str, Any]]:
        if not self.settings.bizinfo_api_key:
            raise CollectorError("BIZINFO_API_KEY is not configured")

        params = {
            "crtfcKey": self.settings.bizinfo_api_key,
            "dataType": "json",
            "searchCnt": str(SEARCH_COUNT),
        }
        last_error = ""
        for attempt in range(1, MAX_RETRIES + 1):
            if attempt > 1:
                self._sleep(RETRY_BACKOFF_SECONDS[min(attempt - 2, len(RETRY_BACKOFF_SECONDS) - 1)])
            try:
                resp = self._get_client().get(API_URL, params=params)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = self._mask(str(exc))
                logger.warning(
                    "bizinfo: transport error, retrying",
                    extra={"attempt": attempt, "error": last_error},
                )
                continue
            if resp.status_code >= 500:
                last_error = f"HTTP {resp.status_code}"
                logger.warning(
                    "bizinfo: server error, retrying",
                    extra={"attempt": attempt, "status": resp.status_code},
                )
                continue
            if resp.status_code >= 400:
                # 403/429 are the source refusing us - don't hammer it, fail this cycle.
                raise CollectorError(f"BizInfo API HTTP error: {resp.status_code}")
            try:
                return extract_items(resp.text)
            except CollectorError as exc:
                # The error quotes part of the body; mask in case it ever echoes the key.
                raise CollectorError(self._mask(str(exc))) from None

        raise CollectorError(
            f"BizInfo API request failed after {MAX_RETRIES} attempts: {last_error}"
        )

    def collect(self) -> Iterable[RawRecord]:
        self.listed_ids = set()
        self.complete = False
        items = self._fetch()
        total = _total_count(items[0]) if items else None

        for item in items:
            pblanc_id = _field(item, "pblancId", "seq")
            if not pblanc_id:
                logger.warning("bizinfo: item missing pblancId, skipping")
                continue
            if pblanc_id in self.listed_ids:
                continue  # duplicate inside one response - idempotency guard
            self.listed_ids.add(pblanc_id)
            yield RawRecord(
                source=self.source,
                external_id=pblanc_id,
                fetched_at=datetime.now(UTC),
                payload=item,
            )

        # Complete only when the source states its total and every one of those
        # announcements arrived with a distinct id. A missing/unreadable totCnt, a short
        # or empty list, or repeated/missing ids all count as incomplete: closing
        # "unlisted" announcements on such a response would close ones that are open.
        self.complete = total is not None and total > 0 and len(self.listed_ids) >= total
        if not self.complete:
            logger.warning(
                "bizinfo: response not provably complete - closing unlisted is skipped",
                extra={"total": total, "received": len(items), "distinct": len(self.listed_ids)},
            )

    def normalize(self, raw: RawRecord) -> BizInfoNormalizedProgram:
        item = raw.payload
        title = _field(item, "pblancNm", "title")
        jurisdiction = _field(item, "jrsdInsttNm", "author")
        executor = _field(item, "excInsttNm")
        # 수행기관이 "직접수행"·"기초자치단체"면 실제 기관명이 아니라서 소관기관을 대신 쓴다.
        organization = (
            executor if executor and executor not in ("직접수행", "기초자치단체") else jurisdiction
        )
        summary_raw = item.get("bsnsSumryCn") or item.get("description") or ""
        description = html_to_text(str(summary_raw)) or None
        period_text = _field(item, "reqstBeginEndDe", "reqstDt")
        period = parse_period(period_text)
        today = self._today or today_kst()
        # 기업마당이 지금 게시 중인 공고는 모집 중으로 본다. 날짜가 있는데 이미 지났을 때만
        # 마감이다. 목록에서 내려간 공고는 job이 따로 마감 처리한다(module docstring).
        recruiting = not (period is not None and period[1] < today)

        return BizInfoNormalizedProgram(
            external_id=raw.external_id,
            title=title,
            organization=organization or None,
            department=jurisdiction or None,
            category=_field(item, "pldirSportRealmLclasCodeNm", "lcategory") or None,
            region=parse_region(title),
            target=_field(item, "trgetNm") or None,
            recruiting=recruiting,
            investment_linked=is_investment_linked(title, description),
            it_related=is_it_related(title),
            # Naive midnight, same convention as K-Startup's YYYYMMDD dates.
            application_start=datetime.combine(period[0], datetime.min.time()) if period else None,
            application_end=datetime.combine(period[1], datetime.min.time()) if period else None,
            application_period_text=period_text or None,
            description=description,
            source_url=_absolute_url(_url_field(item, "pblancUrl", "link"), raw.external_id),
            content_hash=compute_content_hash(
                {key: value for key, value in item.items() if key not in _VOLATILE_FIELDS}
            ),
            raw_payload=item,
        )

    def validate(self, normalized: BizInfoNormalizedProgram) -> bool:
        return bool(normalized.title)

    def persist(self, normalized: BizInfoNormalizedProgram) -> None:
        from worker.repositories.support_programs import upsert_bizinfo_program

        upsert_bizinfo_program(normalized)

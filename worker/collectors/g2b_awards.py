"""G2B award-result collector for service procurements.

The bid-announcement API cannot answer who won. This collector uses the separate
public-data-standard award operation and links its rows back to Project Radar through
the stable G2B bid notice number/order.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel

from worker.collectors.base import BaseCollector, CollectorError, RawRecord
from worker.collectors.g2b import _parse_amount, _parse_int, parse_response_body
from worker.config import Settings, get_settings

logger = logging.getLogger(__name__)

BASE_URL = "http://apis.data.go.kr/1230000/ao/PubDataOpnStdService"
OPERATION = "getDataSetOpnStdScsbidInfo"
SERVICE_BUSINESS_CODE = "5"
DEFAULT_PAGE_SIZE = 100
REQUEST_TIMEOUT_SECONDS = 15.0
MAX_RETRIES = 3
SEOUL = ZoneInfo("Asia/Seoul")
WINNER_NAME_FIELDS = ("bidwinnrNm", "sucsfbidCorpNm", "fnlSucsfCorpNm")


class G2BAwardResult(BaseModel):
    external_id: str
    bid_ntce_no: str
    bid_ntce_ord: int = 0
    bid_classification_no: str = "0"
    rebid_no: int = 0
    title: str | None = None
    winner_name: str
    winner_business_no: str | None = None
    winner_representative: str | None = None
    winner_address: str | None = None
    award_amount: float | None = None
    award_rate: float | None = None
    planned_price: float | None = None
    participant_count: int | None = None
    opened_at: datetime | None = None
    awarded_at: datetime | None = None
    raw_payload: dict[str, Any]


def _first(item: dict[str, Any], *names: str) -> Any:
    for name in names:
        value = item.get(name)
        if value not in (None, ""):
            return value
    return None


def _parse_api_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H%M",
        "%Y-%m-%d",
        "%Y%m%d%H%M%S",
        "%Y%m%d%H%M",
        "%Y%m%d",
    ):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=SEOUL)
        except ValueError:
            continue
    return None


def _parse_opened_at(item: dict[str, Any]) -> datetime | None:
    combined = _first(item, "rlOpengDt", "opengDt")
    if combined:
        return _parse_api_datetime(combined)

    opening_date = _first(item, "opengDate")
    if not opening_date:
        return None
    opening_time = _first(item, "opengTm") or "00:00"
    return _parse_api_datetime(f"{opening_date} {opening_time}")


class G2BAwardCollector(BaseCollector[G2BAwardResult]):
    source = "g2b_award"

    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.Client | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        page_size: int = DEFAULT_PAGE_SIZE,
        max_records: int | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._client = client
        self._owns_client = client is None
        self.page_size = page_size
        self.max_records = max_records
        # The API's query and result timestamps are Korea Standard Time. Formatting
        # an aware UTC value as if it were KST creates a nine-hour collection lag.
        now = datetime.now(SEOUL)
        self.since = since or now.replace(hour=0, minute=0, second=0, microsecond=0)
        self.until = until or now

    def __enter__(self) -> G2BAwardCollector:
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

    def _build_url(self, page_no: int) -> str:
        key = self.settings.g2b_award_api_key
        if not key:
            raise CollectorError("G2B_AWARD_API_KEY is not configured")
        params = (
            f"serviceKey={key}&pageNo={page_no}&numOfRows={self.page_size}"
            f"&bsnsDivCd={SERVICE_BUSINESS_CODE}"
            f"&opengBgnDt={self.since.strftime('%Y%m%d%H%M')}"
            f"&opengEndDt={self.until.strftime('%Y%m%d%H%M')}&type=json"
        )
        return f"{BASE_URL}/{OPERATION}?{params}"

    def _fetch_page(self, page_no: int) -> dict[str, Any]:
        url = self._build_url(page_no)
        last_error: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = self._get_client().get(url)
                response.raise_for_status()
                return parse_response_body(response.text)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                logger.warning(
                    "g2b award: transport error, retrying",
                    extra={"attempt": attempt, "page_no": page_no, "error": str(exc)},
                )
            except httpx.HTTPStatusError as exc:
                last_error = exc
                if exc.response.status_code == 429:
                    continue
                raise CollectorError(f"G2B award API HTTP error: {exc}") from exc
        raise CollectorError(
            f"G2B award API request failed after {MAX_RETRIES} attempts: {last_error}"
        )

    def collect(self) -> Iterable[RawRecord]:
        page_no = 1
        total_count: int | None = None
        fetched = 0
        yielded = 0
        seen: set[str] = set()
        while total_count is None or fetched < total_count:
            if self.max_records is not None and yielded >= self.max_records:
                return
            body = self._fetch_page(page_no)
            total_count = body.get("totalCount", 0) or 0
            items = body.get("items") or []
            if isinstance(items, dict):
                items = [items]
            if not items:
                break
            for item in items:
                bid_no = item.get("bidNtceNo")
                if not bid_no:
                    logger.warning("g2b award: item missing bidNtceNo, skipping")
                    continue
                # The standard result feed also includes unsuccessful/opening-only
                # rows. They are expected source data, not validation failures.
                if not _first(item, *WINNER_NAME_FIELDS):
                    continue
                external_id = self._external_id(item)
                if external_id in seen:
                    continue
                seen.add(external_id)
                yield RawRecord(
                    source=self.source,
                    external_id=external_id,
                    fetched_at=datetime.now(UTC),
                    payload=item,
                )
                yielded += 1
                if self.max_records is not None and yielded >= self.max_records:
                    return
            fetched += len(items)
            page_no += 1

    @staticmethod
    def _external_id(item: dict[str, Any]) -> str:
        return "-".join(
            [
                str(item.get("bidNtceNo", "")),
                str(item.get("bidNtceOrd") or "000"),
                str(item.get("bidClsfcNo") or "0"),
                str(item.get("rbidNo") or "0"),
            ]
        )

    def normalize(self, raw: RawRecord) -> G2BAwardResult:
        item = raw.payload
        return G2BAwardResult(
            external_id=raw.external_id,
            bid_ntce_no=str(item.get("bidNtceNo") or ""),
            bid_ntce_ord=_parse_int(item.get("bidNtceOrd")) or 0,
            bid_classification_no=str(item.get("bidClsfcNo") or "0"),
            rebid_no=_parse_int(item.get("rbidNo")) or 0,
            title=_first(item, "bidNtceNm", "bidNm"),
            winner_name=str(_first(item, *WINNER_NAME_FIELDS) or "").strip(),
            winner_business_no=_first(
                item, "bidwinnrBizno", "sucsfbidCorpBizrno", "fnlSucsfCorpBizrno", "bizrno"
            ),
            winner_representative=_first(
                item,
                "bidwinnrCeoNm",
                "sucsfbidCorpRprsntvNm",
                "fnlSucsfCorpCeoNm",
                "corpRprsntvNm",
            ),
            winner_address=_first(
                item, "bidwinnrAdrs", "sucsfbidCorpAdrs", "fnlSucsfCorpAdrs", "corpAdrs"
            ),
            award_amount=_parse_amount(_first(item, "sucsfbidAmt", "fnlSucsfAmt")),
            award_rate=_parse_amount(_first(item, "sucsfbidRate", "fnlSucsfRate", "fnlSucsfRt")),
            planned_price=_parse_amount(
                _first(item, "plnprc", "plnprcAmt", "prearngPrce", "presmptPrce")
            ),
            participant_count=_parse_int(_first(item, "prtcptCnum", "bidderCnt")),
            opened_at=_parse_opened_at(item),
            awarded_at=_parse_api_datetime(_first(item, "fnlSucsfDate", "sucsfbidDt")),
            raw_payload=item,
        )

    def validate(self, normalized: G2BAwardResult) -> bool:
        return bool(normalized.bid_ntce_no and normalized.winner_name)

    def persist(self, normalized: G2BAwardResult) -> None:
        from worker.repositories.awards import upsert_award_result

        upsert_award_result(normalized)

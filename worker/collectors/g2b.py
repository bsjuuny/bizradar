"""G2B (나라장터) collector - 용역(service) bid announcements only, since public-sector
IT/SI projects are classified under 용역, not 물품/공사/외자. See docs/DATA_PIPELINE.md.

Endpoint verified live against the real data.go.kr key (2026-08-07):
  http://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServc
Note the "ad/" segment - it's easy to miss and the API returns a generic
"service does not exist" error without it, not a helpful 404.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import BaseModel

from worker.collectors.base import BaseCollector, CollectorError, RawRecord
from worker.config import Settings, get_settings

logger = logging.getLogger(__name__)

BASE_URL = "http://apis.data.go.kr/1230000/ad/BidPublicInfoService"
OPERATION = "getBidPblancListInfoServc"
DEFAULT_PAGE_SIZE = 100
REQUEST_TIMEOUT_SECONDS = 15.0
MAX_RETRIES = 3


class G2BNormalizedOpportunity(BaseModel):
    external_id: str
    title: str
    organization: str | None = None
    demand_organization: str | None = None
    budget_amount: float | None = None
    estimated_price: float | None = None
    region_restriction: str | None = None
    posted_at: datetime | None = None
    bid_close_at: datetime | None = None
    open_at: datetime | None = None
    source_url: str | None = None
    content_hash: str
    raw_payload: dict[str, Any]


def _parse_amount(value: Any) -> float | None:
    if value in (None, "", "0"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    logger.warning("g2b: unrecognized datetime format", extra={"value": value})
    return None


def compute_content_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def parse_response_body(text: str) -> dict[str, Any]:
    """Raises CollectorError for anything that isn't a well-formed successful body -
    non-JSON (HTML error pages happen), the legacy OpenAPI_ServiceResponse error
    envelope (bad key, wrong path), or a JSON body with a non-zero result code."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CollectorError(f"G2B API returned non-JSON response: {text[:200]!r}") from exc

    if "OpenAPI_ServiceResponse" in data:
        header = data["OpenAPI_ServiceResponse"].get("cmmMsgHeader", {})
        message = header.get("returnAuthMsg") or header.get("errMsg") or "unknown service error"
        raise CollectorError(f"G2B API service error: {message}")

    response = data.get("response")
    if not isinstance(response, dict):
        raise CollectorError(f"G2B API returned unexpected schema: {list(data.keys())}")

    header = response.get("header", {})
    result_code = header.get("resultCode")
    if result_code not in ("00", None):
        raise CollectorError(f"G2B API business error ({result_code}): {header.get('resultMsg')}")

    body = response.get("body")
    return body if isinstance(body, dict) else {}


class G2BCollector(BaseCollector[G2BNormalizedOpportunity]):
    source = "g2b"

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
        # For live-mode smoke tests: cap total records pulled, per docs/MVP_SCOPE.md's
        # "small page size, short window, a few records only" live-test policy. Never
        # set in scheduled production runs.
        self.max_records = max_records

        now = datetime.now(UTC)
        self.since = since or now.replace(hour=0, minute=0, second=0, microsecond=0)
        self.until = until or now

    def __enter__(self) -> G2BCollector:
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
        if not self.settings.g2b_api_key:
            raise CollectorError("G2B_API_KEY is not configured")

        # serviceKey from data.go.kr is already URL-encoded ("Encoding" key) - append it
        # as-is. Re-encoding it (e.g. via httpx params=) double-encodes and the request
        # fails auth with a misleading "unregistered service key" error.
        params = (
            f"serviceKey={self.settings.g2b_api_key}"
            f"&pageNo={page_no}&numOfRows={self.page_size}&inqryDiv=1"
            f"&inqryBgnDt={self.since.strftime('%Y%m%d%H%M')}"
            f"&inqryEndDt={self.until.strftime('%Y%m%d%H%M')}"
            f"&type=json"
        )
        return f"{BASE_URL}/{OPERATION}?{params}"

    def _fetch_page(self, page_no: int) -> dict[str, Any]:
        url = self._build_url(page_no)
        last_error: Exception | None = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self._get_client().get(url)
                resp.raise_for_status()
                return parse_response_body(resp.text)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                logger.warning(
                    "g2b: transport error, retrying",
                    extra={"attempt": attempt, "page_no": page_no, "error": str(exc)},
                )
            except httpx.HTTPStatusError as exc:
                last_error = exc
                if exc.response.status_code == 429:
                    logger.warning(
                        "g2b: rate limited, retrying",
                        extra={"attempt": attempt, "page_no": page_no},
                    )
                    continue
                raise CollectorError(f"G2B API HTTP error: {exc}") from exc

        raise CollectorError(f"G2B API request failed after {MAX_RETRIES} attempts: {last_error}")

    def collect(self) -> Iterable[RawRecord]:
        page_no = 1
        total_count: int | None = None
        fetched = 0
        yielded = 0
        seen_external_ids: set[str] = set()

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
                    logger.warning("g2b: item missing bidNtceNo, skipping")
                    continue

                external_id = f"{bid_no}-{item.get('bidNtceOrd', '000')}"
                if external_id in seen_external_ids:
                    continue  # duplicate response across pages - idempotency guard
                seen_external_ids.add(external_id)

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

    def normalize(self, raw: RawRecord) -> G2BNormalizedOpportunity:
        item = raw.payload
        return G2BNormalizedOpportunity(
            external_id=raw.external_id,
            title=(item.get("bidNtceNm") or "").strip(),
            organization=item.get("ntceInsttNm") or None,
            demand_organization=item.get("dminsttNm") or None,
            budget_amount=_parse_amount(item.get("asignBdgtAmt")),
            estimated_price=_parse_amount(item.get("presmptPrce")),
            region_restriction=item.get("rgnLmtBidLocplcJdgmBssNm") or None,
            posted_at=_parse_datetime(item.get("bidNtceDt")),
            bid_close_at=_parse_datetime(item.get("bidClseDt")),
            open_at=_parse_datetime(item.get("opengDt")),
            source_url=item.get("bidNtceUrl") or item.get("bidNtceDtlUrl") or None,
            content_hash=compute_content_hash(item),
            raw_payload=item,
        )

    def validate(self, normalized: G2BNormalizedOpportunity) -> bool:
        return bool(normalized.title)

    def persist(self, normalized: G2BNormalizedOpportunity) -> None:
        from worker.repositories.opportunities import upsert_opportunity

        upsert_opportunity(normalized)

"""K-Startup (창업진흥원) collector - 사업공고(business support program announcements),
including TIPS/엔젤투자 등 investment-linked programs (worker/ai/investment_filter.py).
See docs/DATA_PIPELINE.md#support-programs.

Endpoint verified live against the real data.go.kr key (2026-08-10):
  https://apis.data.go.kr/B552735/kisedKstartupService01/getAnnouncementInformation01
Requires a *separate* data.go.kr 활용신청 from G2B's - the same account service key value
is reused once approved, but each dataset needs its own application. Without it: HTTP 200
with `{"OpenAPI_ServiceResponse": {"cmmMsgHeader": {"errMsg":
"SERVICE_KEY_IS_NOT_REGISTERED_ERROR", ...}}}, not an HTTP error status.

No confirmed working server-side date-range or status filter param (a guessed
`cond[rcrt_prgs_yn]=Y` returned a different, undocumented response shape - not used).
Results are stably sorted newest-first by `pbanc_sn` across pages (verified live:
page 1 and page 2 are contiguous, no gaps or overlaps), so `collect()` just walks pages
from the start each run - upserting on `(source, external_id)` makes re-fetching
already-seen recent announcements harmless, same idempotency principle as G2B.
`max_records` bounds this for both live-mode smoke tests and the scheduled job (unlike
G2B, there's no lookback-window date filter to bound it otherwise).
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

from worker.ai.investment_filter import is_investment_linked
from worker.collectors.base import BaseCollector, CollectorError, RawRecord
from worker.config import Settings, get_settings

logger = logging.getLogger(__name__)

BASE_URL = "https://apis.data.go.kr/B552735/kisedKstartupService01"
OPERATION = "getAnnouncementInformation01"
DEFAULT_PAGE_SIZE = 100
REQUEST_TIMEOUT_SECONDS = 15.0
MAX_RETRIES = 3
# Scheduled-job default: recent-first pagination (see module docstring) means a bounded
# fetch each run naturally covers new + recently-updated announcements without a date
# filter. Larger than G2B's per-run volume since there's no lookback window to rely on.
DEFAULT_MAX_RECORDS = 500


class KStartupNormalizedProgram(BaseModel):
    external_id: str
    title: str
    organization: str | None = None
    department: str | None = None
    supervising_type: str | None = None
    category: str | None = None
    region: str | None = None
    target: str | None = None
    recruiting: bool | None = None
    investment_linked: bool = False
    application_start: datetime | None = None
    application_end: datetime | None = None
    description: str | None = None
    source_url: str | None = None
    content_hash: str
    raw_payload: dict[str, Any]


def _parse_yn(value: Any) -> bool | None:
    if value == "Y":
        return True
    if value == "N":
        return False
    return None


def _parse_date(value: Any) -> datetime | None:
    # pbanc_rcpt_bgng_dt / pbanc_rcpt_end_dt are "YYYYMMDD" strings, no time component.
    if not value:
        return None
    try:
        return datetime.strptime(str(value), "%Y%m%d")
    except ValueError:
        logger.warning("kstartup: unrecognized date format", extra={"value": value})
        return None


def compute_content_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def parse_response_body(text: str) -> dict[str, Any]:
    """Raises CollectorError for anything that isn't a well-formed successful body -
    non-JSON, or the legacy OpenAPI_ServiceResponse error envelope (bad/unregistered
    key). A well-formed body always has a `data` list (possibly empty)."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CollectorError(f"K-Startup API returned non-JSON response: {text[:200]!r}") from exc

    if "OpenAPI_ServiceResponse" in data:
        header = data["OpenAPI_ServiceResponse"].get("cmmMsgHeader", {})
        message = header.get("returnAuthMsg") or header.get("errMsg") or "unknown service error"
        raise CollectorError(f"K-Startup API service error: {message}")

    if "data" not in data:
        raise CollectorError(f"K-Startup API returned unexpected schema: {list(data.keys())}")

    return data


class KStartupCollector(BaseCollector[KStartupNormalizedProgram]):
    source = "kstartup"

    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.Client | None = None,
        page_size: int = DEFAULT_PAGE_SIZE,
        max_records: int | None = DEFAULT_MAX_RECORDS,
    ) -> None:
        self.settings = settings or get_settings()
        self._client = client
        self._owns_client = client is None
        self.page_size = page_size
        # Never None in scheduled use (unlike G2B's max_records, which is test-only) -
        # see module docstring for why this collector needs a bound every run.
        self.max_records = max_records

    def __enter__(self) -> KStartupCollector:
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

    def _build_url(self, page: int) -> str:
        if not self.settings.kstartup_api_key:
            raise CollectorError("KSTARTUP_API_KEY is not configured")

        # Same "Encoding" service key gotcha as G2B (docs/TROUBLESHOOTING.md) - append
        # as-is, never re-encode via httpx params=.
        params = (
            f"serviceKey={self.settings.kstartup_api_key}"
            f"&page={page}&perPage={self.page_size}&returnType=json"
        )
        return f"{BASE_URL}/{OPERATION}?{params}"

    def _fetch_page(self, page: int) -> dict[str, Any]:
        url = self._build_url(page)
        last_error: Exception | None = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self._get_client().get(url)
                resp.raise_for_status()
                return parse_response_body(resp.text)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                logger.warning(
                    "kstartup: transport error, retrying",
                    extra={"attempt": attempt, "page": page, "error": str(exc)},
                )
            except httpx.HTTPStatusError as exc:
                last_error = exc
                if exc.response.status_code == 429:
                    logger.warning(
                        "kstartup: rate limited, retrying",
                        extra={"attempt": attempt, "page": page},
                    )
                    continue
                raise CollectorError(f"K-Startup API HTTP error: {exc}") from exc

        raise CollectorError(
            f"K-Startup API request failed after {MAX_RETRIES} attempts: {last_error}"
        )

    def collect(self) -> Iterable[RawRecord]:
        page = 1
        total_count: int | None = None
        fetched = 0
        yielded = 0
        seen_external_ids: set[str] = set()

        while total_count is None or fetched < total_count:
            if self.max_records is not None and yielded >= self.max_records:
                return
            body = self._fetch_page(page)
            total_count = body.get("totalCount") or 0
            items = body.get("data") or []

            if not items:
                break

            for item in items:
                pbanc_sn = item.get("pbanc_sn")
                if not pbanc_sn:
                    logger.warning("kstartup: item missing pbanc_sn, skipping")
                    continue

                external_id = str(pbanc_sn)
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
            page += 1

    def normalize(self, raw: RawRecord) -> KStartupNormalizedProgram:
        item = raw.payload
        title = (item.get("biz_pbanc_nm") or "").strip()
        description = item.get("pbanc_ctnt") or None
        return KStartupNormalizedProgram(
            external_id=raw.external_id,
            title=title,
            organization=item.get("pbanc_ntrp_nm") or None,
            department=item.get("biz_prch_dprt_nm") or None,
            supervising_type=item.get("sprv_inst") or None,
            category=item.get("supt_biz_clsfc") or None,
            region=item.get("supt_regin") or None,
            target=item.get("aply_trgt") or None,
            recruiting=_parse_yn(item.get("rcrt_prgs_yn")),
            investment_linked=is_investment_linked(title, description),
            application_start=_parse_date(item.get("pbanc_rcpt_bgng_dt")),
            application_end=_parse_date(item.get("pbanc_rcpt_end_dt")),
            description=description,
            source_url=item.get("detl_pg_url") or None,
            content_hash=compute_content_hash(item),
            raw_payload=item,
        )

    def validate(self, normalized: KStartupNormalizedProgram) -> bool:
        return bool(normalized.title)

    def persist(self, normalized: KStartupNormalizedProgram) -> None:
        from worker.repositories.support_programs import upsert_support_program

        upsert_support_program(normalized)

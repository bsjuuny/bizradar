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

import json
import logging
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import Any, NamedTuple

import httpx
from pydantic import BaseModel

from worker.ai.investment_filter import is_investment_linked
from worker.ai.support_it_filter import is_it_related
from worker.collectors.base import (
    BaseCollector,
    CollectorError,
    CollectorRunResult,
    RawRecord,
    clean_line,
    compute_content_hash,
    decode_entities,
)
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
# Changed rows go out this many per request (see KStartupCollector.run).
UPSERT_CHUNK_SIZE = 100
# After this many single-row failures in a row the failure is the database, not the rows.
SYSTEMIC_FAILURE_ROWS = 5


class StoredRow(NamedTuple):
    """What a run needs to know about a K-Startup row already in the database
    (worker/repositories/support_programs.fetch_kstartup_state)."""

    content_hash: str
    recruiting: bool | None


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
    it_related: bool = False
    application_start: datetime | None = None
    application_end: datetime | None = None
    description: str | None = None
    source_url: str | None = None
    content_hash: str
    raw_payload: dict[str, Any]


# The API returns some fields HTML-escaped - found live 2026-10-07: 28 stored rows showed
# "&apos;" / "&amp;" on Support Radar ("기술개발(R&amp;D)", "&apos;성과기업 후속 지원&apos;").
# Decoded here; existing rows via worker/jobs/support_reclassify.py.
def _text(value: Any) -> str | None:
    """Single-line fields - same cleaning as the 기업마당 collector (clean_line)."""
    return clean_line(value) or None


def _multiline(value: Any) -> str | None:
    """pbanc_ctnt keeps its line breaks; only entities are decoded."""
    if not value:
        return None
    return decode_entities(str(value)).strip() or None


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
        # Explicit UTC midnight: written without an offset, Postgres would read it in the
        # session TimeZone, and is_open() in SQL compares against UTC midnight.
        return datetime.strptime(str(value), "%Y%m%d").replace(tzinfo=UTC)
    except ValueError:
        logger.warning("kstartup: unrecognized date format", extra={"value": value})
        return None


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
        stored: Mapping[str, StoredRow] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._client = client
        self._owns_client = client is None
        self.page_size = page_size
        # Never None in scheduled use (unlike G2B's max_records, which is test-only) -
        # see module docstring for why this collector needs a bound every run.
        self.max_records = max_records
        # external_id -> StoredRow, read by the job before the run; rows that match are not
        # re-sent (see persist()). None: unknown, so every row is written.
        self._stored = stored
        # How many rows persist() skipped as unchanged this run.
        self.unchanged = 0
        self._pending: list[KStartupNormalizedProgram] = []

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
        title = _text(item.get("biz_pbanc_nm")) or ""
        description = _multiline(item.get("pbanc_ctnt"))
        return KStartupNormalizedProgram(
            external_id=raw.external_id,
            title=title,
            organization=_text(item.get("pbanc_ntrp_nm")),
            department=_text(item.get("biz_prch_dprt_nm")),
            supervising_type=_text(item.get("sprv_inst")),
            category=_text(item.get("supt_biz_clsfc")),
            region=_text(item.get("supt_regin")),
            target=_text(item.get("aply_trgt")),
            recruiting=_parse_yn(item.get("rcrt_prgs_yn")),
            investment_linked=is_investment_linked(title, description),
            it_related=is_it_related(title),
            application_start=_parse_date(item.get("pbanc_rcpt_bgng_dt")),
            application_end=_parse_date(item.get("pbanc_rcpt_end_dt")),
            description=description,
            source_url=item.get("detl_pg_url") or None,
            content_hash=compute_content_hash(item),
            raw_payload=item,
        )

    def validate(self, normalized: KStartupNormalizedProgram) -> bool:
        return bool(normalized.title)

    def run(self) -> CollectorRunResult:
        """BaseCollector.run, then the changed rows persist() queued go out in chunks of
        UPSERT_CHUNK_SIZE - one request per chunk instead of per row (500 single-row
        upserts every hour until 2026-10-15, nearly all of them unchanged). A chunk that
        fails is retried row by row, so one bad row costs only itself; those rows are
        moved from persisted to failed."""
        from worker.repositories.support_programs import upsert_kstartup_programs

        self.unchanged = 0
        self._pending = []
        result = super().run()
        pending, self._pending = self._pending, []
        consecutive_failures = 0
        last_error = ""

        def fail(normalized: KStartupNormalizedProgram, error: str) -> None:
            result.persisted -= 1
            result.failed += 1
            result.errors.append(f"{normalized.external_id}: {error}")

        for start in range(0, len(pending), UPSERT_CHUNK_SIZE):
            chunk = pending[start : start + UPSERT_CHUNK_SIZE]
            if consecutive_failures >= SYSTEMIC_FAILURE_ROWS:
                for normalized in chunk:
                    fail(normalized, f"not attempted after repeated failures: {last_error}")
                continue
            try:
                upsert_kstartup_programs(chunk)
                consecutive_failures = 0
                continue
            except Exception:
                logger.warning("kstartup: chunk upsert failed, retrying row by row", exc_info=True)
            for normalized in chunk:
                if consecutive_failures >= SYSTEMIC_FAILURE_ROWS:
                    fail(normalized, f"not attempted after repeated failures: {last_error}")
                    continue
                try:
                    upsert_kstartup_programs([normalized])
                    consecutive_failures = 0
                except Exception as exc:  # noqa: BLE001 - isolate per-record failures
                    consecutive_failures += 1
                    last_error = str(exc)
                    fail(normalized, last_error)
                    logger.warning(
                        "collector record failed",
                        extra={"source": self.source, "external_id": normalized.external_id},
                    )
        return result

    def persist(self, normalized: KStartupNormalizedProgram) -> None:
        """Queues the row for run() to write, unless the stored row has the same
        content_hash and recruiting state (all 500 of a 2026-10-15 run did). content_hash
        covers the raw payload only, not the derived columns - after a rule or normalize()
        change, run worker/jobs/support_reclassify.py as before; unchanged rows no longer
        pick it up on the next hourly run."""
        stored = self._stored.get(normalized.external_id) if self._stored is not None else None
        if (
            stored is not None
            and stored.content_hash == normalized.content_hash
            and stored.recruiting == normalized.recruiting
        ):
            self.unchanged += 1
            return
        self._pending.append(normalized)

# Data Pipeline

## Status: G2B collector implemented and live-verified (Phase 2). BizInfo/K-Startup
land in Phase 6; AI analysis and match scoring in Phase 4/5 - see below for what's
actually built vs. still just interface/design.

## Collector interface

`worker/collectors/base.py:BaseCollector[TNormalized]` - subclassed once per source.

```python
class BaseCollector[TNormalized: BaseModel](ABC):
    def collect(self) -> Iterable[RawRecord]: ...      # may raise CollectorError
    def normalize(self, raw: RawRecord) -> TNormalized: ...
    def validate(self, normalized: TNormalized) -> bool: ...
    def persist(self, normalized: TNormalized) -> None: ...
    def run(self) -> CollectorRunResult: ...            # template method, see below
```

`run()` isolates per-record failures (bad record -> logged + counted in
`CollectorRunResult.errors`, batch continues). A `collect()` failure (network down, rate
limited) is the caller's problem - the scheduler must catch it per-job so one source
outage doesn't cancel other jobs (`worker/scheduler/`). Every collector must handle:
timeout, retry, pagination, empty response, malformed response, rate limiting, duplicate
response, network failure, unexpected schema.

## G2B collector (implemented, Phase 2)

`worker/collectors/g2b.py:G2BCollector` - `getBidPblancListInfoServc` (용역/service bid
announcements only; IT/SI projects are classified there, not 물품/공사/외자).

```
http://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServc
```

Two live gotchas worth knowing before touching this file (full detail in
`docs/TROUBLESHOOTING.md`):

- The path has an `ad/` segment that's easy to miss - without it the API returns a
  generic "service does not exist" error, not a 404.
- data.go.kr issues an already-URL-encoded ("Encoding") service key. Passing it through
  `httpx`'s param encoding (or `curl --data-urlencode`) double-encodes it and auth fails
  with a misleading "unregistered service key" error - append it to the URL as-is.

Pagination, retry (timeout/transport errors and HTTP 429), and duplicate-response
dedup are handled in `collect()`; a missing/unrecognized response schema, non-JSON body
(HTML error pages happen), and the legacy `OpenAPI_ServiceResponse` error envelope are
all handled in `parse_response_body()` without crashing. `max_records` exists
specifically for small live-mode test runs (section 46 of the original spec) - never set
it in the scheduled job (`worker/jobs/g2b_job.py`, hourly, 2-hour lookback window).

Verified live end-to-end (2026-08-07): real API -> real `opportunities` table, Korean
text intact, re-running the same window upserts in place (row count unchanged, only
`updated_at` moves) - see `docs/VERIFICATION_REPORT.md`.

## Idempotency

Unique key: `(source, external_id)` - for G2B, `{bidNtceNo}-{bidNtceOrd}`. Re-running a
collector for the same window must not create duplicate `opportunities` rows - it
upserts. `content_hash` (sha256 of the canonicalized raw item) is stored on every row;
change detection using it to skip re-analysis is Phase 4 work (nothing consumes it yet).

## RAW -> NORMALIZED -> ANALYZED -> MATCHED

The AI stage (`ANALYZED`) never overwrites `RAW` or `NORMALIZED` columns - each stage is
its own set of columns/tables so a bad AI run is recoverable by re-analyzing the same
normalized input.

## Project filtering (before AI)

Rule filter runs before any LLM call and buckets every `NORMALIZED` project into
`NON_IT` / `LIKELY_IT` / `UNKNOWN`. Only `LIKELY_IT` and a sampled subset of `UNKNOWN` go
to AI analysis - the full 나라장터 feed is never sent to Ollama.

## AI provider interface

`worker/ai/base.py:AIProvider` - `classify_project`, `extract_project`,
`summarize_project`, `extract_support_conditions`. `worker/ai/schemas.py:ProjectAnalysis`
is the structured output contract (mirrors the shape in the original spec: project_type,
technologies[{name, confidence, evidence}], required_roles, requirements, risks,
summary, plus model/model_version/prompt_version/analyzed_at).

AI output is never written to the DB unvalidated. Validation failure gets exactly one
repair attempt; a second failure sets `analysis_status = FAILED` and stops - no infinite
retry.

## Match Engine (rule-based, no LLM)

100 points total: Technology 30, Business Type 20, Budget 15, Experience 15,
Qualification 10, Region 5, Schedule 5. Total and per-category scores are both stored.
Boundary cases that must have explicit tests once implemented: 49/50/64/65/79/80/100.

## Support eligibility

Status: `ELIGIBLE` / `CHECK_REQUIRED` / `NOT_ELIGIBLE`, computed by rule (region, 업력,
company size, business field, entity type, application window). Only free-text
conditions that don't fit the rule schema get AI structuring.

## Failure isolation

- G2B failure -> existing data stays, other sources keep working.
- Ollama failure -> announcement is shown without AI analysis, not hidden.
- BizInfo failure -> Project Radar is unaffected.
- Market aggregation failure -> last successful aggregation is shown, not a blank page.

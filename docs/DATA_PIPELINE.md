# Data Pipeline

## Status: G2B collector (Phase 2), Project UI (Phase 3), and AI analysis (Phase 4) all
implemented and live-verified. BizInfo/K-Startup land in Phase 6; match scoring in
Phase 5 - see below for what's actually built vs. still just interface/design.

## Project UI (implemented, Phase 3; category/analysis display added Phase 4)

`apps/web/src/app/(app)/opportunities/` reads `opportunities` (+ an embedded
`project_analyses` on the detail page) directly (RLS: any authenticated user can
`select`) - no API route needed, Server Components query Supabase straight from
`apps/web/src/lib/opportunities.ts`. List page: paginated (20/page), substring search
over title/organization (`pg_trgm` + `ilike` - see `docs/DATABASE.md`'s Phase 3 gotchas
for why not plain full text search), a category filter tab (전체/IT 관련/IT 무관/미분류)
and badge per row, empty/loading/error states via Next's
`loading.tsx`/`error.tsx`/`not-found.tsx` file conventions. Detail page: full field
breakdown, an "AI 분석" section when a `SUCCESS` analysis exists (project type,
technology chips with confidence, roles/requirements/risks), and a link back to the
나라장터 원문.

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
`worker/repositories/project_analyses.py:get_pending_opportunities()` compares it against
`project_analyses.analyzed_content_hash` to skip re-analysis when nothing changed -
verified live: a second `analyze_job.run()` against unchanged data made zero Ollama
calls.

## RAW -> NORMALIZED -> ANALYZED -> MATCHED

The AI stage (`ANALYZED`) never overwrites `RAW` or `NORMALIZED` columns - each stage is
its own set of columns/tables so a bad AI run is recoverable by re-analyzing the same
normalized input.

## Project filtering (implemented, Phase 4)

`worker/ai/rule_filter.py:classify(title)` buckets every G2B title into `NON_IT` /
`LIKELY_IT` / `UNKNOWN` - called from `G2BCollector.normalize()` at collection time
(not a separate job), so `opportunities.category` is set the moment a row is written.
Keyword-based, biased toward `LIKELY_IT` on purpose: a false positive costs one wasted
~60s Ollama call, a false negative silently drops a real IT opportunity, which is the
worse failure for a product whose job is finding IT projects. Verified against every
title in `fixtures/g2b/bid_list_servc_sample.json` (real data) before shipping,
including a case where data.go.kr's own official classification (`pubPrcrmntLrgClsfcNm`)
mis-tagged a cybersecurity cert-testing project as "학술연구 및 기타 서비스" - the keyword
filter catches it anyway. `UNKNOWN` sampling for AI analysis is NOT_IMPLEMENTED - only
`LIKELY_IT` reaches Ollama right now.

## AI provider (implemented, Phase 4: OllamaProvider)

`worker/ai/base.py:AIProvider` - `classify_project`, `extract_project`,
`summarize_project`, `extract_support_conditions`. `worker/ai/schemas.py` splits this
into `ProjectExtraction` (what the LLM actually generates - no provenance) and
`ProjectAnalysis` (`ProjectExtraction` + `model`/`model_version`/`prompt_version`/
`analyzed_at`, added by the caller, not the provider).

`worker/ai/ollama_provider.py:OllamaProvider` is the only implementation. It calls
Ollama's `/api/generate` with `format: <json_schema>` (JSON-schema-constrained decoding,
not just `format: "json"`) - verified live before writing the provider: a real call
against `qwen3:8b` for a real G2B title returned valid, schema-conforming JSON with
correct Korean text on the first try. `classify_project`/`summarize_project` delegate to
`extract_project` rather than using separate prompts, since nothing in this pipeline
calls them standalone yet - building two more untested prompt/schema pairs for code paths
nothing exercises wasn't worth it. `extract_support_conditions` raises
`NotImplementedError` (Phase 6).

AI output is never written to the DB unvalidated. Validation failure gets exactly one
repair attempt (a second prompt including the validation error); a second failure raises
`AIProviderError`, and the job records `project_analyses.status = FAILED` with the error
message - no infinite retry. The repair path itself is covered by offline tests
(`worker/tests/test_ollama_provider.py`) with a mocked transport, not live - reliably
forcing a real model to produce invalid JSON on demand isn't practical, so the live
verification covers the success path and the mocked tests cover repair/failure.

**Known limitation, not a bug**: analysis quality is limited by input richness. The
worker only sends title + organization + budget to the model (no full announcement body
- G2B's list API doesn't return long-form specs, only links to attached PDF/HWP
documents, and parsing those is out of MVP scope per the original spec's exclusions).
Real live output for "양자내성암호 시범전환 사업 공인시험 위탁" came back with
`technologies: []` and a summary that just restates the title - correct behavior for
thin input, not a broken extraction. Richer analysis would require fetching and parsing
the linked spec documents, which is future work, not Phase 4 scope.

Also observed live: the first Ollama call after the service starts is slow (~61s, cold
model load); subsequent calls with the model already resident in memory were much faster
(~9s in the same session). `REQUEST_TIMEOUT_SECONDS = 300` in `ollama_provider.py`
accounts for the cold-start case.

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

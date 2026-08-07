# Data Pipeline

## Status: interfaces only (Phase 0). Concrete collectors land in Phase 2 (G2B) and
Phase 6 (BizInfo, K-Startup).

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

## Idempotency

Unique key: `(source, external_id)`. Re-running a collector for the same hour must not
create duplicate `opportunities` rows - it upserts. Change detection uses
`content_hash` (hash of the normalized payload): if unchanged, the record is not sent
back through AI analysis.

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

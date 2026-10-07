# Support programs: 기업마당(BizInfo) + cross-source dedupe

Phase 6 remainder (2026-10-07). K-Startup collection is described in
`docs/DATA_PIPELINE.md#support-programs-k-startup-implemented-2026-08-10`; this file covers
what was added on top of it. Status: **code, tests and migration written, API verified with
a real key; not yet deployed** - see "Turning it on" at the bottom.

## Source decision (measured 2026-10-07)

Three candidate sources were compared on real data before writing anything: 157 open
K-Startup rows from `support_programs`, the public 기업마당 list page (1,442 currently
posted), and the public 중소벤처24 list (1,554 currently open). Titles were normalized and
matched with the rule in "Dedupe" below.

| Pair | Overlap |
| --- | --- |
| K-Startup (open) found in 기업마당 | 16 of 157 (~10%) with the final rule - 17 기업마당 rows, one program is posted there twice |
| K-Startup (open) found in 중소벤처24 | 5 of 157 strictly |
| 기업마당 found in 중소벤처24 | ~78% (1,134 of 1,442) |
| 중소벤처24 found in 기업마당 | ~78% (1,218 of 1,554) |

- K-Startup is mostly private incubators and university 창업보육센터 programs; it barely
  overlaps either aggregator, so it stays as its own source.
- 기업마당 and 중소벤처24 are largely the same pool. Only one of them is collected:
  **기업마당**, because it carries other ministries (과기정통부 etc.) and 지자체 programs,
  its key is applied for on the 기업마당 site itself, and it was already the planned Phase 6
  source.
- 중소벤처24 is **not** collected. Its unique ~22% is mostly 중기부 통합공고 split into
  sub-programs (지원기관 코드 SP99 "기타": 284 of 336). Its API token is issued by
  기정원(TIPA) on request, and the API has an IP allow-list error (code 14), which a home PC
  with a changing IP would hit. Worth revisiting only for its structured eligibility fields
  (업력·종업원수·매출액·지역·기업규모), which would feed Support eligibility - official
  spec: `portal.smes.go.kr/ione-gw/api/pblanc/list`, `중소벤처24_API개발가이드_V3`.
- IT relevance is similar in both aggregators (title keyword match ~9% of 기업마당, ~11%
  of 중소벤처24), so Support Radar gets noisier for IT/SI companies either way - an IT
  filter for support programs is a separate, open item.

## Collector - `worker/collectors/bizinfo.py`

- `GET https://www.bizinfo.go.kr/uss/rss/bizinfoApi.do?crtfcKey=...&dataType=json&searchCnt=5000`
  ([spec](https://www.bizinfo.go.kr/apiDetail.do?id=bizinfoApi)). One request returns
  everything currently posted - no pagination.
- Key: `BIZINFO_API_KEY`, BizInfo's own `crtfcKey` (기업마당 > 활용정보 > 정책정보 개방 >
  지원사업정보 API > 사용신청). A data.go.kr key does not work. Without a key the API
  answers HTTP 200 `{"reqErr": "인증키를 입력해주세요."}` (verified live) - parsed as an error.
- **Verified with a real key 2026-10-07** (read-only call, nothing written):
  `{"jsonArray": [...]}` with 1,443 items = `totCnt` (a number, on every item), so the
  response counts as complete; every item has `pblancId`/`pblancNm`/`pblancUrl`
  (absolute, already the `/sii/siia/selectSIIA200Detail.do` form)/기관/지원분야/
  `trgetNm`/`bsnsSumryCn` (HTML); 신청기간 is `YYYY-MM-DD ~ YYYY-MM-DD` (502) or a phrase.
  All 1,443 normalize and validate; 991 get a region, 49 are flagged investment-linked.
  The official spec page shows other forms (`{"jsonArray": {"item": [...]}}`,
  `20220727 ~ 20220930`, RSS-style names) - still accepted as fallbacks. Recorded sample:
  `fixtures/bizinfo/api_response_sample.json` (5 items, contact fields removed).
- The key is in the query string and httpx error messages quote the URL, so the collector
  masks the key in every error it raises or logs.
- Mapping: `organization` = 수행기관 unless it is the placeholder "직접수행"/"기초자치단체",
  then 소관기관; `department` = 소관기관 (the detail page labels it 소관기관 for BizInfo rows);
  `category` = 지원분야 대분류; `region` = the title's leading `[지역]` tag, only when every
  part is a known region word (e.g. `[서울ㆍ인천ㆍ경기]` -> `서울·인천·경기`; untagged ->
  null, never guessed as 전국); `application_period_text` = 신청기간 as written.
- Dates: only real date ranges become `application_start/end`. 65% of postings (942 of
  1,442) say "예산 소진시까지", "상시 접수", "세부사업별 상이" etc. - those keep null dates
  and the list shows the text instead of "일정 미정".
- `recruiting`: true for everything currently posted unless its end date has passed. After
  a **complete** response (item count matches `totCnt`, list non-empty), the job sets
  `recruiting=false` on BizInfo rows that are no longer listed. A truncated or empty
  response skips that step, so an upstream hiccup can't close every announcement.

## Dedupe - `worker/dedupe/support_programs.py`

A 기업마당 row that repeats an open K-Startup announcement gets `duplicate_of` = the
K-Startup row's id; `/support` lists only `duplicate_of is null`. K-Startup is the row kept
(original posting, more fields). Rows are never deleted - collection only upserts, so a
deleted row would come back next hour, and `raw_payload` is the evidence if a match is wrong.

Exact title matching found 0 of the 17 real duplicates: 기업마당 adds `[지역]` and "공고",
K-Startup wraps names in 「」 or moves "4차" to the end, spacing/punctuation differ. Rule:
1. normalize: drop leading `[...]` tags, all non-word characters, a trailing
   (재/수정/변경/연장)공고; lowercase;
2. the set of numbers in both titles must be equal (separates "2차" from "3차" of a
   recurring program, which otherwise score 0.85+);
3. both have a deadline: same day and bigram overlap coefficient >= 0.8;
   either lacks one: overlap >= 0.9 **and** Jaccard >= 0.65.

All 18 candidate pairs in the measurement were read by hand: 17 same announcement, 1 not
(기업마당 "스타트업 법률지원사업 참여기업 모집" vs a K-Startup row for one city's 법률상담회
under that program - overlap 0.95, Jaccard 0.59). The rule keeps the 17 and drops the 1;
both sets are regression tests in `worker/tests/test_support_dedupe.py`. Known miss: the
same contest listed with different deadlines on the two sites (10-09 vs 10-11) stays
visible twice.

The pass runs at the end of every BizInfo job (`worker/jobs/bizinfo_job.py`) over open
K-Startup rows (`application_end >= today` or `recruiting`) and recruiting BizInfo rows,
and writes only rows whose mark changes, including clearing stale marks. A K-Startup row
collected between BizInfo runs is picked up within the hour.

## Schema - `supabase/migrations/20261007100000_bizinfo_support_programs.sql`

- `source` check widened to `('kstartup', 'bizinfo')` (drops `support_programs_source_check`
  without `if exists` on purpose: a different name fails loudly instead of leaving the old
  constraint).
- `application_period_text text`, `duplicate_of uuid references support_programs(id) on
  delete set null`, plus `duplicate_of is distinct from id`.

## Web

`/support`: hides `duplicate_of` rows, shows each row's source under its title, adds a
source filter (모든 출처 / K-Startup / 기업마당), and shows 신청기간 text when there is no
deadline date (`apps/web/src/lib/support-display.ts`). Detail page: source-aware labels
and "기업마당 원문 보기" link.

## Turning it on (order matters)

1. Apply the migration: `npx supabase db push --dry-run`, then `npx supabase db push`.
   **Before** deploying the web app - it selects the new columns, so `/support` errors
   against the old schema.
2. Push to `master` (Vercel deploys `apps/web`).
3. Put the key in the vault and restart the worker:
   `vault.py set BIZINFO_API_KEY --file bizradar/.env.worker`, `pm2 restart bizradar-worker`.
   Until then the job logs `bizinfo job skipped` every hour and touches nothing.
   The worker runs from this local checkout, not from what is pushed - a restart (or a
   PC reboot) with the key in the vault but **before step 1** makes every hourly run fail
   all ~1,450 upserts (source check + missing columns). Nothing is corrupted, but the log
   fills with errors until the migration is applied.
4. After the first run: the log line `bizinfo job finished` should show `collected` ~1,450,
   `failed` 0, `complete` true, followed by `cross-source dedupe finished` (~17 marked).

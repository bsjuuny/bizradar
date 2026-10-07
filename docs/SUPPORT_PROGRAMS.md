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
- The key is in the query string. httpx error messages quote the URL (raw or
  percent-encoded), so the collector masks both forms in every error it raises or logs.
  httpx also logs every request URL at INFO - `worker/logging_config.py` holds httpx and
  httpcore at WARNING, and redacts `serviceKey=`/`crtfcKey=` values from every log line it
  formats (message, extras, tracebacks - httpx's HTTPStatusError text quotes the URL too).
  Before that fix the 12:08 and 13:08 runs on 2026-10-07 wrote the key into the PM2 out
  log (and the data.go.kr serviceKey has been landing there all along).
- Retries (transport errors, 5xx) wait 2 s then 5 s; 4xx is not retried. `content_hash`
  leaves out `inqireCo` (view count) and `totCnt` (list size), which change every fetch.
- Only changed rows are written: the stored `(content_hash, recruiting)` is read once per
  run (if that read fails, every row is written) and a posting that matches is skipped -
  nearly all of the ~1,450 are, every hour. `content_hash` covers the stable payload *and*
  every derived column except `recruiting`, so a change to `normalize()` or to a rule
  reaches every listed row on the next run; only closed rows (never re-sent) need
  reclassify. The job logs `written` (actually sent) next to `persisted` (accepted,
  including the skipped `unchanged`).
- Scheduled at a 35-minute offset from the top-of-the-hour job group, to spread load. At
  :08 alongside the others, 26-30 of ~1,450 upserts per run failed with the worker's
  long-standing intermittent `WinError 10035`. The fixes for that are writing only changed
  rows (above) and one Supabase client per thread (`get_service_client()` in
  `worker/repositories/opportunities.py`; it used to be one process-wide client shared by
  concurrent jobs).
- `source_url` must be an http(s) URL on bizinfo.go.kr; anything else falls back to the
  detail page built from the id (it becomes the "원문 보기" link).
- Mapping: `organization` = 수행기관 unless it is the placeholder "직접수행"/"기초자치단체",
  then 소관기관; `department` = 소관기관 (the detail page labels it 소관기관 for BizInfo rows);
  `category` = 지원분야 대분류; `region` = the title's leading `[지역]` tag, only when every
  part is a known region word (e.g. `[서울ㆍ인천ㆍ경기]` -> `서울·인천·경기`; untagged ->
  null, never guessed as 전국); `application_period_text` = 신청기간 as written.
- Dates: only real date ranges become `application_start/end`. 65% of postings (942 of
  1,442) say "예산 소진시까지", "상시 접수", "세부사업별 상이" etc. - those keep null dates
  and the list shows the text instead of "일정 미정".
- `recruiting`: true for everything currently posted unless its end date has passed. After
  a **complete** response the job sets `recruiting=false` on BizInfo rows that are no
  longer listed. Complete means provably whole: `totCnt` present and readable (a number;
  "1,443" tolerated) and at least that many *distinct* ids received. A missing totCnt, a
  short or empty list, or repeated/missing ids all skip the closing step, so an upstream
  hiccup can't close announcements that are still open.
- Entity decoding (`decode_entities` in `worker/collectors/base.py`) only expands
  `;`-terminated references; `html.unescape` alone also expands legacy forms without `;`
  and turns a URL's `&notice=1` into `¬ice=1`. Named references must be exact HTML5
  names ("&notice;" stays as is). URL fields are never decoded.
- 사업개요 HTML: `<br>` (any attributes) and closing block tags become line breaks, table
  cells end with a space, other tags vanish without a gap.

## Dedupe - `worker/dedupe/support_programs.py`

A 기업마당 row that repeats an open K-Startup announcement gets `duplicate_of` = the
K-Startup row's id. That is a pairing, not a hide flag: whether `/support` hides the copy is
decided per view at query time (see "Web"). K-Startup is the row kept
(original posting, more fields). Rows are never deleted - collection only upserts, so a
deleted row would come back next hour, and `raw_payload` is the evidence if a match is wrong.

Exact title matching found 0 of the 17 real duplicates: 기업마당 adds `[지역]` and "공고",
K-Startup wraps names in 「」 or moves "4차" to the end, spacing/punctuation differ. Rule:
1. normalize: drop leading `[...]` tags, all non-word characters - including 'ㆍ'
   (U+318D), which the regex engine treats as a Hangul letter, not punctuation - and a
   trailing (재/수정/변경/연장)공고; lowercase;
2. the set of numbers in both titles must be equal (separates "2차" from "3차" of a
   recurring program, which otherwise score 0.85+), after unifying "1,000" -> "1000" and
   "'26년" -> "2026년";
3. regions, when both are specific, must share a 시·도 (권역 words such as 수도권 are
   expanded; 전국/unknown never block). Generic titles recur in every region - a Seoul
   incubator's "2026년 창업보육센터 입주기업 모집" and "[대전] ... 모집 공고" score 1.0/1.0.
   All 17 measured pairs agree on region or have one side 전국/untagged. Organization names
   are not compared: they differ in 7 of the 17 true pairs;
4. both have a deadline: same day, bigram overlap coefficient >= 0.8 and Jaccard >= 0.55
   (the same day alone isn't proof - month-end deadlines are common, and a short generic
   title is nearly a subset of a longer unrelated one; weakest true dated pair: 0.62);
   either lacks one: overlap >= 0.9 **and** Jaccard >= 0.65.

All 18 candidate pairs in the measurement were read by hand: 17 same announcement, 1 not
(기업마당 "스타트업 법률지원사업 참여기업 모집" vs a K-Startup row for one city's 법률상담회
under that program - overlap 0.95, Jaccard 0.59). The rule keeps the 17 and drops the 1;
both sets are regression tests in `worker/tests/test_support_dedupe.py`. Known miss: the
same contest listed with different deadlines on the two sites (10-09 vs 10-11) stays
visible twice.

The pass runs at the end of every BizInfo job run (`worker/jobs/bizinfo_job.py`) - also
when collection was skipped (no key) or failed. It pairs recruiting 기업마당 rows with open
K-Startup rows, and diffs against the marks of every 기업마당 row that is recruiting *or*
still carries a mark - so a closed copy's mark (set while it was open, or by an older
rule) is cleared rather than kept forever. It writes only rows whose mark changes.
"Open" K-Startup rows are read from
`support_programs_listing.is_open` - the single SQL definition of 모집 중
(`support_program_is_open()`), which the web filters on too.
A K-Startup row collected between BizInfo runs is picked up within the hour.

## Schema - `supabase/migrations/20261007100000_bizinfo_support_programs.sql`

- `source` check widened to `('kstartup', 'bizinfo')` (drops `support_programs_source_check`
  without `if exists` on purpose: a different name fails loudly instead of leaving the old
  constraint).
- `application_period_text text`, `duplicate_of uuid references support_programs(id) on
  delete set null`, plus `duplicate_of is distinct from id`.

## Web

`/support` reads the `support_programs_listing` view
(`supabase/migrations/20261007130000_support_programs_listing.sql`): every row plus its
`is_open` and, for a paired 기업마당 copy, the original's current state and filter columns
(`original_open`, `original_end`, `original_title`, `original_organization`,
`original_category`, `original_it_related`, `original_investment_linked`).

"모집 중" anywhere - this page, "7일 안에 마감", the detail page's 모집상태, the worker's
pairing - is `is_open`, i.e. the SQL function `support_program_is_open()`: the source says
recruiting (or doesn't say, and gives a deadline), and there is no deadline or it hasn't
passed (Asia/Seoul). One definition, so they can't drift.

A copy is hidden exactly when its original is in the same result: the original is open
and passes every other active filter too - the deadline window, IT, investment, 지원분야
and the search term are evaluated on the `original_*` columns
(`copyHidingFilter` in `apps/web/src/lib/support-filters.ts`). With a 출처 filter nothing
is hidden: original (K-Startup) and copy (기업마당) are never in the same result. A closed
original never hides its open copy. All of it is evaluated at query time, so a copy
reappears the moment its original closes or passes its deadline - not at the next hourly
dedupe. A page number past the end (old link, shorter list) falls back to page 1.

Each row shows its source under the title. The deadline column wraps (it can hold long
신청기간 text) and shows "마감" for a closed
posting (`recruiting=false`), else the D-day, else the 신청기간 text when there is no
deadline date, else "일정 미정" (`apps/web/src/lib/support-display.ts`). Detail page:
source-aware labels and "기업마당 원문 보기" link. Search terms are quoted for PostgREST's
`or=()` (`apps/web/src/lib/postgrest.ts`); `*`, which PostgREST turns into `%` with no
escape, becomes the single-character wildcard `_`.

Filters (all plain links / GET params, no client JS - same pattern as `/opportunities`):

| Filter | Param | Meaning |
| --- | --- | --- |
| 상태 (default 모집 중) | `status=open\|closing\|all` | open = `is_open`: `recruiting` and (no deadline or deadline >= today, Asia/Seoul) - `support_program_is_open()` in SQL. The date check is there because K-Startup's own 모집 flag lags its deadline (16 rows on 2026-10-07). closing = open with a deadline within 7 days. all = including closed. |
| 출처 | `source=kstartup\|bizinfo` | |
| IT 관련만 | `it=1` | `it_related` (see "IT filter") |
| 투자연계형만 | `investment=1` | `investment_linked` |
| 지원분야 | `field=<key>` | One shared grouping over both sources' category values (`SUPPORT_FIELDS`): 자금·융자, 기술개발, 창업·사업화, 공간·보육, 판로·수출, 경영·컨설팅·교육, 인력, 행사·네트워크, 기타. |

Why "모집 중" is the default: of 2,493 visible rows on 2026-10-07, 910 were closed
K-Startup postings; they sorted last but still made up most of the pages and the count.

The 지원분야 groups map raw category strings, which must match the DB character for
character (the middle dot is 'ㆍ' U+318D). All 18 values in use on 2026-10-07 map to exactly
one group (checked against the DB and in `support-display.test.ts`). A category a source
introduces later belongs to no group: such rows still list, they just never match a
지원분야 chip until it's added.

## IT filter - `worker/ai/support_it_filter.py`

`it_related` = the program's subject is IT (SW·AI·데이터·클라우드·정보보호·ICT·블록체인·
게임·핀테크, and DX·AX·스마트공장 programs whose vendors are IT/SI companies). Title-only
keyword rule, computed at collection like `investment_linked`. Separate from the G2B
procurement filter (`rule_filter.py`) because several of its keywords mean something else
in support-program titles - measured on all 1,599 open programs (2026-10-07):
"IoT/사물인터넷" = environmental-emission sensors for small workplaces (all 7 hits),
"전산" = substring of 안전산업/가전산업, "플랫폼/온라인/디지털" = 소상공인 online-sales
support, "로봇/반도체" = hardware. A trailing parenthetical that names a funding project
("...사업"/"...구축", e.g. "(AI 빅데이터 기반 의료바이오 첨단기기 연구제조센터 구축사업)" on a
medical-device program) is ignored unless it names an IT-industry program or an IT voucher
("(AI바우처 지원사업)"); other trailing parentheticals count, since K-Startup puts the field
there ("(AI 분야)"). Full-width parentheses are treated the same. "게임체인저" is an
exception (policy buzzword, not the game industry).

Result: 155 of 1,599 open programs. Every hit was read; then the 308 non-hits with weaker
words were read for misses, which added 디지털혁신, 디지털 품질(SW testing), 가명정보,
위치정보, 개인정보, 전자문서, 스마트시티, AIoT, ETRI, ChatGPT, 코딩 (17 programs). The 98 hits
among closed K-Startup rows were read as well. Tests use those real titles.

**Changing the rule (or any collector text handling) requires a reclassify run** - the
column is written at collection time only, and K-Startup re-fetches just its newest 500:

```
python -m worker.jobs.support_reclassify --dry-run
python -m worker.jobs.support_reclassify
```

It re-runs each row's own collector `normalize()` on the stored `raw_payload` (K-Startup
and 기업마당 alike) and writes only derived columns that changed (`DERIVED_COLUMNS` in
`worker/repositories/support_programs.py`; never recruiting, dates or `duplicate_of`). It
loads the shared vault first, like the PM2 entrypoint (`worker/secrets_loader.py`).

Same change set: K-Startup's API HTML-escapes some fields (`&apos;`, `&amp;` - 28 stored
rows, e.g. category "기술개발(R&amp;D)", seen in its raw_payload, not introduced by us).
The collector now decodes them; the reclassify run fixes the stored rows.

## Turning it on (order matters)

1. Apply the migration: `npx supabase db push --dry-run`, then `npx supabase db push`.
   **Before** deploying the web app - it selects the new columns, so `/support` errors
   against the old schema.
2. Push to `master` (Vercel deploys `apps/web` - not Railway as AGENTS.md and
   INFRASTRUCTURE.md still say; the 2026-10-07 pushes show up as Vercel "Production"
   deployments in the GitHub deployments API).
3. Put the key in the vault and restart the worker:
   `vault.py set BIZINFO_API_KEY --file bizradar/.env.worker`, `pm2 restart bizradar-worker`.
   Until then the job logs `bizinfo job skipped` every hour and touches nothing.
   The worker runs from this local checkout, not from what is pushed - a restart (or a
   PC reboot) with the key in the vault but **before step 1** makes every hourly run fail
   all ~1,450 upserts (source check + missing columns). Nothing is corrupted, but the log
   fills with errors until the migration is applied.
4. After the first run: the log line `bizinfo job finished` should show `collected` ~1,450,
   `failed` 0, `complete` true, followed by `cross-source dedupe finished` (~17 marked).

Steps 1-4 were done 2026-10-07. The changes after it (filters, review fixes) add two
migrations - `20261007120000_support_programs_it_related.sql` and
`20261007130000_support_programs_listing.sql` - and roll out the same way:

1. `npx supabase db push` (both; the second also creates the `support_program_is_open()`
   function) - before the web deploy (it reads the view and `it_related`) **and** before any worker restart (the collectors now write `it_related`;
   against the old schema every upsert fails).
2. `python -m worker.jobs.support_reclassify --dry-run`, then without `--dry-run` - fills
   `it_related` and re-normalizes stored text (K-Startup entities, whitespace); until then
   "IT 관련만" shows nothing.
3. Push to `master`, then `pm2 restart bizradar-worker`.

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
- Only changed rows are written: the job reads the stored `(id, content_hash,
  recruiting)` once per run - for rows seen in the list within 30 days (every listed row,
  and every recruiting row the closing step may close), not the ever-growing closed
  history; bounded even if the closing step stalls for weeks - and hands it to the collector (if that read fails, every
  row is written) and to the closing step. A posting that matches is skipped - nearly all
  of the ~1,450 are, every hour - and the changed ones are upserted 100 per request
  (`BizInfoCollector.run`; a failing chunk is retried row by row, and after 5 single-row
  failures in a row the rest of the run's writes are given up - that is the database,
  not the rows), so even a rule change that touches every listed row is ~15 requests. Listed rows get their `last_seen_at` refreshed in chunks
  of 100 once it is a day old (not hourly: every update also bumps `updated_at` and leaves
  a dead tuple), whatever `persist()` did with them - a row whose upsert keeps failing is
  still listed. `content_hash` covers the stable payload *and*
  every derived column except `recruiting`, so a change to `normalize()` or to a rule
  reaches every listed row on the next run; only closed rows (never re-sent) need
  reclassify. The job logs `written` (actually sent) next to `persisted` (accepted,
  including the skipped `unchanged`).
- Scheduled at :35 every hour (a cron trigger, so a worker restart doesn't push it back),
  away from the top-of-the-hour job group, to spread load. At
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
- Dates: only real "start ~ end" date ranges become `application_start/end` (stored as
  UTC midnight with an explicit offset). Read forms: `2026-10-01`, `2026.10.1.`,
  `2026. 10. 2.(목) 09:00`, `2026/10/01`, `20261001`; an end date may omit its year
  (then it takes the start's year, or the next one when it falls before the start - "12.
  1. ~ 1. 15." - but only for a window of up to 183 days: "10. 20. ~ 10. 2." is a typo,
  not a year-long window, and stays text). Also accepted, though none of the 1,473 stored
  texts of 2026-10-08 uses them: a full-width tilde, "18시", a trailing remark in
  parentheses.
  65% of postings (942 of 1,442) say "예산 소진시까지", "상시 접수", "세부사업별 상이" etc.,
  and an open end ("2026-10-01 ~") has no deadline either - those keep null dates, stay
  open until 기업마당 delists them (or they go 3 days unseen, see `last_seen_at`), and the
  list shows the text instead of "일정 미정".
- `recruiting`: true for everything currently posted unless its end date has passed. After
  a **complete** response the job sets `recruiting=false` on BizInfo rows that are no
  longer listed. Complete means provably whole: `totCnt` present and readable (a number;
  "1,443" tolerated) and at least that many *distinct* ids received. A missing totCnt, a
  short or empty list, or repeated/missing ids all skip the closing step, so an upstream
  hiccup can't close announcements that are still open.
- `last_seen_at` (always set for 기업마당 rows - a check constraint): when the posting was
  last in a response (upserts set it; skipped rows
  are refreshed by the job), whether or not the response was complete. The closing step
  can stall - an expired key, or responses that keep coming back incomplete - and for the
  65% of postings without a deadline date, leaving the list is the only way they close.
  So `is_open` stops counting a date-less row as open once it has gone 3 days unseen
  (dated rows close on their date - a worker PC that was off for a long weekend must not
  turn a posting with weeks to go into 마감). Per row: one
  missing or repeated id in a response affects that posting only. K-Startup rows (and
  only K-Startup rows have it null (a check constraint requires it on 기업마당 rows), and
  the rule skips them.
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
3. a specific region on either side must be matched by a specific region on the other
   that shares a 시·도 (권역 words such as 수도권 are expanded). Generic titles recur in
   every region - a Seoul incubator's "2026년 창업보육센터 입주기업 모집" and "[대전] ...
   모집 공고" score 1.0/1.0. 전국 is no match for a specific region: it is K-Startup's
   default (113 of ~175 open rows, local incubators included). Of the 17 measured pairs, 6
   name the same region on both sides and 11 have none on either (기업마당 untagged,
   K-Startup 전국); none pairs a region with 전국, and re-running the rule on the live rows
   gave the same 17. Organization names are not compared: they differ in 7 of the 17 true
   pairs;
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
when collection was skipped (no key) or failed; only a worker without Supabase settings
skips it. It pairs open 기업마당 rows with K-Startup rows that are open or closed within
the last 30 days (`plan_duplicate_marks`) - so a copy first collected just after its
original closed still pairs; with the 30-day window the live data of 2026-10-08 gives
the same 17 pairs.
A pair stays paired after either side closes, as long as the two titles still match
under the current rule - every marked row is re-checked against its original each run,
so a rule change clears marks that no longer hold, and only a strictly better-scoring
original takes a mark over. Un-pairing on close would list the program twice under "마감 포함 전체". It
writes only rows whose mark changes, one request per distinct value. "Open" is `is_open`. A K-Startup row collected between BizInfo runs is picked up within the
hour.

A pairing never changes either row's 모집 status. It is a fuzzy title match; if it were
wrong and a copy inherited its original's closing, a program 기업마당 still lists as open
would read 마감 - and for a radar a missed opportunity costs more than a duplicate line.
(Tried and reverted on 2026-10-08.) So a date-less copy ("예산 소진시까지") whose K-Startup
original has passed its deadline stays 모집 중, as 기업마당 itself shows it; the listing
then shows the copy for the pair (below).

## Schema - `supabase/migrations/20261007100000_bizinfo_support_programs.sql`

- `source` check widened to `('kstartup', 'bizinfo')` (drops `support_programs_source_check`
  without `if exists` on purpose: a different name fails loudly instead of leaving the old
  constraint).
- `application_period_text text`, `duplicate_of uuid references support_programs(id) on
  delete set null`, plus `duplicate_of is distinct from id`.

## Web

`/support` gets its rows from one SQL function, `list_support_programs(...)`
(`supabase/migrations/20261007130000_support_programs_listing.sql`, replaced by
`20261008100000_support_programs_open_status.sql`), which filters, hides
paired copies, orders and pages in one place:

1. `filtered`: the page's filters (status, IT, investment, 출처, 지원분야, search term)
   applied to every row of `support_programs`, projecting only the listed columns (not
   `raw_payload`/`description`). Bad arguments (an unknown status or 출처, a page size
   outside 1-100, a negative offset or window) raise an error rather than quietly returning
   something else - any signed-in user can call the RPC directly.
2. `visible`: an original and its copies (more than one is possible - a 공고 and its
   재공고 both repeating one K-Startup posting, seen once on 2026-10-08) form a group, and
   the rows of a group that are *in `filtered`* show as one: open rows first, then the
   original, then the lowest id. So both open -> the original; only a copy open -> that
   copy; all closed -> the original. Checked against `filtered` itself, not approximated:
   NULL columns on the original, or filters added later, can't make a program vanish (an
   earlier version re-applied each filter to copied `original_*` columns by hand, and a
   NULL there hid the copy with no original listed). With a 출처 filter only one side is
   in `filtered` (copies of the same original still collapse to one). Evaluated per
   query: under 모집 중 a copy shows as soon as its original closes, and under "마감 포함
   전체" the same row - the open one - stands for the group, so the views agree.
3. Order: open first, by nearest deadline (no deadline last); then unknown status
   (could still be open - not buried under the closed history); then closed, most
   recently closed first.
4. Search is `~*` with the regex literal prefix `***=` - the same literal, case-insensitive
   match as every other list (`apps/web/src/lib/postgrest.ts`); `%`, `_`, `*` are just
   characters.

"모집 중" anywhere - this page, "7일 안에 마감", the deadline column, the detail page's
모집상태, the worker's pairing - is the SQL function `is_open(support_programs)` (a
PostgREST computed column): the source says recruiting (or doesn't say, and gives a
deadline), and there is no deadline or it hasn't passed (Asia/Seoul,
`support_program_today_utc()`). One definition, so they can't drift. Each row's own data
only - pairing doesn't enter it (see Dedupe). With neither a 모집 status nor a deadline the answer
is NULL (unknown): not in 모집 중; the detail page's 모집상태 shows "—" and the deadline
column the 신청기간 text or "일정 미정" - never 마감 (no
such K-Startup row on 2026-10-08, but `_parse_yn` returns None for unknown values).

One more condition, for date-less rows whose source is a list of what is posted right
now (기업마당): `last_seen_at` must be under 3 days old (see "`last_seen_at`" above) -
otherwise such a posting would stay 모집 중 forever whenever the closing step stalls.

The 7-day "곧 마감" window: `CLOSING_SOON_DAYS` in `support-display.ts` is passed to the
function as `p_closing_days` and also labels the chip, so the label and the filter come
from the same constant (the SQL default of 7 is only for direct callers).

A page number past the end (old link, shorter list) shows the last page, and the pager
reports the page actually shown. Page numbers are capped at 100,000 so the offset stays
a valid SQL integer. Each row shows its source under the title. The deadline
column wraps (it can hold long 신청기간 text) and shows "마감" when the posting isn't open,
else the D-day, else the 신청기간 text when there is no deadline date, else "일정 미정"
(`apps/web/src/lib/support-display.ts`). Detail page: source-aware labels and "기업마당 원문
보기" link.

Filters (all plain links / GET params, no client JS - same pattern as `/opportunities`):

| Filter | Param | Meaning |
| --- | --- | --- |
| 상태 (default 모집 중) | `status=open\|closing\|all` | open = `is_open`: `recruiting` (or unknown with a deadline) and (no deadline or deadline >= today, Asia/Seoul), and for date-less 기업마당 rows seen in the list within 3 days (see above). The date check is there because K-Startup's own 모집 flag lags its deadline (16 rows on 2026-10-07). closing = open with a deadline within `CLOSING_SOON_DAYS` (7). all = including closed. |
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
`worker/repositories/support_programs.py` - including the application dates, which are
pure functions of the payload, so a `parse_period` fix reaches stored rows; never
recruiting, `last_seen_at` or `duplicate_of`). It
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

Steps 1-4 were done 2026-10-07. The filters and review fixes after it added
`20261007120000_support_programs_it_related.sql`, `20261007130000_support_programs_listing.sql`
(`last_seen_at`, `is_open()`, `list_support_programs()`) and two permission migrations
(`20261007140000`, `20261007150000`: EXECUTE revoked from PUBLIC and anon) - all applied
2026-10-07, reclassify run, pushed and the worker restarted.

`20261008100000_support_programs_open_status.sql` (the NULL "unknown" status, the 3-day rule for date-less rows only, the
pair-shows-its-open-row listing, the 기업마당 `last_seen_at` check) rolls out the same way:

1. `npx supabase db push` - before the web deploy. It only adds a check that every row
   already satisfies and replaces two functions with the same signatures, so applying it
   under the running worker and web is safe; the worker needs nothing new from it.
2. `python -m worker.jobs.support_reclassify --dry-run`, then without `--dry-run` - the
   IT filter now also reads "IT" and 정보기술 (2 K-Startup rows on 2026-10-08).
3. Push to `master`, then `pm2 restart bizradar-worker`.

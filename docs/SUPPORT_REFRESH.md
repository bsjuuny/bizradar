# Support refresh deployment gate

K-Startup hashes the raw API item; 기업마당 also hashes its derived fields, but closed
rows may never be fetched again. Both need a pass over stored `raw_payload` after rule
or normalization changes. The PM2 scheduler now checks a local checkpoint at startup
and gates **both** support collectors before each scheduled run. It never automatically
approves a production update. Until approval, those two jobs log an actionable error
and skip collection; G2B, matching and other jobs continue.

## What detects changes

`support_refresh.fingerprint()` hashes all worker implementation `.py` files (excluding
tests), including added helpers and the derived-column allowlist. This intentionally
errs on the side of a refresh for unrelated worker edits too. It works without git on
the deployment host. A checkpoint binds that fingerprint to the exact Supabase URL and
`DATA_MODE`. Missing, corrupt or mismatched checkpoints fail closed. Editing code under a
running process also blocks collection: restart to load the new implementation.

`.support-refresh/` is local, gitignored state. Keep it on the single PM2 worker host;
do not copy checkpoints between machines or recreate them by hand. A fresh checkout or
rollback to different code requires a fresh reviewed plan. Normal approved hourly runs
only check local files: no additional Supabase calls and no full-table scans. Existing
K-Startup/BizInfo hash skips, bulk writes and match-score optimizations are unchanged.

## First deployment and every subsequent worker change

Run in the repo root using the same Python environment and vault/environment as PM2.
The current project uses a local PC worker; a web deployment alone does not update it.
This change has **not** been applied to any live database or verified on that PC.

1. Confirm the intended host, branch/commit, Supabase project and `DATA_MODE`; ensure
   schema migrations for all `DERIVED_COLUMNS` are already present. Stop
   `bizradar-worker` on the host before pulling/replacing code or running this procedure.
   Pause any other support writers, including manual collector commands, on all hosts.
2. Deploy the code and dependencies, then prepare a **read-only database** plan:

   ```bash
   python -m worker.jobs.support_reclassify --dry-run --plan .support-refresh/plan.json
   ```

   This pages through all K-Startup and 기업마당 rows, including closed and old rows.
   The local JSON shows the target URL, mode, code fingerprint, database snapshot digest,
   counts per source and aggregate changed-column counts. It includes no credentials or
   raw payloads. Review these before approving the impact. `rows` means candidate changes;
   `unchanged`, `failed`, `scanned` and `written` are separate (`written=0` in a dry run).
   Fix invalid payloads/normalization failures before proceeding.
3. After reviewing the exact environment and impact, explicitly apply that plan:

   ```bash
   python -m worker.jobs.support_reclassify --apply-plan .support-refresh/plan.json
   ```

   It re-reads/re-derives first. Any code, target, mode, snapshot or count change rejects
   the plan **before writing**. Generate and review a new plan if it became stale.
   The existing bare command no longer applies implicitly. Complete success writes an
   atomic local checkpoint. Restart PM2 (`pm2 restart bizradar-worker`) and check its logs
   for the absence of `support refresh required` and for the next support collection.
4. To verify idempotency, prepare another dry-run plan: it should show zero candidate
   changes unless the source data changed. This read-only check does not erase the
   successful checkpoint. Do not apply a no-op plan unnecessarily.

## Writes, failures and concurrency

Only changed derived fields on changed rows are PATCHed. Identical changes share a
request, bounded to 100 IDs as in the existing repository; a unique 기업마당 hash can still
require a separate patch. No per-row version stamps, no hourly reclassification and no
new database migration are introduced. Recruiting, `last_seen_at`, `duplicate_of` and
raw payloads are untouched. Dedupe remains in the existing collection job.

The two scheduler wrappers and plan/apply commands use an exclusive per-target lock
file. Concurrent commands on this checkout cannot collect while a refresh is running.
This is **single-host coordination**, not a distributed database lock: other checkouts,
manual job calls and external writers must be paused during review/apply. The database
snapshot is checked before writing, not inside a database-wide transaction.

Normalization failures are reported separately from unchanged rows and prevent the
reviewed apply from writing anything. On an UPDATE error, the current chunk counts as
failed, later candidates as `pending`, and processing stops to avoid a storm of retry
requests. `written` counts rows in acknowledged successful chunks; a timeout may have
applied remotely, so inspect/replan rather than assuming rollback. No checkpoint is
written on failure. Some earlier chunks may already have succeeded; a new dry run
safely excludes them. Refresh is idempotent, not transactional across chunks.

A crashed process may leave a `.lock` file containing its PID. Confirm all relevant
processes have stopped before removing that lock; it is deliberately never auto-expired.
A blocked collector logs the cause instead of assuming completion. Preserve logs/plans
for the deployment review; never bypass the gate by writing a checkpoint manually.

## Offline verification

`worker/tests/test_support_reclassify.py` covers changed/unchanged/failed accounting,
partial write failures, invalid payloads, batching, dates, protected fields and second-run
no-op behavior with both sources. `test_support_refresh.py` covers first deployment,
reviewed apply, stale code/target/data rejection, no checkpoint on failure, exclusivity,
helper fingerprint detection, stale loaded processes and scheduler wiring. GitHub Actions
runs the worker suite, Ruff and mypy with no production secrets.

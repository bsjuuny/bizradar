# Troubleshooting

## `npx create-next-app` / `npx shadcn` says "path is not writable" in bash

Seen during Phase 0 setup on Windows: running these through the bash/MSYS shell produced
a false "not writable" error even though the directory's ACLs were fine. Running the same
command through PowerShell worked. If a Node CLI reports permission errors on a path that
demonstrably has correct `icacls` permissions, retry from PowerShell before assuming a
real permissions problem.

## `npm install` fails with an `@babel/core` peer conflict pulling in Vitest

`shadcn` (the CLI, kept as a devDependency so `npx shadcn add <component>` keeps working)
pins older `@babel/*` packages that conflict with `@vitejs/plugin-react`'s peer range.
This is a dev-tool-only conflict, not a runtime one - install with `--legacy-peer-deps`
for that one command.

## Vitest warns "ESM syntax in a file loaded as CommonJS" / "`__dirname`"

Use `vitest.config.mts` (not `.ts`) and `import.meta.dirname` instead of `__dirname`.

## mypy: "violates the Liskov substitution principle" on a `BaseCollector` subclass

`BaseCollector` is generic (`BaseCollector[TNormalized: BaseModel]`). A subclass must
declare its concrete type, e.g. `class G2BCollector(BaseCollector[G2BOpportunity]):` -
if you type the override methods to accept `BaseModel` directly instead, mypy is telling
you the override is contravariant-unsafe; parameterize the base class instead of loosening
the subclass method signature.

## Ollama not installed / not on PATH

Confirmed during Phase 0 environment check: `ollama` was not found on this machine.
Phase 4 (Ollama + Structured Analysis) cannot be implemented or tested until it's
installed and `qwen3:8b` is pulled. Everything else in the MVP is independent of this.

## `INSERT` into `companies` fails with "new row violates row-level security policy" even
## though the INSERT policy is `with check (true)`

Found while writing the Phase 1 RLS smoke test (`supabase/tests/test_rls_phase1.py`).
`INSERT ... RETURNING` (what `Prefer: return=representation` / Supabase JS's
`.insert().select()` do under the hood) makes Postgres also check the table's **SELECT**
policy on the newly inserted row - not just the INSERT policy's `with check`.
`companies_select_own` depends on `auth_company_id()`, which reads `company_members`,
which doesn't have a row yet for a company that was *just* created. Result: the very
first insert of a brand-new company fails RLS, even though nothing about the INSERT
policy itself is wrong.

Fix used here: the client generates the company's `id` (`crypto.randomUUID()` /
`uuid.uuid4()`) and sends it explicitly in the insert body, and the insert does **not**
request `return=representation`. No RETURNING means no implicit SELECT-policy check.
Once the matching `company_members` row is inserted right after, `auth_company_id()`
resolves and a normal `SELECT` on `companies` works. Apply the same pattern (client
generates the id, first insert doesn't ask for the row back) to any future table whose
SELECT policy depends on a row that doesn't exist until a *second* insert.

## `npx supabase link` fails with `LegacyPlatformAuthRequiredError`

Needs a personal Supabase CLI access token (`SUPABASE_ACCESS_TOKEN`), which is different
from both the DB password and the `service_role` key. Generate one at
https://supabase.com/dashboard/account/tokens.

## `db push --dry-run` fails with `password authentication failed for user "postgres"`

The DB password (Project Settings -> Database) is separate from the CLI access token
and from the `service_role` API key - three different secrets. Reset it from the
dashboard if it's not the one you have on hand.

## Worker can't find `worker` package

Run `pip install -e ".[dev]"` from the repo root (not from `worker/`) - the package is
defined by the root `pyproject.toml` with `packages.find.include = ["worker*"]`.

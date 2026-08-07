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

## `next dev` blocks static chunks: "Blocked cross-origin request... from 127.0.0.1"

Next's dev-origin protection treats `127.0.0.1` and `localhost` as different origins.
Playwright's default `baseURL` is `127.0.0.1`. Fix: add `allowedDevOrigins: ["127.0.0.1"]`
to `next.config.ts` (done in `apps/web/next.config.ts`).

## Middleware doesn't run - file should be `proxy.ts`, not `middleware.ts`

Next.js 16 renamed Middleware to Proxy. The file is `proxy.ts` (or inside `src/` when
using a `src` layout), the exported function is `proxy` (or a default export), and
`export const config = { matcher: [...] }` still works the same way. A `middleware.ts`
file is simply never picked up - no error, no warning, it just silently doesn't run.

## Supabase `signUp()` returns "Email address ... is invalid" for made-up domains

This project has email domain validation on: `auth.signUp()` rejects any address whose
domain doesn't have real MX records (`example.com`, `bizradar-playwright-test.com`, ...).
Admin-created users (`POST /auth/v1/admin/users`, used by `supabase/tests/test_rls_phase1.py`
and the e2e test's `beforeAll`) bypass this check, which is why those work with
`@example.com` but a UI-driven signup test needs a real, resolvable domain (a Gmail
plus-alias like `you+test-x@gmail.com` works and is only ever seen by the project owner).

## Supabase `signUp()` returns "email rate limit exceeded"

The built-in dev mailer (no custom SMTP configured) has a low rate limit by default -
this is expected on a fresh project, not a bug. `apps/web/e2e/core-flow.spec.ts`'s signup
test treats this as a legitimate outcome (asserts the error is surfaced to the user
rather than crashing) instead of retrying or hiding it. Configure custom SMTP in the
Supabase dashboard (Auth -> Emails) if this needs to stop happening in practice.

## G2B (나라장터) API returns "해당 오픈API 서비스가 없거나 폐기됨" (service doesn't exist)

The real path has an `ad/` segment that's very easy to miss:

```
http://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServc
```

Without `ad/`, the API returns this generic "service does not exist" error - not a 404,
and nothing about the message suggests a path problem.

## G2B API returns "SERVICE_KEY_IS_NOT_REGISTERED_ERROR" with a key that is registered

data.go.kr issues an already-URL-encoded key (the "Encoding" variant - it contains
literal `%2F`, `%2B`, `%3D` sequences). Passing it through anything that URL-encodes its
input again (`httpx` request `params=`, `curl --data-urlencode`) double-encodes it, and
the server can't match it to your registration - the error looks like an auth/registration
problem but is actually a double-encoding bug. Append the key to the URL string as-is.

## Korean text looks corrupted (`\udcec...` escaped surrogates) when checking Supabase data

Seen while verifying `worker/collectors/g2b.py` output with
`curl ".../rest/v1/opportunities?..." | python -m json.tool`. This is not a real data bug
- `python -m json.tool` reading piped stdin on Windows decodes using the console's
default codepage, not UTF-8, and mangles multi-byte Korean text. Verify with `httpx` in
Python instead (same stack the app actually uses), or write the piped output to a file
and read it back with `encoding="utf-8"` explicitly.

## Worker can't find `worker` package

Run `pip install -e ".[dev]"` from the repo root (not from `worker/`) - the package is
defined by the root `pyproject.toml` with `packages.find.include = ["worker*"]`.

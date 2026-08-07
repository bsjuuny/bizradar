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

## Worker can't find `worker` package

Run `pip install -e ".[dev]"` from the repo root (not from `worker/`) - the package is
defined by the root `pyproject.toml` with `packages.find.include = ["worker*"]`.

"""Shared helpers for reading whole tables through PostgREST.

PostgREST caps an unbounded select at the project's max-rows setting and returns the
truncated first page with no error and no warning - the caller cannot tell a complete
result from a clipped one. Live on 2026-09-17: project_analyses held 1,902 SUCCESS rows,
an unbounded select returned exactly 1,000, and match_job consequently scored only 903
opportunities (see match_scores.py). Page explicitly instead of trusting an unbounded
select to return everything.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, cast

PAGE_SIZE = 1000


def chunked[T](items: Sequence[T], size: int) -> list[list[T]]:
    return [list(items[i : i + size]) for i in range(0, len(items), size)]


def fetch_all_pages(build_query: Callable[[], Any], key: str | None = None) -> list[dict[str, Any]]:
    """Reads every page of a select.

    With ``key`` (a unique column that the select returns), pages by key: each request
    asks for rows after the last key seen, ordered by it. Rows inserted while paging can't
    shift a page, so no existing row is skipped or read twice. ``build_query`` must then
    return the query *without* an order - this adds it.

    Without ``key``, pages by offset; ``build_query`` must return a fresh *ordered* query,
    since PostgREST gives no stable row order without an explicit sort.

    Either way it advances by the rows that actually came back and stops only on an empty
    page, so a server max-rows smaller than PAGE_SIZE still reads to the end.
    """
    rows: list[dict[str, Any]] = []
    if key is not None:
        last: Any = None
        while True:
            query = build_query().order(key)
            if last is not None:
                query = query.gt(key, last)
            page = cast("list[dict[str, Any]]", query.limit(PAGE_SIZE).execute().data or [])
            if not page:
                return rows
            rows.extend(page)
            last = page[-1][key]

    offset = 0
    while True:
        page = cast(
            "list[dict[str, Any]]",
            build_query().range(offset, offset + PAGE_SIZE - 1).execute().data or [],
        )
        if not page:
            return rows
        rows.extend(page)
        offset += len(page)

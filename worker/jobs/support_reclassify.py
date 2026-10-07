"""Re-derive the rule-based columns of support_programs rows that are already stored.

Classification happens once, at collection time - the same trap as
opportunities.category (docs/DATA_PIPELINE.md): change a rule and the stored rows keep the
old answer, and K-Startup is only re-fetched for its newest 500 announcements per hour, so
older rows would never catch up. Run this after every change to
worker/ai/support_it_filter.py, worker/ai/investment_filter.py or a collector's text
handling:

    python -m worker.jobs.support_reclassify --dry-run   # what would change
    python -m worker.jobs.support_reclassify

(from the repo root, so .env.worker is picked up).

- K-Startup rows: normalize() is re-run on the stored raw_payload, so every derived column
  (DERIVED_COLUMNS) comes out exactly as a fresh collection would write it.
- BizInfo rows: it_related and investment_linked, from the stored title/description.
  Their text columns are already decoded at collection. (Open announcements are re-sent
  every hour anyway; this matters for the ones that closed and won't be.)
Only changed columns of changed rows are written. Recruiting state, dates and
duplicate_of are never touched.
"""

from __future__ import annotations

import argparse
import logging
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from worker.ai.investment_filter import is_investment_linked
from worker.ai.support_it_filter import is_it_related
from worker.collectors.base import RawRecord
from worker.collectors.kstartup import KStartupCollector
from worker.repositories import support_programs

logger = logging.getLogger(__name__)


def kstartup_changes(row: Mapping[str, Any], collector: KStartupCollector) -> dict[str, Any]:
    normalized = collector.normalize(
        RawRecord(
            source="kstartup",
            external_id=row["external_id"],
            fetched_at=datetime.now(UTC),
            payload=row["raw_payload"],
        )
    )
    wanted = {column: getattr(normalized, column) for column in support_programs.DERIVED_COLUMNS}
    return {column: value for column, value in wanted.items() if row.get(column) != value}


def bizinfo_changes(row: Mapping[str, Any]) -> dict[str, Any]:
    wanted = {
        "it_related": is_it_related(row["title"]),
        "investment_linked": is_investment_linked(row["title"], row.get("description")),
    }
    return {column: value for column, value in wanted.items() if row.get(column) != value}


def run(dry_run: bool = False) -> Counter[str]:
    """Returns how many rows changed per column ("rows" = rows touched)."""
    changed: Counter[str] = Counter()
    collector = KStartupCollector()
    plans = [
        (row, kstartup_changes(row, collector))
        for row in support_programs.fetch_programs_for_reclassify("kstartup")
    ] + [
        (row, bizinfo_changes(row))
        for row in support_programs.fetch_programs_for_reclassify("bizinfo")
    ]

    for row, changes in plans:
        if not changes:
            continue
        changed["rows"] += 1
        changed.update(changes.keys())
        if not dry_run:
            support_programs.update_program(row["id"], changes)

    logger.info(
        "support_reclassify finished",
        extra={"dry_run": dry_run, "scanned": len(plans), **dict(changed)},
    )
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="report changes, write nothing")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    result = run(dry_run=args.dry_run)
    verb = "would change" if args.dry_run else "changed"
    print(f"{verb}: {dict(result) or 'nothing'}")


if __name__ == "__main__":
    main()

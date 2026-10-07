"""Re-derive the derived columns of support_programs rows that are already stored.

Classification and text cleaning happen once, at collection time - the same trap as
opportunities.category (docs/DATA_PIPELINE.md): change a rule and stored rows keep the old
answer. K-Startup re-fetches only its newest 500 announcements per hour and 기업마당 never
re-sends a closed one, so those rows would never catch up. Run this after every change to
worker/ai/support_it_filter.py, worker/ai/investment_filter.py or a collector's
normalize()/text handling:

    python -m worker.jobs.support_reclassify --dry-run   # what would change
    python -m worker.jobs.support_reclassify

(from the repo root; it reads the shared vault first, like the PM2 entrypoint).

Each row's own collector re-runs normalize() on the stored raw_payload, so the columns in
DERIVED_COLUMNS come out exactly as a fresh collection would write them. Only changed
columns of changed rows are written. Recruiting state, dates and duplicate_of are never
touched.
"""

from __future__ import annotations

import argparse
import logging
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic import BaseModel

from worker.collectors.base import RawRecord
from worker.collectors.bizinfo import BizInfoCollector
from worker.collectors.kstartup import KStartupCollector
from worker.repositories import support_programs

logger = logging.getLogger(__name__)


class _Normalizer(Protocol):
    def normalize(self, raw: RawRecord) -> BaseModel: ...


def row_changes(
    row: Mapping[str, Any], source: str, collector: _Normalizer, columns: Sequence[str]
) -> dict[str, Any]:
    normalized = collector.normalize(
        RawRecord(
            source=source,
            external_id=row["external_id"],
            fetched_at=datetime.now(UTC),
            payload=row["raw_payload"],
        )
    )
    wanted = {column: getattr(normalized, column) for column in columns}
    return {column: value for column, value in wanted.items() if row.get(column) != value}


def run(dry_run: bool = False) -> Counter[str]:
    """Returns how many rows changed per column ("rows" = rows touched)."""
    collectors: dict[str, _Normalizer] = {
        "kstartup": KStartupCollector(),
        "bizinfo": BizInfoCollector(),
    }
    changed: Counter[str] = Counter()
    scanned = 0
    for source, collector in collectors.items():
        columns = support_programs.DERIVED_COLUMNS[source]
        for row in support_programs.fetch_programs_for_reclassify(source):
            scanned += 1
            changes = row_changes(row, source, collector, columns)
            if not changes:
                continue
            changed["rows"] += 1
            changed.update(changes.keys())
            if not dry_run:
                support_programs.update_program(row["id"], changes)

    logger.info(
        "support_reclassify finished",
        extra={"dry_run": dry_run, "scanned": scanned, **dict(changed)},
    )
    return changed


def main() -> None:
    from worker.logging_config import configure_logging
    from worker.secrets_loader import load_github_secrets

    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="report changes, write nothing")
    args = parser.parse_args()
    load_github_secrets()
    configure_logging()
    result = run(dry_run=args.dry_run)
    verb = "would change" if args.dry_run else "changed"
    print(f"{verb}: {dict(result) or 'nothing'}")


if __name__ == "__main__":
    main()

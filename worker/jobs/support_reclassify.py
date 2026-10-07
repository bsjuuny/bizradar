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
DERIVED_COLUMNS come out exactly as a fresh collection would write them - including the
application dates, which are pure functions of the payload (a parse_period fix must reach
stored rows). Only changed columns of changed rows are written; rows needing the same
change go in one request per chunk - which batches K-Startup rows, while each changed
기업마당 row is its own request (its content_hash is part of the change). A row whose
payload can't be re-derived is logged and left as is. Recruiting state, duplicate_of and
last_seen_at are never touched: they depend on when a row was collected and on the
closing/dedupe passes, not on the payload.
"""

from __future__ import annotations

import argparse
import json
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
    changes: dict[str, Any] = {}
    for column in columns:
        wanted = getattr(normalized, column)
        if not _same_value(row.get(column), wanted):
            # Dates go to PostgREST as ISO strings (with their +00:00 offset).
            changes[column] = wanted.isoformat() if isinstance(wanted, datetime) else wanted
    return changes


def _same_value(stored: Any, wanted: Any) -> bool:
    # PostgREST returns timestamptz as a string ("2026-10-16T00:00:00+00:00"); normalize()
    # gives a datetime. Same instant counts as unchanged.
    if isinstance(wanted, datetime):
        return isinstance(stored, str) and datetime.fromisoformat(stored) == wanted
    return bool(stored == wanted)


def run(dry_run: bool = False) -> Counter[str]:
    """Returns how many rows changed per column ("rows" = rows touched, "failed" = rows
    whose payload couldn't be re-derived and were left as they are)."""
    collectors: dict[str, _Normalizer] = {
        "kstartup": KStartupCollector(),
        "bizinfo": BizInfoCollector(),
    }
    changed: Counter[str] = Counter()
    scanned = 0
    # Rows needing the identical change, written together: after a rule change most rows
    # differ by the same column value (e.g. {"it_related": true}).
    groups: dict[str, tuple[dict[str, Any], list[str]]] = {}
    for source, collector in collectors.items():
        columns = support_programs.DERIVED_COLUMNS[source]
        for row in support_programs.fetch_programs_for_reclassify(source):
            scanned += 1
            try:
                changes = row_changes(row, source, collector, columns)
            except Exception:
                # One unreadable stored payload must not cost every other row its update
                # (after a migration this run is what fills it_related).
                logger.exception(
                    "support_reclassify: could not re-derive a row, skipped",
                    extra={"source": source, "id": row["id"]},
                )
                changed["failed"] += 1
                continue
            if not changes:
                continue
            changed["rows"] += 1
            changed.update(changes.keys())
            key = json.dumps(changes, sort_keys=True, ensure_ascii=False)
            groups.setdefault(key, (changes, []))[1].append(row["id"])

    if not dry_run:
        for changes, row_ids in groups.values():
            support_programs.update_programs(row_ids, changes)

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

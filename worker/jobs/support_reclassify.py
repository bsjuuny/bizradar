"""Re-derive the derived columns of support_programs rows that are already stored.

Classification and text cleaning happen once, at collection time - the same trap as
opportunities.category (docs/DATA_PIPELINE.md): change a rule and stored rows keep the old
answer. K-Startup re-fetches only its newest 500 announcements per hour and 기업마당 never
re-sends a closed one, so those rows would never catch up. Run this after every change to
worker/ai/support_it_filter.py, worker/ai/investment_filter.py or a collector's
normalize()/text handling:

    python -m worker.jobs.support_reclassify --dry-run --plan .support-refresh/plan.json
    # Review the target, source counts and changed columns before applying:
    python -m worker.jobs.support_reclassify --apply-plan .support-refresh/plan.json

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

import hashlib
import json
import logging
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
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

    def validate(self, normalized: Any) -> bool: ...


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
    if not collector.validate(normalized):
        raise ValueError("Stored payload does not produce a valid program")
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


@dataclass
class Prepared:
    counts: Counter[str]
    groups: dict[str, tuple[dict[str, Any], list[str]]]
    snapshot: str
    sources: dict[str, dict[str, int]] = field(default_factory=dict)


def prepare() -> Prepared:
    """Returns how many rows changed per column ("rows" = rows touched, "failed" = rows
    whose payload couldn't be re-derived and were left as they are)."""
    collectors: dict[str, _Normalizer] = {
        "kstartup": KStartupCollector(),
        "bizinfo": BizInfoCollector(),
    }
    changed: Counter[str] = Counter(scanned=0, rows=0, unchanged=0, failed=0, written=0)
    source_counts: dict[str, dict[str, int]] = {}
    snapshots = []
    # Rows needing the identical change, written together: after a rule change most rows
    # differ by the same column value (e.g. {"it_related": true}).
    groups: dict[str, tuple[dict[str, Any], list[str]]] = {}
    for source, collector in collectors.items():
        before = changed.copy()
        columns = support_programs.DERIVED_COLUMNS[source]
        for row in support_programs.fetch_programs_for_reclassify(source):
            changed["scanned"] += 1
            snapshots.append((source, row))
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
                changed["unchanged"] += 1
                continue
            changed["rows"] += 1
            changed.update(changes.keys())
            key = json.dumps(changes, sort_keys=True, ensure_ascii=False)
            groups.setdefault(key, (changes, []))[1].append(row["id"])

        source_counts[source] = {
            key: changed[key] - before[key] for key in ("scanned", "rows", "unchanged", "failed")
        }

    snapshot = hashlib.sha256(
        json.dumps(
            sorted(snapshots, key=lambda item: (item[0], item[1]["id"])),
            sort_keys=True,
            ensure_ascii=False,
        ).encode()
    ).hexdigest()
    return Prepared(changed, groups, snapshot, source_counts)


def apply(prepared: Prepared) -> Counter[str]:
    result = prepared.counts.copy()
    result["written"] = 0
    # One failed chunk never claims successful writes; no row-by-row request explosion.
    # Keep chunks at the repository's existing 100-id update bound.
    for changes, row_ids in prepared.groups.values():
        for start in range(0, len(row_ids), 100):
            chunk = row_ids[start : start + 100]
            try:
                support_programs.update_programs(chunk, changes)
                result["written"] += len(chunk)
            except Exception:
                result["failed"] += len(chunk)
                logger.exception("support_reclassify: update chunk failed")
                # Stop on a database error; remaining candidates stay pending on retry.
                result["pending"] = (
                    result["rows"]
                    - result["written"]
                    - (result["failed"] - prepared.counts["failed"])
                )
                return result
    return result


def run(dry_run: bool = False) -> Counter[str]:
    prepared = prepare()
    result = prepared.counts if dry_run else apply(prepared)
    logger.info("support_reclassify finished", extra={"dry_run": dry_run, **dict(result)})
    return result


def main() -> None:
    # Preserve the established command, but require the reviewed-plan deployment path.
    from worker.jobs.support_refresh import main as refresh_main

    refresh_main()


if __name__ == "__main__":
    main()

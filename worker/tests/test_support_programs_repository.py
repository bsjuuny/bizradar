import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from worker.collectors.bizinfo import BizInfoNormalizedProgram, StoredRow
from worker.repositories import support_programs


class _RecordingQuery:
    def __init__(self, client: "_RecordingClient", table: str) -> None:
        self._client = client
        self._request: dict[str, Any] = {"table": table}

    def update(self, values: dict[str, Any]) -> "_RecordingQuery":
        self._request.update(op="update", values=values)
        return self

    def upsert(self, values: dict[str, Any], on_conflict: str = "") -> "_RecordingQuery":
        self._request.update(op="upsert", values=values, on_conflict=on_conflict)
        return self

    def in_(self, column: str, values: list[str]) -> "_RecordingQuery":
        self._request["in"] = (column, list(values))
        return self

    def execute(self) -> None:
        self._client.requests.append(self._request)


class _RecordingClient:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    def table(self, name: str) -> _RecordingQuery:
        return _RecordingQuery(self, name)


@pytest.fixture
def client(monkeypatch):
    fake = _RecordingClient()
    monkeypatch.setattr(support_programs, "get_service_client", lambda: fake)
    return fake


def test_duplicate_marks_are_written_one_request_per_value(client):
    support_programs.set_duplicate_of({"bz-1": "ks-1", "bz-2": "ks-1", "bz-3": None})

    assert [(r["values"], r["in"]) for r in client.requests] == [
        ({"duplicate_of": "ks-1"}, ("id", ["bz-1", "bz-2"])),
        ({"duplicate_of": None}, ("id", ["bz-3"])),
    ]


def test_close_unlisted_uses_the_given_state_without_reading(client, monkeypatch):
    def must_not_read():
        raise AssertionError("state was given - no second read")

    monkeypatch.setattr(support_programs, "fetch_bizinfo_state", must_not_read)

    closed = support_programs.close_unlisted_bizinfo(
        {"A"},
        {
            "A": StoredRow("row-a", "h", True),
            "B": StoredRow("row-b", "h", True),
            "C": StoredRow("row-c", "h", True),
            # Recently seen but already closed: nothing to do.
            "D": StoredRow("row-d", "h", False),
        },
    )

    assert closed == 2
    assert [(r["values"], r["in"]) for r in client.requests] == [
        ({"recruiting": False}, ("id", ["row-b", "row-c"])),
    ]


def test_close_unlisted_reads_the_state_when_not_given(client, monkeypatch):
    # The job's own read failed: fall back to reading it here.
    monkeypatch.setattr(
        support_programs, "fetch_bizinfo_state", lambda: {"B": StoredRow("row-b", "h", True)}
    )

    assert support_programs.close_unlisted_bizinfo({"A"}) == 1
    assert client.requests[0]["in"] == ("id", ["row-b"])


def test_seen_refresh_is_due_for_listed_rows_not_refreshed_for_a_day():
    now = datetime(2026, 10, 8, 12, tzinfo=UTC)
    stored = {
        "A": StoredRow("row-a", "h", True, None),  # never recorded
        "B": StoredRow("row-b", "h", True, now - timedelta(hours=25)),  # a day old
        "C": StoredRow("row-c", "h", True, now - timedelta(hours=2)),  # fresh enough
        "D": StoredRow("row-d", "h", True, None),  # not listed
    }

    due = support_programs.seen_refresh_due(stored, ["A", "B", "C", "NEW"], now)

    # Every listed stored row, whatever persist() did with it ("NEW" was upserted with
    # its own last_seen_at).
    assert sorted(due) == ["row-a", "row-b"]


def test_seen_rows_get_a_fresh_last_seen_at(client):
    support_programs.mark_bizinfo_seen(["row-a", "row-b"])

    (request,) = client.requests
    assert request["in"] == ("id", ["row-a", "row-b"])
    assert datetime.fromisoformat(request["values"]["last_seen_at"]).tzinfo is not None


def test_bizinfo_upsert_records_the_row_as_seen(client):
    normalized = BizInfoNormalizedProgram(
        external_id="PBLN_1", title="t", content_hash="h", raw_payload={}
    )

    support_programs.upsert_bizinfo_programs(
        [normalized, normalized.model_copy(update={"external_id": "PBLN_2"})]
    )

    (request,) = client.requests  # one request for both
    assert request["op"] == "upsert"
    assert request["on_conflict"] == "source,external_id"
    assert [row["external_id"] for row in request["values"]] == ["PBLN_1", "PBLN_2"]
    assert all(row["last_seen_at"] for row in request["values"])
    # A multi-row upsert needs the same keys on every row.
    assert len({tuple(sorted(row)) for row in request["values"]}) == 1


def test_bulk_updates_are_chunked(client):
    ids = [f"row-{i}" for i in range(250)]

    support_programs.update_programs(ids, {"it_related": True})

    assert [len(r["in"][1]) for r in client.requests] == [100, 100, 50]
    assert all(r["values"] == {"it_related": True} for r in client.requests)


def test_last_seen_intervals_agree_with_the_sql_rule():
    # is_open() (SQL) closes a date-less 기업마당 row after N days unseen; the worker only
    # rewrites last_seen_at once it is LAST_SEEN_REFRESH_AFTER old. If N dropped to near
    # the refresh interval, listed rows would flicker out of 모집 중 between refreshes.
    # Reads the newest migration that defines is_open, so a later change can't skip this -
    # however it is spelled (schema prefix, spacing, days or hours).
    migrations = sorted(
        (Path(__file__).resolve().parents[2] / "supabase" / "migrations").glob("*.sql")
    )
    defines_is_open = re.compile(r"function\s+(?:public\.)?is_open\s*\(", re.IGNORECASE)
    defining = [m for m in migrations if defines_is_open.search(m.read_text(encoding="utf-8"))]
    sql = defining[-1].read_text(encoding="utf-8")
    body = sql[defines_is_open.search(sql).start() :]
    window = re.search(r"last_seen_at\s*>=\s*now\(\)\s*-\s*interval\s*'(\d+)\s*(day|hour)s?'", body)
    assert window, f"no last_seen_at interval found in {defining[-1].name} - update this test"
    amount, unit = int(window.group(1)), window.group(2)
    stale_after = timedelta(days=amount) if unit == "day" else timedelta(hours=amount)

    hourly_run = timedelta(hours=1)
    assert stale_after >= 2 * support_programs.LAST_SEEN_REFRESH_AFTER + hourly_run
    # The state read must include every listed row, refreshed or not yet.
    assert support_programs.LAST_SEEN_REFRESH_AFTER + hourly_run <= support_programs._STATE_WINDOW

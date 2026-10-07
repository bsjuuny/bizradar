import logging
from datetime import date

import pytest

from worker.collectors.base import CollectorRunResult
from worker.collectors.bizinfo import StoredRow
from worker.config import Settings
from worker.dedupe.support_programs import ProgramTitle
from worker.jobs import bizinfo_job

STORED = {
    "A": StoredRow("row-a", "hash-a", True),
    "C": StoredRow("row-c", "hash-c", True),
}


class FakeCollector:
    def __init__(self, complete: bool = True, listed=("A", "B"), stored=None):
        self.complete = complete
        self.listed_ids = set(listed)
        self.stored = stored
        self.unchanged_ids = ["row-a"]

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return None

    def run(self) -> CollectorRunResult:
        return CollectorRunResult(source="bizinfo", collected=2, persisted=2)


class FakeRepo:
    """Stands in for worker.repositories.support_programs."""

    def __init__(self):
        self.closed_with = None
        self.closed_from = None
        self.seen = None
        self.changes = None
        self.kstartup = [
            ProgramTitle("ks-1", "2026년 극지 데이터 융합 스케일업 프로그램", date(2026, 10, 11))
        ]
        self.bizinfo = [
            ProgramTitle(
                "bz-1",
                "2026년 극지 데이터 융합 스케일업 프로그램 참여기업 모집 공고",
                date(2026, 10, 11),
            ),
            ProgramTitle("bz-2", "2026년 중소기업 수출지원사업 통합 공고", None),
        ]
        self.current = {"bz-1": None, "bz-2": "ks-old"}

    def fetch_bizinfo_state(self):
        return STORED

    def mark_bizinfo_seen(self, row_ids):
        self.seen = list(row_ids)

    def close_unlisted_bizinfo(self, listed_ids, stored=None):
        self.closed_with = set(listed_ids)
        self.closed_from = stored
        return 0

    def fetch_open_kstartup_titles(self):
        return self.kstartup

    def fetch_open_bizinfo_titles(self):
        return self.bizinfo, self.current

    def set_duplicate_of(self, changes):
        self.changes = dict(changes)


SUPABASE = {"supabase_url": "https://example.supabase.co", "supabase_service_role_key": "k"}


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(
        bizinfo_job,
        "get_settings",
        lambda: Settings(_env_file=None, bizinfo_api_key="key", **SUPABASE),
    )
    repo = FakeRepo()
    monkeypatch.setattr(bizinfo_job, "support_programs", repo)
    return repo


def test_job_skips_collection_without_key_but_still_dedupes(monkeypatch, caplog):
    monkeypatch.setattr(bizinfo_job, "get_settings", lambda: Settings(_env_file=None, **SUPABASE))
    repo = FakeRepo()
    monkeypatch.setattr(bizinfo_job, "support_programs", repo)

    def must_not_construct(*args, **kwargs):
        raise AssertionError("collector must not run without a key")

    monkeypatch.setattr(bizinfo_job, "BizInfoCollector", must_not_construct)

    with caplog.at_level(logging.INFO):
        bizinfo_job.run()

    assert any("skipped" in record.message for record in caplog.records)
    assert repo.closed_with is None
    assert repo.seen is None
    # Rows collected while a key existed still get their marks maintained.
    assert repo.changes == {"bz-1": "ks-1", "bz-2": None}


def test_job_without_supabase_skips_dedupe_quietly(monkeypatch, caplog):
    # A fresh checkout (DATA_MODE=mock, no .env.worker): nothing to dedupe against, and
    # no hourly "dedupe failed" stack trace either.
    monkeypatch.setattr(bizinfo_job, "get_settings", lambda: Settings(_env_file=None))
    repo = FakeRepo()
    monkeypatch.setattr(bizinfo_job, "support_programs", repo)
    monkeypatch.setattr(bizinfo_job, "BizInfoCollector", lambda stored: FakeCollector())

    with caplog.at_level(logging.INFO):
        bizinfo_job.run()

    assert repo.changes is None
    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert any("dedupe skipped" in record.message for record in caplog.records)


def test_job_collects_closes_unlisted_and_dedupes(monkeypatch, configured, caplog):
    made = []
    monkeypatch.setattr(
        bizinfo_job,
        "BizInfoCollector",
        lambda stored: made.append(FakeCollector(stored=stored)) or made[-1],
    )

    with caplog.at_level(logging.INFO):
        bizinfo_job.run()

    assert any("job finished" in record.message for record in caplog.records)
    # One state read, shared by the collector's skip and the closing pass.
    assert made[0].stored is STORED
    assert configured.closed_with == {"A", "B"}
    assert configured.closed_from is STORED
    # Rows skipped as unchanged were still listed: recorded as seen.
    assert configured.seen == ["row-a"]
    # bz-1 repeats the open K-Startup row; bz-2's stale mark is cleared.
    assert configured.changes == {"bz-1": "ks-1", "bz-2": None}


def test_job_does_not_close_anything_after_incomplete_response(monkeypatch, configured):
    monkeypatch.setattr(
        bizinfo_job, "BizInfoCollector", lambda stored: FakeCollector(complete=False)
    )

    bizinfo_job.run()

    assert configured.closed_with is None
    # What did arrive was listed: those rows stay fresh, only the missing ones age out.
    assert configured.seen == ["row-a"]
    assert configured.changes is not None  # dedupe still runs


def test_state_read_failure_writes_every_row_and_close_reads_for_itself(
    monkeypatch, configured, caplog
):
    def broken_state():
        raise RuntimeError("db down")

    configured.fetch_bizinfo_state = broken_state
    made = []
    monkeypatch.setattr(
        bizinfo_job,
        "BizInfoCollector",
        lambda stored: made.append(FakeCollector(stored=stored)) or made[-1],
    )

    with caplog.at_level(logging.WARNING):
        bizinfo_job.run()

    assert any("could not read stored state" in record.message for record in caplog.records)
    assert made[0].stored is None
    assert configured.closed_with == {"A", "B"}
    assert configured.closed_from is None


def test_job_isolates_collector_failure(monkeypatch, configured, caplog):
    def fail(stored):
        raise RuntimeError("upstream down")

    monkeypatch.setattr(bizinfo_job, "BizInfoCollector", fail)

    with caplog.at_level(logging.ERROR):
        bizinfo_job.run()

    assert any("failed entirely" in record.message for record in caplog.records)
    assert configured.closed_with is None
    # A BizInfo outage must not freeze stale duplicate_of marks: dedupe still runs.
    assert configured.changes == {"bz-1": "ks-1", "bz-2": None}


def test_close_failure_does_not_stop_dedupe(monkeypatch, configured, caplog):
    monkeypatch.setattr(bizinfo_job, "BizInfoCollector", lambda stored: FakeCollector())

    def broken_close(listed_ids, stored=None):
        raise RuntimeError("db down")

    configured.close_unlisted_bizinfo = broken_close

    with caplog.at_level(logging.ERROR):
        bizinfo_job.run()

    assert any("closing unlisted" in record.message for record in caplog.records)
    assert configured.changes == {"bz-1": "ks-1", "bz-2": None}


def test_seen_marking_failure_does_not_stop_closing(monkeypatch, configured, caplog):
    monkeypatch.setattr(bizinfo_job, "BizInfoCollector", lambda stored: FakeCollector())

    def broken_seen(row_ids):
        raise RuntimeError("db down")

    configured.mark_bizinfo_seen = broken_seen

    with caplog.at_level(logging.ERROR):
        bizinfo_job.run()

    assert any("as seen failed" in record.message for record in caplog.records)
    assert configured.closed_with == {"A", "B"}


def test_dedupe_failure_is_logged_not_raised(monkeypatch, configured, caplog):
    monkeypatch.setattr(bizinfo_job, "BizInfoCollector", lambda stored: FakeCollector())

    def broken_fetch():
        raise RuntimeError("db down")

    configured.fetch_open_kstartup_titles = broken_fetch

    with caplog.at_level(logging.ERROR):
        bizinfo_job.run()

    assert any("dedupe failed" in record.message for record in caplog.records)

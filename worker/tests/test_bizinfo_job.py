import logging
from datetime import date

import pytest

from worker.collectors.base import CollectorRunResult
from worker.config import Settings
from worker.dedupe.support_programs import ProgramTitle
from worker.jobs import bizinfo_job


class FakeCollector:
    def __init__(self, complete: bool = True, listed=("A", "B")):
        self.complete = complete
        self.listed_ids = set(listed)

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

    def close_unlisted_bizinfo(self, listed_ids):
        self.closed_with = set(listed_ids)
        return 0

    def fetch_open_kstartup_titles(self, today):
        return self.kstartup

    def fetch_open_bizinfo_titles(self):
        return self.bizinfo, self.current

    def set_duplicate_of(self, changes):
        self.changes = dict(changes)


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(
        bizinfo_job, "get_settings", lambda: Settings(_env_file=None, bizinfo_api_key="key")
    )
    repo = FakeRepo()
    monkeypatch.setattr(bizinfo_job, "support_programs", repo)
    return repo


def test_job_skips_collection_without_key_but_still_dedupes(monkeypatch, caplog):
    monkeypatch.setattr(bizinfo_job, "get_settings", lambda: Settings(_env_file=None))
    repo = FakeRepo()
    monkeypatch.setattr(bizinfo_job, "support_programs", repo)

    def must_not_construct(*args, **kwargs):
        raise AssertionError("collector must not run without a key")

    monkeypatch.setattr(bizinfo_job, "BizInfoCollector", must_not_construct)

    with caplog.at_level(logging.INFO):
        bizinfo_job.run()

    assert any("skipped" in record.message for record in caplog.records)
    assert repo.closed_with is None
    # Rows collected while a key existed still get their marks maintained.
    assert repo.changes == {"bz-1": "ks-1", "bz-2": None}


def test_job_collects_closes_unlisted_and_dedupes(monkeypatch, configured, caplog):
    monkeypatch.setattr(bizinfo_job, "BizInfoCollector", lambda: FakeCollector())

    with caplog.at_level(logging.INFO):
        bizinfo_job.run()

    assert any("job finished" in record.message for record in caplog.records)
    assert configured.closed_with == {"A", "B"}
    # bz-1 repeats the open K-Startup row; bz-2's stale mark is cleared.
    assert configured.changes == {"bz-1": "ks-1", "bz-2": None}


def test_job_does_not_close_anything_after_incomplete_response(monkeypatch, configured):
    monkeypatch.setattr(bizinfo_job, "BizInfoCollector", lambda: FakeCollector(complete=False))

    bizinfo_job.run()

    assert configured.closed_with is None
    assert configured.changes is not None  # dedupe still runs


def test_job_isolates_collector_failure(monkeypatch, configured, caplog):
    def fail():
        raise RuntimeError("upstream down")

    monkeypatch.setattr(bizinfo_job, "BizInfoCollector", fail)

    with caplog.at_level(logging.ERROR):
        bizinfo_job.run()

    assert any("failed entirely" in record.message for record in caplog.records)
    assert configured.closed_with is None
    # A BizInfo outage must not freeze stale duplicate_of marks: dedupe still runs.
    assert configured.changes == {"bz-1": "ks-1", "bz-2": None}


def test_close_failure_does_not_stop_dedupe(monkeypatch, configured, caplog):
    monkeypatch.setattr(bizinfo_job, "BizInfoCollector", lambda: FakeCollector())

    def broken_close(listed_ids):
        raise RuntimeError("db down")

    configured.close_unlisted_bizinfo = broken_close

    with caplog.at_level(logging.ERROR):
        bizinfo_job.run()

    assert any("closing unlisted" in record.message for record in caplog.records)
    assert configured.changes == {"bz-1": "ks-1", "bz-2": None}


def test_dedupe_failure_is_logged_not_raised(monkeypatch, configured, caplog):
    monkeypatch.setattr(bizinfo_job, "BizInfoCollector", lambda: FakeCollector())

    def broken_fetch(today):
        raise RuntimeError("db down")

    configured.fetch_open_kstartup_titles = broken_fetch

    with caplog.at_level(logging.ERROR):
        bizinfo_job.run()

    assert any("dedupe failed" in record.message for record in caplog.records)

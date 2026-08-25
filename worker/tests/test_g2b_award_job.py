import logging

from worker.collectors.base import CollectorRunResult
from worker.config import Settings
from worker.jobs import g2b_award_job


class FakeCollector:
    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return None

    def run(self) -> CollectorRunResult:
        return CollectorRunResult(source="g2b_award", collected=2, persisted=2)


def test_job_skips_cleanly_without_key(monkeypatch, caplog):
    monkeypatch.setattr(g2b_award_job, "get_settings", lambda: Settings(_env_file=None))

    with caplog.at_level(logging.INFO):
        g2b_award_job.run()

    assert any("skipped" in record.message for record in caplog.records)


def test_job_collects_when_key_is_configured(monkeypatch, caplog):
    monkeypatch.setattr(
        g2b_award_job,
        "get_settings",
        lambda: Settings(_env_file=None, g2b_award_api_key="key"),
    )
    monkeypatch.setattr(g2b_award_job, "G2BAwardCollector", lambda **kwargs: FakeCollector())

    with caplog.at_level(logging.INFO):
        g2b_award_job.run()

    assert any("job finished" in record.message for record in caplog.records)


def test_job_isolates_collector_failure(monkeypatch, caplog):
    monkeypatch.setattr(
        g2b_award_job,
        "get_settings",
        lambda: Settings(_env_file=None, g2b_award_api_key="key"),
    )

    def fail(**kwargs):
        raise RuntimeError("upstream down")

    monkeypatch.setattr(g2b_award_job, "G2BAwardCollector", fail)

    with caplog.at_level(logging.ERROR):
        g2b_award_job.run()

    assert any("job failed" in record.message for record in caplog.records)

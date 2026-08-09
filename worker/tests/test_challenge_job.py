from dataclasses import replace

from worker.challenges.models import ChallengeCollectionSummary
from worker.challenges.sources import DATA_GO_KR
from worker.collectors.base import CollectorRunResult
from worker.jobs import challenge_job


class FakeCollector:
    def __init__(self, *, source_config, **kwargs):
        self.source_config = source_config

    def __enter__(self):
        if self.source_config.source_id == "broken":
            raise RuntimeError("503")
        return self

    def __exit__(self, *exc_info):
        return None

    def run(self):
        return CollectorRunResult(source=self.source_config.source_id, collected=2, persisted=2)


def test_collection_summary_reports_partial_success():
    assert ChallengeCollectionSummary(sources=2, success=1, failed=1).status == "PARTIAL_SUCCESS"


def test_one_source_failure_does_not_stop_remaining_sources(monkeypatch):
    healthy = replace(DATA_GO_KR, source_id="healthy")
    broken = replace(DATA_GO_KR, source_id="broken")
    monkeypatch.setattr(challenge_job, "CHALLENGE_SOURCES", (broken, healthy))
    monkeypatch.setattr(challenge_job, "DataGoKrChallengeCollector", FakeCollector)
    monkeypatch.setattr(challenge_job, "record_source_status", lambda **kwargs: None)
    monkeypatch.setattr(
        challenge_job,
        "get_settings",
        lambda: type("S", (), {"feature_challenge": True, "challenge_collection_enabled": True})(),
    )

    result = challenge_job.run()

    assert result.status == "PARTIAL_SUCCESS"
    assert result.success == 1
    assert result.failed == 1
    assert result.persisted == 2

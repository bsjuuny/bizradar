from datetime import UTC, datetime

import pytest
from pydantic import BaseModel

from worker.collectors.base import BaseCollector, RawRecord


class DummyNormalized(BaseModel):
    external_id: str


class DummyCollector(BaseCollector[DummyNormalized]):
    """Collects 3 records; the second fails to persist to exercise error isolation."""

    source = "dummy"

    def collect(self):
        return [
            RawRecord(
                source=self.source,
                external_id=str(i),
                fetched_at=datetime.now(UTC),
                payload={"i": i},
            )
            for i in range(3)
        ]

    def normalize(self, raw: RawRecord) -> DummyNormalized:
        return DummyNormalized(external_id=raw.external_id)

    def validate(self, normalized: DummyNormalized) -> bool:
        return True

    def persist(self, normalized: DummyNormalized) -> None:
        if normalized.external_id == "1":
            raise RuntimeError("boom")


def test_base_collector_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        BaseCollector()


def test_run_isolates_per_record_failures():
    result = DummyCollector().run()

    assert result.collected == 3
    assert result.persisted == 2
    assert result.failed == 1
    assert "1: boom" in result.errors[0]

from worker.repositories import project_analyses


class _FakeExecute:
    def execute(self):
        return None


class _FakeTable:
    def __init__(self, captured: list[dict]):
        self._captured = captured

    def upsert(self, row: dict, on_conflict: str):
        self._captured.append(row)
        return _FakeExecute()


class _FakeClient:
    def __init__(self, captured: list[dict]):
        self._captured = captured

    def table(self, name: str):
        assert name == "project_analyses"
        return _FakeTable(self._captured)


def test_upsert_failure_forces_prompt_version_to_none(monkeypatch):
    # Regression test for a live-found bug: if prompt_version were left out of the
    # upsert payload, an upsert only touches columns it includes, so a FAILED row would
    # silently keep whatever prompt_version it last had. When a reanalysis triggered
    # purely by a content_hash change (prompt_version already current) then fails, that
    # left analyzed_content_hash matching the candidate and prompt_version already
    # "current" - get_pending_opportunities() would never consider it pending again.
    # Forcing None here guarantees a version mismatch, so it's always retried.
    captured: list[dict] = []
    monkeypatch.setattr(project_analyses, "get_service_client", lambda: _FakeClient(captured))

    project_analyses.upsert_failure("opp-1", "hash-b", "simulated failure")

    assert len(captured) == 1
    row = captured[0]
    assert row["prompt_version"] is None
    assert row["analyzed_content_hash"] == "hash-b"
    assert row["status"] == "FAILED"


def test_a_failed_row_is_always_pending_regardless_of_current_prompt_version(monkeypatch):
    # End-to-end through get_pending_opportunities(): a FAILED row (prompt_version=None
    # after upsert_failure) must compare unequal to *any* real current prompt_version.
    candidate = {
        "id": "opp-1",
        "title": "t",
        "organization": None,
        "demand_organization": None,
        "budget_amount": None,
        "content_hash": "hash-b",
    }
    existing = {
        "opportunity_id": "opp-1",
        "analyzed_content_hash": "hash-b",
        "prompt_version": None,
    }

    class _Query:
        def __init__(self, data):
            self._data = data

        def select(self, *_a, **_kw):
            return self

        def eq(self, *_a, **_kw):
            return self

        def order(self, *_a, **_kw):
            return self

        def limit(self, *_a, **_kw):
            return self

        def in_(self, *_a, **_kw):
            return self

        def execute(self):
            return type("R", (), {"data": self._data})()

    class _Client:
        def table(self, name: str):
            return _Query([candidate]) if name == "opportunities_current" else _Query([existing])

    monkeypatch.setattr(project_analyses, "get_service_client", lambda: _Client())

    pending = project_analyses.get_pending_opportunities(
        "LIKELY_IT", 5, current_prompt_version="v99"
    )
    assert [c["id"] for c in pending] == ["opp-1"]

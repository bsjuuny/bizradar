import logging

import pytest

from worker.jobs import match_job
from worker.matching.engine import CompanyProfile, OpportunityRequirements, compute_match_score
from worker.repositories.match_scores import score_values


def _finished(caplog):
    finished = [r for r in caplog.records if "match job finished" in r.message]
    assert len(finished) == 1
    return finished[0]


@pytest.fixture
def two_by_one(monkeypatch):
    companies = [
        ("company-1", CompanyProfile(technologies={"Python"})),
        ("company-2", CompanyProfile()),
    ]
    opportunities = [
        ("opp-1", OpportunityRequirements(technologies=["Python"])),
    ]
    monkeypatch.setattr(match_job, "get_companies_for_matching", lambda: companies)
    monkeypatch.setattr(match_job, "get_analyzed_opportunities", lambda: opportunities)
    monkeypatch.setattr(match_job, "get_existing_scores", lambda: {})
    return companies, opportunities


def _record_upserts(monkeypatch):
    calls: list[list[tuple[str, str]]] = []
    monkeypatch.setattr(
        match_job,
        "upsert_match_scores",
        lambda scores: calls.append([(c, o) for c, o, _ in scores]),
    )
    return calls


def test_run_computes_score_for_every_company_opportunity_pair(monkeypatch, caplog, two_by_one):
    calls = _record_upserts(monkeypatch)

    with caplog.at_level(logging.INFO):
        match_job.run()

    # one request for both pairs, not one per pair
    assert calls == [[("company-1", "opp-1"), ("company-2", "opp-1")]]
    record = _finished(caplog)
    assert (record.computed, record.written, record.unchanged, record.failed) == (2, 2, 0, 0)


def test_run_skips_pairs_whose_stored_score_is_unchanged(monkeypatch, caplog, two_by_one):
    companies, opportunities = two_by_one
    unchanged = score_values(compute_match_score(companies[0][1], opportunities[0][1]))
    monkeypatch.setattr(
        match_job,
        "get_existing_scores",
        lambda: {
            ("company-1", "opp-1"): unchanged,
            ("company-2", "opp-1"): (0.0,) * 7,  # stale - must be rewritten
        },
    )
    calls = _record_upserts(monkeypatch)

    with caplog.at_level(logging.INFO):
        match_job.run()

    assert calls == [[("company-2", "opp-1")]]
    record = _finished(caplog)
    assert (record.written, record.unchanged) == (1, 1)


def test_run_makes_no_write_when_nothing_changed(monkeypatch, caplog, two_by_one):
    companies, opportunities = two_by_one
    monkeypatch.setattr(
        match_job,
        "get_existing_scores",
        lambda: {
            (cid, oid): score_values(compute_match_score(company, req))
            for cid, company in companies
            for oid, req in opportunities
        },
    )
    calls = _record_upserts(monkeypatch)

    with caplog.at_level(logging.INFO):
        match_job.run()

    assert calls == []
    assert _finished(caplog).unchanged == 2


def test_run_writes_every_pair_when_stored_scores_cannot_be_read(monkeypatch, caplog, two_by_one):
    def boom():
        raise RuntimeError("Supabase is unreachable")

    monkeypatch.setattr(match_job, "get_existing_scores", boom)
    calls = _record_upserts(monkeypatch)

    with caplog.at_level(logging.INFO):
        match_job.run()

    assert calls == [[("company-1", "opp-1"), ("company-2", "opp-1")]]
    assert _finished(caplog).written == 2


def test_run_writes_in_chunks(monkeypatch, caplog, two_by_one):
    monkeypatch.setattr(match_job, "UPSERT_CHUNK_SIZE", 1)
    calls = _record_upserts(monkeypatch)

    with caplog.at_level(logging.INFO):
        match_job.run()

    assert calls == [[("company-1", "opp-1")], [("company-2", "opp-1")]]


def test_failed_chunk_is_retried_row_by_row(monkeypatch, caplog, two_by_one):
    calls: list[list[tuple[str, str]]] = []

    def upsert(scores):
        pairs = [(c, o) for c, o, _ in scores]
        calls.append(pairs)
        if len(pairs) > 1 or pairs == [("company-2", "opp-1")]:
            raise RuntimeError("simulated DB failure")

    monkeypatch.setattr(match_job, "upsert_match_scores", upsert)

    with caplog.at_level(logging.INFO):
        match_job.run()

    assert calls[1:] == [[("company-1", "opp-1")], [("company-2", "opp-1")]]
    record = _finished(caplog)
    assert (record.status, record.written, record.failed) == ("partial", 1, 1)


def test_repeated_row_failures_stop_further_requests(monkeypatch, caplog):
    companies = [(f"company-{i}", CompanyProfile()) for i in range(10)]
    monkeypatch.setattr(match_job, "get_companies_for_matching", lambda: companies)
    monkeypatch.setattr(
        match_job, "get_analyzed_opportunities", lambda: [("opp-1", OpportunityRequirements())]
    )
    monkeypatch.setattr(match_job, "get_existing_scores", lambda: {})
    calls = []

    def upsert(scores):
        calls.append(len(scores))
        raise RuntimeError("relation does not exist")

    monkeypatch.setattr(match_job, "upsert_match_scores", upsert)

    with caplog.at_level(logging.INFO):
        match_job.run()

    # the chunk, then SYSTEMIC_FAILURE_ROWS single rows, then nothing
    assert calls == [10] + [1] * match_job.SYSTEMIC_FAILURE_ROWS
    assert _finished(caplog).failed == 10


def test_run_no_companies_or_opportunities_is_a_noop(monkeypatch, caplog):
    monkeypatch.setattr(match_job, "get_companies_for_matching", lambda: [])
    monkeypatch.setattr(match_job, "get_analyzed_opportunities", lambda: [])
    monkeypatch.setattr(match_job, "get_existing_scores", lambda: {})
    calls = _record_upserts(monkeypatch)

    with caplog.at_level(logging.INFO):
        match_job.run()

    assert calls == []
    assert _finished(caplog).computed == 0


def test_run_does_not_raise_when_repository_fails(monkeypatch, caplog):
    def boom():
        raise RuntimeError("Supabase is unreachable")

    monkeypatch.setattr(match_job, "get_companies_for_matching", boom)

    with caplog.at_level(logging.ERROR):
        match_job.run()  # must not raise

    assert any("match job failed entirely" in r.message for r in caplog.records)

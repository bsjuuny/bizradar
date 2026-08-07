import logging

from worker.jobs import match_job
from worker.matching.engine import CompanyProfile, OpportunityRequirements


def test_run_computes_score_for_every_company_opportunity_pair(monkeypatch, caplog):
    companies = [
        ("company-1", CompanyProfile(technologies={"Python"})),
        ("company-2", CompanyProfile()),
    ]
    opportunities = [
        ("opp-1", OpportunityRequirements(technologies=["Python"])),
    ]
    monkeypatch.setattr(match_job, "get_companies_for_matching", lambda: companies)
    monkeypatch.setattr(match_job, "get_analyzed_opportunities", lambda: opportunities)

    calls = []
    monkeypatch.setattr(
        match_job,
        "upsert_match_score",
        lambda company_id, opportunity_id, score: calls.append((company_id, opportunity_id)),
    )

    with caplog.at_level(logging.INFO):
        match_job.run()

    assert calls == [("company-1", "opp-1"), ("company-2", "opp-1")]
    assert any("match job finished" in r.message for r in caplog.records)


def test_run_no_companies_or_opportunities_is_a_noop(monkeypatch, caplog):
    monkeypatch.setattr(match_job, "get_companies_for_matching", lambda: [])
    monkeypatch.setattr(match_job, "get_analyzed_opportunities", lambda: [])
    monkeypatch.setattr(
        match_job, "upsert_match_score", lambda *a, **kw: (_ for _ in ()).throw(AssertionError())
    )

    with caplog.at_level(logging.INFO):
        match_job.run()

    finished = [r for r in caplog.records if "match job finished" in r.message]
    assert len(finished) == 1
    assert finished[0].computed == 0


def test_run_does_not_raise_when_repository_fails(monkeypatch, caplog):
    def boom():
        raise RuntimeError("Supabase is unreachable")

    monkeypatch.setattr(match_job, "get_companies_for_matching", boom)

    with caplog.at_level(logging.ERROR):
        match_job.run()  # must not raise

    assert any("match job failed entirely" in r.message for r in caplog.records)

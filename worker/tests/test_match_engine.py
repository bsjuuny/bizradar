from dataclasses import replace
from datetime import UTC, datetime, timedelta

from worker.matching.engine import CompanyProfile, OpportunityRequirements, compute_match_score

NOW = datetime(2026, 8, 7, tzinfo=UTC)

_FULL_COMPANY = CompanyProfile(
    technologies={f"tech{i}" for i in range(30)},
    business_type="SI 전문기업",
    budget_min=0,
    budget_max=1_000_000_000,
    experience_years=10,
    qualifications={"SW사업자"},
    region="서울",
)

_FULL_OPPORTUNITY = OpportunityRequirements(
    technologies=[f"tech{i}" for i in range(30)],
    project_type="SYSTEM_BUILD",
    budget_amount=500_000_000,
    min_experience_years=3,
    required_qualifications=["SW사업자"],
    region_restriction="서울",
    bid_close_at=NOW + timedelta(days=30),
)


def _techs(n: int) -> list[str]:
    return [f"tech{i}" for i in range(n)]


def full_company(**overrides: object) -> CompanyProfile:
    return replace(_FULL_COMPANY, **overrides)  # type: ignore[arg-type]


def full_opportunity(**overrides: object) -> OpportunityRequirements:
    return replace(_FULL_OPPORTUNITY, **overrides)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Named scenarios (section 26 of the original spec)
# ---------------------------------------------------------------------------


def test_perfect_match_scores_100():
    score = compute_match_score(full_company(), full_opportunity(), now=NOW)
    assert score.total == 100


def test_partial_technology_match():
    company = full_company(technologies={"tech0", "tech1"})
    opp = full_opportunity(technologies=_techs(4))  # company matches 2 of 4
    score = compute_match_score(company, opp, now=NOW)
    assert score.technology == 15.0  # 2/4 * 30


def test_budget_out_of_range_scores_zero_on_budget_only():
    company = full_company(budget_min=0, budget_max=100_000_000)
    opp = full_opportunity(budget_amount=500_000_000)
    score = compute_match_score(company, opp, now=NOW)
    assert score.budget == 0.0
    assert score.technology == 30.0  # unaffected


def test_region_mismatch_scores_zero_on_region_only():
    company = full_company(region="부산")
    opp = full_opportunity(region_restriction="서울")
    score = compute_match_score(company, opp, now=NOW)
    assert score.region == 0.0


def test_no_experience_scores_zero_on_experience_only():
    company = full_company(experience_years=1)
    opp = full_opportunity(min_experience_years=5)
    score = compute_match_score(company, opp, now=NOW)
    assert score.experience == 0.0


def test_missing_qualification_scores_zero():
    company = full_company(qualifications=set())
    opp = full_opportunity(required_qualifications=["SW사업자", "정보보호관리체계 인증"])
    score = compute_match_score(company, opp, now=NOW)
    assert score.qualification == 0.0


# ---------------------------------------------------------------------------
# "Nothing required" gets full credit (benefit of the doubt), not disqualified
# ---------------------------------------------------------------------------


def test_no_stated_requirement_gives_full_credit_each_category():
    company = CompanyProfile()  # nothing declared at all
    opp = OpportunityRequirements()  # nothing required at all
    score = compute_match_score(company, opp, now=NOW)
    assert score.total == 100  # no constraints anywhere = nothing to fail


def test_missing_company_data_against_a_real_requirement_scores_zero_not_full():
    # A stated requirement + no company data to confirm it is NOT the same as "no
    # requirement" - this must not silently default to full credit.
    company = CompanyProfile()
    opp = full_opportunity()
    score = compute_match_score(company, opp, now=NOW)
    assert score.business_type == 0.0
    assert score.experience == 0.0
    assert score.qualification == 0.0
    assert score.region == 0.0


def test_no_company_budget_preference_is_flexible_not_unknown():
    # Budget is the deliberate exception: an unset range means "no preference", not
    # "can't confirm" - see the module docstring.
    company = full_company(budget_min=None, budget_max=None)
    opp = full_opportunity(budget_amount=999_999_999)
    score = compute_match_score(company, opp, now=NOW)
    assert score.budget == 15.0


# ---------------------------------------------------------------------------
# Schedule: proximity to the bid deadline
# ---------------------------------------------------------------------------


def test_schedule_full_credit_far_from_deadline():
    opp = full_opportunity(bid_close_at=NOW + timedelta(days=14))
    score = compute_match_score(full_company(), opp, now=NOW)
    assert score.schedule == 5.0


def test_schedule_partial_credit_close_to_deadline():
    opp = full_opportunity(bid_close_at=NOW + timedelta(days=3))
    score = compute_match_score(full_company(), opp, now=NOW)
    assert 0 < score.schedule < 5.0


def test_schedule_zero_after_deadline_passed():
    opp = full_opportunity(bid_close_at=NOW - timedelta(days=1))
    score = compute_match_score(full_company(), opp, now=NOW)
    assert score.schedule == 0.0


def test_schedule_full_credit_when_no_deadline_stated():
    opp = full_opportunity(bid_close_at=None)
    score = compute_match_score(full_company(), opp, now=NOW)
    assert score.schedule == 5.0


# ---------------------------------------------------------------------------
# Exact total-score boundaries (section 26 of the original spec):
# 49 / 50 / 64 / 65 / 79 / 80 / 100
# ---------------------------------------------------------------------------


def test_boundary_100():
    score = compute_match_score(full_company(), full_opportunity(), now=NOW)
    assert score.total == 100


def test_boundary_80():
    company = full_company(technologies=set(_techs(10)))  # 10/30 matched -> 10 pts
    score = compute_match_score(company, full_opportunity(), now=NOW)
    assert score.total == 80


def test_boundary_79():
    company = full_company(technologies=set(_techs(9)))  # 9/30 matched -> 9 pts
    score = compute_match_score(company, full_opportunity(), now=NOW)
    assert score.total == 79


def test_boundary_65():
    # Fail business type: budget+exp+qual+region+schedule (15+15+10+5+5=50) + tech 15/30 = 65
    company = full_company(business_type=None, technologies=set(_techs(15)))
    score = compute_match_score(company, full_opportunity(), now=NOW)
    assert score.total == 65


def test_boundary_64():
    company = full_company(business_type=None, technologies=set(_techs(14)))
    score = compute_match_score(company, full_opportunity(), now=NOW)
    assert score.total == 64


def test_boundary_50():
    company = full_company(business_type=None, technologies=set())
    score = compute_match_score(company, full_opportunity(), now=NOW)
    assert score.total == 50


def test_boundary_49():
    # Fail business type and region: remaining budget+experience+qualification+schedule
    # (15+15+10+5=45) + tech 4/30 (4) = 49
    company = full_company(business_type=None, region="부산", technologies=set(_techs(4)))
    score = compute_match_score(company, full_opportunity(), now=NOW)
    assert score.total == 49

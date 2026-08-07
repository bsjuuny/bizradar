"""Rule-based Match Engine - no LLM (section 25 of the original spec). 100 points:
Technology 30, Business Type 20, Budget 15, Experience 15, Qualification 10, Region 5,
Schedule 5.

Consistent rule across every category: if the OPPORTUNITY doesn't state a requirement,
that category scores full points (nothing to fail against - same "benefit of the doubt"
principle as worker/ai/rule_filter.py). If the opportunity does state a requirement and
the COMPANY hasn't provided the corresponding profile data, the category scores 0 - a
missing requirement is "no constraint", but missing company data is "can't confirm a
fit", and those are not the same thing. Budget is the one deliberate exception: a company
that hasn't set a budget range is read as "no preference" (flexible), not "unknown",
since the range is an optional filter the company opts into, not a declarative fact
about the company.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

TECHNOLOGY_MAX = 30.0
BUSINESS_TYPE_MAX = 20.0
BUDGET_MAX = 15.0
EXPERIENCE_MAX = 15.0
QUALIFICATION_MAX = 10.0
REGION_MAX = 5.0
SCHEDULE_MAX = 5.0

SCHEDULE_COMFORTABLE_DAYS = 7

# Keywords used to fuzzy-match a company's free-text business_type against the AI's
# controlled project_type enum - business_type isn't itself an enum (see
# docs/DATABASE.md's Phase 5 gotchas for why not).
BUSINESS_TYPE_KEYWORDS: dict[str, list[str]] = {
    "SYSTEM_BUILD": ["SI", "시스템", "구축", "개발"],
    "MAINTENANCE": ["유지보수", "운영", "SM"],
    "CONSULTING": ["컨설팅", "자문"],
    "DATA_ANALYTICS": ["데이터", "분석", "BI"],
    "AI_ML": ["AI", "인공지능", "머신러닝", "딥러닝"],
    "INFRASTRUCTURE": ["인프라", "네트워크", "보안", "클라우드"],
}


@dataclass
class CompanyProfile:
    technologies: set[str] = field(default_factory=set)
    business_type: str | None = None
    budget_min: float | None = None
    budget_max: float | None = None
    experience_years: int = 0
    qualifications: set[str] = field(default_factory=set)
    region: str | None = None


@dataclass
class OpportunityRequirements:
    technologies: list[str] = field(default_factory=list)
    project_type: str | None = None
    budget_amount: float | None = None
    min_experience_years: int | None = None
    required_qualifications: list[str] = field(default_factory=list)
    region_restriction: str | None = None
    bid_close_at: datetime | None = None


@dataclass
class MatchScore:
    technology: float
    business_type: float
    budget: float
    experience: float
    qualification: float
    region: float
    schedule: float

    @property
    def total(self) -> float:
        return (
            self.technology
            + self.business_type
            + self.budget
            + self.experience
            + self.qualification
            + self.region
            + self.schedule
        )


def _score_technology(company: CompanyProfile, opp: OpportunityRequirements) -> float:
    if not opp.technologies:
        return TECHNOLOGY_MAX
    company_norm = {t.strip().lower() for t in company.technologies}
    matched = sum(1 for t in opp.technologies if t.strip().lower() in company_norm)
    return min(TECHNOLOGY_MAX, (matched / len(opp.technologies)) * TECHNOLOGY_MAX)


def _score_business_type(company: CompanyProfile, opp: OpportunityRequirements) -> float:
    if not opp.project_type or opp.project_type == "OTHER":
        return BUSINESS_TYPE_MAX
    if not company.business_type:
        return 0.0
    keywords = BUSINESS_TYPE_KEYWORDS.get(opp.project_type, [])
    if not keywords:
        return BUSINESS_TYPE_MAX
    return BUSINESS_TYPE_MAX if any(k in company.business_type for k in keywords) else 0.0


def _score_budget(company: CompanyProfile, opp: OpportunityRequirements) -> float:
    if opp.budget_amount is None:
        return BUDGET_MAX
    if company.budget_min is None and company.budget_max is None:
        return BUDGET_MAX  # no preference declared - treated as flexible, not unknown
    low = company.budget_min if company.budget_min is not None else 0.0
    high = company.budget_max if company.budget_max is not None else float("inf")
    return BUDGET_MAX if low <= opp.budget_amount <= high else 0.0


def _score_experience(company: CompanyProfile, opp: OpportunityRequirements) -> float:
    if opp.min_experience_years is None:
        return EXPERIENCE_MAX
    return EXPERIENCE_MAX if company.experience_years >= opp.min_experience_years else 0.0


def _score_qualification(company: CompanyProfile, opp: OpportunityRequirements) -> float:
    if not opp.required_qualifications:
        return QUALIFICATION_MAX
    required = {q.strip() for q in opp.required_qualifications}
    return QUALIFICATION_MAX if required.issubset(company.qualifications) else 0.0


def _score_region(company: CompanyProfile, opp: OpportunityRequirements) -> float:
    restriction = (opp.region_restriction or "").strip()
    if not restriction or restriction == "제한 없음":
        return REGION_MAX
    if not company.region:
        return 0.0
    return REGION_MAX if company.region in restriction else 0.0


def _score_schedule(opp: OpportunityRequirements, *, now: datetime | None = None) -> float:
    if opp.bid_close_at is None:
        return SCHEDULE_MAX
    reference = now or datetime.now(UTC)
    days_remaining = (opp.bid_close_at - reference).total_seconds() / 86400
    if days_remaining < 0:
        return 0.0
    if days_remaining >= SCHEDULE_COMFORTABLE_DAYS:
        return SCHEDULE_MAX
    return round(SCHEDULE_MAX * (days_remaining / SCHEDULE_COMFORTABLE_DAYS), 2)


def compute_match_score(
    company: CompanyProfile,
    opportunity: OpportunityRequirements,
    *,
    now: datetime | None = None,
) -> MatchScore:
    return MatchScore(
        technology=_score_technology(company, opportunity),
        business_type=_score_business_type(company, opportunity),
        budget=_score_budget(company, opportunity),
        experience=_score_experience(company, opportunity),
        qualification=_score_qualification(company, opportunity),
        region=_score_region(company, opportunity),
        schedule=_score_schedule(opportunity, now=now),
    )

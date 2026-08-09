"""Typed Challenge domain models shared by collectors, analysis, and repositories."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

ChallengeType = Literal[
    "CONTEST",
    "HACKATHON",
    "AI_COMPETITION",
    "DATA_COMPETITION",
    "DEV_COMPETITION",
    "IDEA_COMPETITION",
    "STARTUP_COMPETITION",
    "AWARD",
    "PUBLIC_DATA_COMPETITION",
    "OTHER",
]
PolicyStatus = Literal["REQUIRED", "ALLOWED", "LIMITED", "PROHIBITED", "UNKNOWN"]
ParticipationType = Literal["ONLINE", "OFFLINE", "HYBRID", "UNKNOWN"]
ChallengeStatus = Literal["UPCOMING", "OPEN", "CLOSING_SOON", "CLOSED", "UNKNOWN"]
EligibilityType = Literal[
    "ANYONE",
    "STUDENT",
    "UNIVERSITY",
    "GRADUATE_STUDENT",
    "EMPLOYEE",
    "DEVELOPER",
    "STARTUP",
    "COMPANY",
    "TEAM",
    "REGION_LIMITED",
    "AGE_LIMITED",
    "OTHER",
    "UNKNOWN",
]


class PolicyAssessment(BaseModel):
    status: PolicyStatus = "UNKNOWN"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: str | None = None
    source_section: str | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def unknown_without_evidence(self) -> PolicyAssessment:
        # Missing/ambiguous evidence must never become an affirmative AI permission.
        if self.status == "UNKNOWN":
            self.confidence = 0.0
            self.evidence = None
        elif not self.evidence:
            self.status = "UNKNOWN"
            self.confidence = 0.0
        return self


class ChallengeAIAnalysis(BaseModel):
    challenge_type: ChallengeType = "OTHER"
    ai_policy: PolicyAssessment = Field(default_factory=PolicyAssessment)
    ai_coding: PolicyAssessment = Field(default_factory=PolicyAssessment)
    generative_ai: PolicyAssessment = Field(default_factory=PolicyAssessment)
    ai_image: PolicyAssessment = Field(default_factory=PolicyAssessment)
    ai_video: PolicyAssessment = Field(default_factory=PolicyAssessment)
    ai_audio: PolicyAssessment = Field(default_factory=PolicyAssessment)
    external_ai_api: PolicyAssessment = Field(default_factory=PolicyAssessment)
    prompt_disclosure_required: bool = False
    ai_usage_disclosure_required: bool = False


class ChallengeAttachment(BaseModel):
    name: str
    url: str | None = None
    media_type: str | None = None


class ChallengeNormalized(BaseModel):
    source_id: str
    source_name: str
    source_type: str = "OFFICIAL_HTML"
    source_priority: int = Field(default=10, ge=0)
    external_id: str
    dedupe_key: str
    content_hash: str

    title: str
    summary: str | None = None
    description: str | None = None
    challenge_type: ChallengeType = "OTHER"

    organizer: str | None = None
    host: str | None = None
    sponsor: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    apply_start_date: datetime | None = None
    apply_end_date: datetime | None = None
    result_date: datetime | None = None

    eligibility: str | None = None
    eligibility_type: EligibilityType = "UNKNOWN"
    team_min: int | None = Field(default=None, ge=1)
    team_max: int | None = Field(default=None, ge=1)
    region: str | None = None
    participation_type: ParticipationType = "UNKNOWN"

    prize: str | None = None
    total_prize_amount: int | None = Field(default=None, ge=0)
    currency: str | None = "KRW"
    prize_description: str | None = None

    source_url: str
    application_url: str | None = None
    thumbnail_url: str | None = None
    required_documents: list[str] = Field(default_factory=list)
    submission_requirements: list[str] = Field(default_factory=list)
    technology_keywords: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    attachments: list[ChallengeAttachment] = Field(default_factory=list)

    ai_policy: PolicyAssessment = Field(default_factory=PolicyAssessment)
    generative_ai_policy: PolicyStatus = "UNKNOWN"
    ai_coding_policy: PolicyStatus = "UNKNOWN"
    llm_policy: PolicyStatus = "UNKNOWN"
    ai_image_policy: PolicyStatus = "UNKNOWN"
    ai_video_policy: PolicyStatus = "UNKNOWN"
    ai_audio_policy: PolicyStatus = "UNKNOWN"
    external_ai_api_policy: PolicyStatus = "UNKNOWN"
    prompt_disclosure_required: bool = False
    ai_usage_disclosure_required: bool = False
    analysis_status: Literal["PENDING", "SUCCESS", "FAILED", "RULE_ONLY", "SKIPPED"] = "RULE_ONLY"
    analysis_error: str | None = None

    external_api_policy: str | None = None
    open_source_policy: str | None = None
    copyright_policy: str | None = None
    ownership_policy: str | None = None
    original_text: str
    search_text: str
    status: ChallengeStatus = "UNKNOWN"
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    collected_at: datetime
    last_checked_at: datetime

    @model_validator(mode="after")
    def valid_team_range(self) -> ChallengeNormalized:
        if self.team_min and self.team_max and self.team_min > self.team_max:
            self.team_min = None
            self.team_max = None
        return self


class ChallengeCollectionSummary(BaseModel):
    sources: int = 0
    success: int = 0
    failed: int = 0
    fetched: int = 0
    persisted: int = 0
    skipped: int = 0
    errors: list[str] = Field(default_factory=list)
    duration_seconds: float = 0.0

    @property
    def status(self) -> Literal["SUCCESS", "PARTIAL_SUCCESS", "FAILED"]:
        if self.failed == 0:
            return "SUCCESS"
        if self.success > 0:
            return "PARTIAL_SUCCESS"
        return "FAILED"

"""Structured output schema for AI project analysis. See docs/DATA_PIPELINE.md."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

ProjectType = Literal[
    "SYSTEM_BUILD",
    "MAINTENANCE",
    "CONSULTING",
    "DATA_ANALYTICS",
    "AI_ML",
    "INFRASTRUCTURE",
    "OTHER",
]


class TechnologyMatch(BaseModel):
    name: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: str


class ProjectExtraction(BaseModel):
    """The part an LLM actually generates - no provenance metadata. Validated directly
    against the model's raw JSON output before anything downstream sees it."""

    project_type: ProjectType
    technologies: list[TechnologyMatch] = []
    required_roles: list[str] = []
    requirements: list[str] = []
    risks: list[str] = []
    summary: str = ""
    # Added Phase 5 (worker/matching/engine.py needs these to score Experience/
    # Qualification) - null/empty means "no such requirement stated", not "unknown".
    min_experience_years: int | None = Field(default=None, ge=0)
    required_qualifications: list[str] = []

    @field_validator("required_roles", "requirements", "risks", "required_qualifications")
    @classmethod
    def _dedupe_preserving_order(cls, items: list[str]) -> list[str]:
        # A live run showed a local model repeating the same entry up to the schema's
        # maxItems cap ("정보보호관리체계 인증" x7) - schema-valid, useless output.
        # maxItems bounds the damage (no more timeouts/truncation - see
        # docs/DATA_PIPELINE.md), this removes the exact duplicates that slip through.
        seen: set[str] = set()
        deduped = []
        for item in items:
            if item not in seen:
                seen.add(item)
                deduped.append(item)
        return deduped


class ProjectAnalysis(ProjectExtraction):
    """A ProjectExtraction plus the provenance fields the worker adds, not the LLM."""

    model: str
    model_version: str
    prompt_version: str
    analyzed_at: datetime

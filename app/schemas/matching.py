"""Deterministic, explainable, candidate-aware ranking contracts (Phase 3.2)."""
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.candidate import CandidateProfile
from app.schemas.jobs import JobListing


class JobMatch(BaseModel):
    job: JobListing
    match_score: int = Field(ge=0, le=100, description="Heuristic ranking score, NOT hiring probability")
    relevance: Literal["strong", "partial", "low"]
    eligibility: Literal["needs_review", "likely_ineligible"]
    title_relevant: bool
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills_to_verify: list[str] = Field(default_factory=list)
    review_flags: list[str] = Field(default_factory=list)
    explanation: str


class JobRecommendationsResponse(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    query: str
    model: str
    file_name: str
    candidate_profile: CandidateProfile
    count: int
    jobs_considered: int
    matches: list[JobMatch] = Field(default_factory=list)
    sources_checked: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

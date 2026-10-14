"""Public read-only API contracts for multi-role discovery/recommendations."""
from typing import Literal
from pydantic import BaseModel, Field
from app.schemas.candidate import CandidateProfile
from app.schemas.jobs import JobListing
from app.schemas.matching import JobMatch


class MultiRoleHit(BaseModel):
    job: JobListing
    matched_roles: list[str] = Field(default_factory=list)
    retrieval_score: int = Field(ge=0, description="Keyword/title retrieval score (not job fit)")


class MultiRoleSearchResponse(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    roles: list[str]
    count: int = Field(ge=0)
    jobs_considered: int = Field(ge=0)
    jobs: list[MultiRoleHit] = Field(default_factory=list)
    sources_checked: list[str] = Field(default_factory=list)
    source_result_counts: dict[str, int] = Field(default_factory=dict,
        description="Number of top results displayed from each attempted source (not all fetched listings).")
    source_fetched_counts: dict[str, int] = Field(default_factory=dict,
        description="Number of raw postings retrieved from each source before filters; sources_checked includes attempts.")
    warnings: list[str] = Field(default_factory=list)


class MultiRoleRecommendationsResponse(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    roles: list[str]
    file_name: str
    model: str
    candidate_profile: CandidateProfile
    count: int = Field(ge=0)
    jobs_considered: int = Field(ge=0)
    matches: list[JobMatch] = Field(default_factory=list)
    matched_roles_by_job: dict[str, list[str]] = Field(default_factory=dict)
    sources_checked: list[str] = Field(default_factory=list)
    source_result_counts: dict[str, int] = Field(default_factory=dict,
        description="Number of top results displayed from each attempted source (not all fetched listings).")
    source_fetched_counts: dict[str, int] = Field(default_factory=dict,
        description="Number of raw postings retrieved from each source before filters; sources_checked includes attempts.")
    warnings: list[str] = Field(default_factory=list)

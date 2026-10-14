"""Read-only public response for grouped and diversified discovery (Phase 3.6)."""
from typing import Literal
from pydantic import BaseModel, Field

from app.schemas.jobs import JobListing


class JobVariantResponse(BaseModel):
    job: JobListing
    geographic_status: Literal["needs_review"] = "needs_review"
    geographic_review_flags: list[str] = Field(default_factory=list)
    experience_year_mentions: list[int] = Field(default_factory=list,
        description="Explicit N+ years phrases, not verified minimum experience requirements.")


class JobGroupResponse(BaseModel):
    group_id: str
    title: str
    company: str
    retrieval_score: int
    matched_roles: list[str]
    variant_count: int
    variants: list[JobVariantResponse]


class GroupedSearchResponse(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    roles: list[str]
    count: int
    groups_found: int
    jobs_considered: int
    grouped_jobs: list[JobGroupResponse]
    source_fetched_counts: dict[str, int]
    source_group_counts: dict[str, int] = Field(default_factory=dict,
        description="Groups attributed to source of their top-ranked representative; variants may span providers.")
    sources_checked: list[str]
    warnings: list[str]


# Phase 3.7: groups are ranked by evidenced resume fit, not keyword retrieval.
from app.schemas.candidate import CandidateProfile
from app.schemas.matching import JobMatch


class CandidateMatchedVariant(BaseModel):
    match: JobMatch
    geographic_status: Literal["needs_review"] = "needs_review"
    geographic_review_flags: list[str] = Field(default_factory=list)
    experience_year_mentions: list[int] = Field(default_factory=list)


class CandidateMatchedGroup(BaseModel):
    group_id: str
    company: str
    title: str
    matched_roles: list[str] = Field(default_factory=list)
    group_match_score: int = Field(ge=0, le=100,
        description="Maximum evidence-based technical ranking across variants; not eligibility")
    best_scored_variant_id: str = Field(description="Best technical score only; not eligible to apply")
    variant_count: int
    variants: list[CandidateMatchedVariant]


class GroupedRecommendationsResponse(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    roles: list[str]
    file_name: str
    model: str
    candidate_profile: CandidateProfile
    count: int = Field(ge=0)
    groups_found: int = Field(ge=0)
    jobs_considered: int = Field(ge=0)
    grouped_matches: list[CandidateMatchedGroup] = Field(default_factory=list)
    sources_checked: list[str] = Field(default_factory=list)
    source_fetched_counts: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

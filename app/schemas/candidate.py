"""Evidence-based candidate profile contract: facts versus recommendations."""

from typing import Literal
from pydantic import BaseModel, Field, ConfigDict


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class EvidenceItem(StrictModel):
    name: str = Field(min_length=1, max_length=180)
    source_quote: str = Field(min_length=1, max_length=800)


class WorkExperience(StrictModel):
    job_title: str = Field(min_length=1, max_length=180)
    organization: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    source_quote: str = Field(min_length=1, max_length=800)


class Project(StrictModel):
    name: str = Field(min_length=1, max_length=180)
    technologies: list[str] = Field(default_factory=list)
    source_quote: str = Field(min_length=1, max_length=800)


class Education(StrictModel):
    degree: str = Field(min_length=1, max_length=180)
    institution: str | None = None
    source_quote: str = Field(min_length=1, max_length=800)


class Certification(StrictModel):
    name: str = Field(min_length=1, max_length=180)
    issuer: str | None = None
    source_quote: str = Field(min_length=1, max_length=800)


class RecommendedRole(StrictModel):
    title: str = Field(min_length=1, max_length=160)
    rationale: str = Field(min_length=1, max_length=500)


class CandidateProfile(StrictModel):
    full_name: str | None = None
    headline: str | None = None
    location: str | None = None
    skills: list[EvidenceItem] = Field(default_factory=list)
    experiences: list[WorkExperience] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    certifications: list[Certification] = Field(default_factory=list)
    recommended_roles: list[RecommendedRole] = Field(default_factory=list)


class CandidateAnalysisResponse(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    file_name: str
    model: str
    profile: CandidateProfile
    warnings: list[str] = Field(default_factory=list)

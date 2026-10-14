"""Evidence-constrained local application drafting schemas (Phase 5.0)."""
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.schemas.candidate import CandidateProfile


class PostingForDraft(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    title: str = Field(min_length=2, max_length=240)
    company: str = Field(min_length=1, max_length=160)
    location: str | None = Field(default=None, max_length=200)
    description: str = Field(min_length=30, max_length=18000)


class ApplicationDraftRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    candidate_profile: CandidateProfile
    posting: PostingForDraft

    @field_validator('candidate_profile')
    @classmethod
    def profile_needs_evidence(cls, p):
        if not p.skills and not p.projects and not p.experiences:
            raise ValueError('A profile with resume-based skills, projects, or experience is required')
        return p


class SkillCheck(BaseModel):
    skill: str
    evidence: str


class ApplicationDraftResponse(BaseModel):
    schema_version: str = '1.0'
    generation: str = 'local_evidence_bound_templates'
    job_title: str
    company: str
    matched_skills: list[SkillCheck]
    technologies_to_verify: list[str]
    experience_year_mentions: list[int]
    resume_text: str
    cover_letter_text: str
    review_notes: list[str]

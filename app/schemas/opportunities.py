"""Strict public-job metadata and local follow-up schemas (no resume storage)."""
from datetime import date, datetime
from enum import Enum
from urllib.parse import urlsplit
from pydantic import BaseModel, ConfigDict, Field, field_validator


class Stage(str, Enum):
    saved = 'saved'
    researching = 'researching'
    ready_to_apply = 'ready_to_apply'
    applied = 'applied'
    interview = 'interview'
    offer = 'offer'
    rejected = 'rejected'
    withdrawn = 'withdrawn'
    archived = 'archived'


class OpportunityCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    title: str = Field(min_length=2, max_length=240)
    company: str = Field(min_length=1, max_length=160)
    url: str = Field(min_length=12, max_length=2048)
    source: str = Field(min_length=1, max_length=80)
    source_job_id: str | None = Field(default=None, max_length=250)
    location: str | None = Field(default=None, max_length=200)
    technical_score: int | None = Field(default=None, ge=0, le=100)

    @field_validator('url')
    @classmethod
    def valid_public_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('A public HTTPS job posting URL is required')
        host = parsed.hostname.lower().rstrip('.')
        if (host == 'localhost' or host.endswith('.localhost') or host.endswith('.local')
            or host.endswith('.internal') or host == '0.0.0.0'):
            raise ValueError('Local/private job posting hosts are not accepted')
        try:
            import ipaddress
            ip = ipaddress.ip_address(host)
            if not ip.is_global:
                raise ValueError('Local/private job posting hosts are not accepted')
        except ValueError as exc:
            if 'Local/private' in str(exc):
                raise
        return value


class OpportunityUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    stage: Stage | None = None
    notes: str | None = Field(default=None, max_length=4000)
    next_action_on: date | None = None
    interview_at: datetime | None = None

    @field_validator('notes')
    @classmethod
    def notes_not_null(cls, value):
        if value is None:
            raise ValueError('notes cannot be null; use empty text to clear notes')
        return value

    @field_validator('stage')
    @classmethod
    def stage_not_null(cls, value):
        if value is None:
            raise ValueError('stage cannot be null')
        return value

    @field_validator('interview_at')
    @classmethod
    def interview_timezone(cls, value):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError('interview_at must include a timezone')
        return value


class Activity(BaseModel):
    id: int
    created_at: str
    kind: str
    description: str


class Opportunity(BaseModel):
    id: str
    title: str
    company: str
    url: str
    source: str
    source_job_id: str | None = None
    location: str | None = None
    technical_score: int | None = None
    stage: Stage
    notes: str
    next_action_on: date | None = None
    interview_at: datetime | None = None
    created_at: str
    updated_at: str


class OpportunityList(BaseModel):
    count: int
    opportunities: list[Opportunity]

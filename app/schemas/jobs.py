"""Phase 3.1 normalized public job listing contract."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

class JobListing(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    source: Literal["remotive", "greenhouse", "lever", "ashby"]
    title: str
    company: str
    location: str | None = None
    remote: bool | None = None  # None: unknown; do not assume remote eligibility
    description: str = ""  # plain text, truncated, untrusted content
    url: HttpUrl  # Link to official board/source; NO application submitted
    published_at: str | None = None
    salary: str | None = None

class JobSearchResponse(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    query: str
    count: int = Field(ge=0)
    jobs: list[JobListing] = Field(default_factory=list)
    sources_checked: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

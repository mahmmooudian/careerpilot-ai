"""Public response contract for the resume ingestion endpoint."""

from typing import Literal

from pydantic import BaseModel, Field


class ResumeParseResponse(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    file_name: str
    file_type: Literal["pdf", "docx"]
    page_count: int | None = Field(
        description="Page count for PDF; null for DOCX because pagination requires rendering."
    )
    characters: int = Field(ge=0)
    word_count: int = Field(ge=0)
    raw_text: str
    warnings: list[str] = Field(default_factory=list)

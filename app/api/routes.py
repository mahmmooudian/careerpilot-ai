"""Phase 1 extraction and Phase 2 consent-gated analysis APIs."""

from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from app.core.config import MAX_UPLOAD_BYTES
from app.schemas.candidate import CandidateAnalysisResponse
from app.schemas.resume import ResumeParseResponse
from app.services.candidate_extractor import AIExtractionError, extract_profile
from app.services.resume_parser import ResumeParseError, parse_resume

router = APIRouter(prefix="/api/v1/resumes", tags=["Resumes"])


async def _parse_upload(file: UploadFile) -> ResumeParseResponse:
    try:
        contents = await file.read(MAX_UPLOAD_BYTES + 1)
        return await run_in_threadpool(parse_resume, file.filename or "", contents)
    except ResumeParseError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    finally:
        await file.close()


@router.post(
    "/parse",
    response_model=ResumeParseResponse,
    summary="Parse a PDF or DOCX resume (no external AI request)",
)
async def parse_resume_file(file: Annotated[UploadFile, File(description="PDF or DOCX resume")]):
    return await _parse_upload(file)


@router.post(
    "/analyze",
    response_model=CandidateAnalysisResponse,
    summary="Extract structured candidate profile with external AI (explicit consent)",
    responses={
        400: {"description": "Consent is required"},
        422: {"description": "Unreadable resume"},
        503: {"description": "AI provider not configured"},
        502: {"description": "Provider or model response error"},
        504: {"description": "Provider timeout"},
    },
)
async def analyze_resume_file(
    file: Annotated[UploadFile, File(description="PDF or DOCX resume")],
    consent_to_external_processing: Annotated[bool, Form(description="Required: permit sending extracted resume text to the configured AI provider")] = False,
):
    if not consent_to_external_processing:
        await file.close()
        raise HTTPException(
            status_code=400,
            detail="Explicit consent is required before sending resume data to an external AI provider.",
        )

    parsed = await _parse_upload(file)
    try:
        profile, model, evidence_warnings = await run_in_threadpool(extract_profile, parsed.raw_text)
    except AIExtractionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return CandidateAnalysisResponse(
        file_name=parsed.file_name,
        model=model,
        profile=profile,
        warnings=parsed.warnings + evidence_warnings,
    )

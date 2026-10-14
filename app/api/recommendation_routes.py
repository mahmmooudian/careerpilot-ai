"""Phase 3.2: one-resume, read-only recommendations, with explicit AI consent."""
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from app.api.routes import _parse_upload
from app.schemas.matching import JobRecommendationsResponse
from app.services.candidate_extractor import AIExtractionError, extract_profile
from app.services.job_discovery import JobDiscovery
from app.services.job_matching import rank_jobs

router = APIRouter(prefix="/api/v1/jobs", tags=["Job Matching"])
_discovery = JobDiscovery()  # Request budgets remain per-process, as in Phase 3.1.


@router.post(
    "/recommend", response_model=JobRecommendationsResponse,
    summary="Find and rank jobs from a resume (requires external-AI consent; read-only)",
    responses={
        400: {"description": "Explicit consent required"},
        422: {"description": "Invalid/unreadable file or parameters"},
        503: {"description": "AI provider is not configured"},
        502: {"description": "External AI provider error"},
        504: {"description": "External AI timeout"},
    },
)
async def recommend_jobs(
    file: Annotated[UploadFile, File(description="PDF or DOCX resume")],
    consent_to_external_processing: Annotated[bool, Form(description="Required: extracted resume text sent to configured model provider")] = False,
    query: Annotated[str, Form(min_length=3, max_length=80, description="Target role, e.g. 'machine learning' or 'AI Engineer'")] = "machine learning",
    remote_only: Annotated[bool, Form(description="Limit to remote-labelled jobs")] = True,
    work_country: Annotated[str | None, Form(max_length=80, description="Where you are eligible to work; only used for eligibility warning, never assumed")] = None,
    limit: Annotated[int, Form(ge=1, le=20)] = 10,
):
    if not consent_to_external_processing:
        await file.close()
        raise HTTPException(status_code=400,
                            detail="Explicit consent is required before sending resume data to the external model provider.")
    parsed = await _parse_upload(file)
    try:
        profile, model, evidence_warnings = await run_in_threadpool(extract_profile, parsed.raw_text)
    except AIExtractionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    # Fetch more than final requested count because strict title relevance filters results.
    discovery = await run_in_threadpool(_discovery.search, query, min(50, max(limit * 5, 20)), remote_only)
    matches = rank_jobs(discovery.jobs, profile, query, work_country, limit)
    warnings = parsed.warnings + evidence_warnings + discovery.warnings
    if not matches:
        warnings.append("No title-relevant opportunities found. Try AI Engineer, Data Scientist, or another role/source.")
    warnings.append("Scores are heuristic ranking aids, not probabilities of being hired. Check each official posting and eligibility before applying.")
    return JobRecommendationsResponse(
        file_name=parsed.file_name, model=model, candidate_profile=profile,
        query=query, count=len(matches), jobs_considered=len(discovery.jobs),
        matches=matches, sources_checked=discovery.sources_checked, warnings=warnings,
    )

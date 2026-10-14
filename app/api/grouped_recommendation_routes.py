"""Resume-aware, read-only grouped job suggestions (Phase 3.7)."""
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from app.api.routes import _parse_upload
from app.api import multi_routes
from app.schemas.grouped import GroupedRecommendationsResponse
from app.services.candidate_extractor import AIExtractionError, extract_profile
from app.services.grouped_recommendations import match_groups

router = APIRouter(prefix="/api/v1/jobs", tags=["Grouped Job Recommendations"])


@router.post("/recommend/multi/grouped", response_model=GroupedRecommendationsResponse,
             summary="Match candidate once, rank grouped geographic job variants (read-only)")
async def grouped_recommend(
    file: Annotated[UploadFile, File(description="PDF or DOCX resume")],
    consent_to_external_processing: Annotated[bool, Form(description="Allow external AI resume processing")] = False,
    roles: Annotated[str, Form(min_length=3, max_length=400)] = "AI Engineer,Machine Learning Engineer,RAG Engineer",
    remote_only: Annotated[bool, Form()] = True,
    location_query: Annotated[str | None, Form(max_length=80)] = None,
    work_country: Annotated[str | None, Form(max_length=80)] = None,
    limit: Annotated[int, Form(ge=1, le=20)] = 10,
    diversify: Annotated[bool, Form()] = True,
):
    if not consent_to_external_processing:
        await file.close()
        raise HTTPException(status_code=400, detail="External resume processing requires explicit consent.")
    role_list = multi_routes._roles_or_422(roles)
    parsed = await _parse_upload(file)
    try:
        profile, model, evidence_warnings = await run_in_threadpool(extract_profile, parsed.raw_text)
    except AIExtractionError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e

    discovered = await run_in_threadpool(
        multi_routes._multi.search_multi,
        role_list, 200, remote_only, location_query,
        internal_pool=True,
    )
    matches, total = await run_in_threadpool(
        match_groups, discovered.hits, profile,
        work_country=work_country, limit=limit, diversify=diversify,
    )
    warnings = list(parsed.warnings) + evidence_warnings + list(discovered.warnings)
    warnings.append("Best-scored variant is technical rank only; location, legal work authorization, and commercial years remain unverified.")
    if len(discovered.hits) == 200:
        warnings.append("Ranking evaluated at most 200 top title matches; more listings may exist.")
    if not matches:
        warnings.append("No role-relevant groups found. Add employer boards or try other titles.")
    return GroupedRecommendationsResponse(
        roles=role_list, file_name=parsed.file_name, model=model,
        candidate_profile=profile, count=len(matches), groups_found=total,
        jobs_considered=discovered.jobs_considered, grouped_matches=matches,
        sources_checked=discovered.checked,
        source_fetched_counts=discovered.source_fetched_counts,
        warnings=warnings,
    )

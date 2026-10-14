"""Phase 3.4 multiple-role discovery and one-pass resume matching (read-only)."""
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from starlette.concurrency import run_in_threadpool

from app.api.routes import _parse_upload
from app.api import recommendation_routes
from app.schemas.multi import MultiRoleHit, MultiRoleSearchResponse, MultiRoleRecommendationsResponse
from app.services.candidate_extractor import AIExtractionError, extract_profile
from app.services.job_matching import match_job
from app.services.multi_job_discovery import MultiJobDiscovery, parse_roles

router = APIRouter(prefix="/api/v1/jobs", tags=["Multi-Source Job Discovery"])
_multi = MultiJobDiscovery(recommendation_routes._discovery)  # shared Remotive rate budget/cache


def _roles_or_422(value: str) -> list[str]:
    try:
        return parse_roles(value)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@router.get("/search/multi", response_model=MultiRoleSearchResponse,
            summary="Search several job titles across configured providers (read-only)")
async def multi_search(
    roles: str = Query(..., min_length=3, max_length=400,
                       description="Comma-separated: AI Engineer,Machine Learning Engineer,RAG Engineer"),
    limit: int = Query(20, ge=1, le=30),
    remote_only: bool = Query(False),
    location_query: str | None = Query(None, max_length=80,
         description="Literal location filter, not proof of country eligibility"),
):
    role_list = _roles_or_422(roles)
    result = await run_in_threadpool(_multi.search_multi, role_list, limit, remote_only, location_query)
    return MultiRoleSearchResponse(
        roles=role_list, count=len(result.hits), jobs_considered=result.jobs_considered,
        jobs=[MultiRoleHit(job=h.job, matched_roles=list(h.matched_roles),
                           retrieval_score=h.retrieval_score) for h in result.hits],
        sources_checked=result.checked, source_result_counts=result.source_result_counts,
        source_fetched_counts=result.source_fetched_counts,
        warnings=result.warnings,
    )


@router.post("/recommend/multi", response_model=MultiRoleRecommendationsResponse,
             summary="Find and match multiple job titles, extracting resume only once (read-only)")
async def multi_recommend(
    file: Annotated[UploadFile, File(description="PDF or DOCX resume")],
    consent_to_external_processing: Annotated[bool, Form(description="Explicit consent to send resume text to configured AI provider")] = False,
    roles: Annotated[str, Form(min_length=3, max_length=400)] = "AI Engineer,Machine Learning Engineer,RAG Engineer",
    remote_only: Annotated[bool, Form()] = True,
    location_query: Annotated[str | None, Form(max_length=80)] = None,
    work_country: Annotated[str | None, Form(max_length=80)] = None,
    limit: Annotated[int, Form(ge=1, le=20)] = 10,
):
    # Validate consent and role list before expensive network/model requests.
    if not consent_to_external_processing:
        await file.close()
        raise HTTPException(400, "External resume processing requires explicit consent.")
    role_list = _roles_or_422(roles)
    parsed = await _parse_upload(file)
    try:
        profile, model, evidence_warnings = await run_in_threadpool(extract_profile, parsed.raw_text)
    except AIExtractionError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e

    discovered = await run_in_threadpool(
        _multi.search_multi, role_list, min(30, max(limit * 3, 20)), remote_only, location_query,
    )
    ranked = []
    role_ids: dict[str, list[str]] = {}
    for hit in discovered.hits:
        candidates = [match_job(hit.job, profile, role, work_country)
                      for role in hit.matched_roles]
        options = [m for m in candidates if m is not None]
        if options:
            best = max(options, key=lambda m: m.match_score)
            ranked.append(best)
            role_ids[best.job.id] = list(hit.matched_roles)
    ranked.sort(key=lambda m: (-m.match_score, m.job.title.casefold(), m.job.id))
    matches = ranked[:limit]
    warnings = parsed.warnings + evidence_warnings + discovered.warnings
    warnings.append("Scores rank role relevance, not hiring probability. All country, work authorization and seniority requirements need verification.")
    if not matches:
        warnings.append("No matching title in available sources. Add employer boards or try other role titles.")
    return MultiRoleRecommendationsResponse(
        roles=role_list, file_name=parsed.file_name, model=model, candidate_profile=profile,
        count=len(matches), jobs_considered=discovered.jobs_considered, matches=matches,
        matched_roles_by_job={m.job.id: role_ids[m.job.id] for m in matches},
        sources_checked=discovered.checked, source_result_counts=discovered.source_result_counts,
        source_fetched_counts=discovered.source_fetched_counts,
        warnings=warnings,
    )

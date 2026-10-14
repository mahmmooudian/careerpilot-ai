"""Phase 6: optional advanced public-feed filters; no candidate information."""
from fastapi import APIRouter, Depends, Query
from starlette.concurrency import run_in_threadpool
from app.api import multi_routes
from app.schemas.jobs import JobListing
from app.services.job_intelligence import AdvancedFilters, AdvancedSearchResponse, advanced_search_result

router = APIRouter(prefix='/api/v1/jobs', tags=['Advanced Job Intelligence'])


def search_intelligence(options: AdvancedFilters) -> AdvancedSearchResponse:
    roles = multi_routes._roles_or_422(options.roles)
    discovered = multi_routes._multi.search_multi(
        roles, 200, remote_only=options.remote_only,
        location_query=options.location_query, internal_pool=True,
    )
    return advanced_search_result(discovered, options)

@router.get('/intelligence/search', response_model=AdvancedSearchResponse,
            summary='Advanced read-only job discovery (freshness, seniority and quality checks)')
async def search_endpoint(options: AdvancedFilters = Depends()):
    return await run_in_threadpool(search_intelligence, options)

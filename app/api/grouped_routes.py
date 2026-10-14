"""Phase 3.6: grouped multi-source discovery, without applicant data or external AI."""
from collections import Counter

from fastapi import APIRouter, Query
from starlette.concurrency import run_in_threadpool

from app.api import multi_routes
from app.schemas.grouped import GroupedSearchResponse, JobGroupResponse, JobVariantResponse
from app.services.job_grouping import group_results

router = APIRouter(prefix="/api/v1/jobs", tags=["Grouped Job Discovery"])


def _search(roles: list[str], limit: int, remote_only: bool,
            location_query: str | None, work_country: str | None,
            diversify: bool) -> GroupedSearchResponse:
    # Larger internal retrieval pool, bounded at 200; public /search/multi remains <=30.
    found = multi_routes._multi.search_multi(
        roles, limit=200, remote_only=remote_only,
        location_query=location_query, internal_pool=True,
    )
    groups, total = group_results(found.hits, limit=limit, work_country=work_country,
                                  diversify=diversify)
    source_groups: Counter[str] = Counter()
    serialized = []
    for group in groups:
        lead = group.variants[0].hit.job
        source_key = (lead.id.split(":", 2)[0] + ":" + lead.id.split(":", 2)[1]
                      if lead.source != "remotive" and ":" in lead.id else lead.source)
        source_groups[source_key] += 1
        serialized.append(JobGroupResponse(
            group_id=group.group_id, title=group.title, company=group.company,
            retrieval_score=group.retrieval_score,
            matched_roles=list(group.matched_roles), variant_count=len(group.variants),
            variants=[JobVariantResponse(
                job=v.hit.job, geographic_status=v.geographic_status,
                geographic_review_flags=list(v.review_flags),
                experience_year_mentions=list(v.years_mentions),
            ) for v in group.variants],
        ))
    warnings = list(found.warnings)
    if len(found.hits) == 200:
        warnings.append("Grouping sampled the top 200 title-matching listings; additional matches may exist.")
    if total < len(found.hits):
        warnings.append("Same-company, same-title listings were grouped; each variant URL and location remains available.")
    warnings.append("Geographic status is always needs_review: neither residence nor work authorization is verified.")
    return GroupedSearchResponse(
        roles=roles, count=len(serialized), groups_found=total,
        jobs_considered=found.jobs_considered, grouped_jobs=serialized,
        sources_checked=found.checked, source_fetched_counts=found.source_fetched_counts,
        source_group_counts={s: source_groups[s] for s in found.checked},
        warnings=warnings,
    )


@router.get("/search/multi/grouped", response_model=GroupedSearchResponse,
            summary="Group same-role postings across regions and diversify companies (read-only)")
async def grouped_search(
    roles: str = Query(..., min_length=3, max_length=400),
    limit: int = Query(20, ge=1, le=30, description="Maximum distinct job groups"),
    remote_only: bool = Query(True),
    location_query: str | None = Query(None, max_length=80),
    work_country: str | None = Query(None, max_length=80,
        description="Optional country preference, NOT an assertion of work authorization"),
    diversify: bool = Query(True, description="Apply soft company-diversity ranking"),
):
    role_list = multi_routes._roles_or_422(roles)
    return await run_in_threadpool(_search, role_list, limit, remote_only,
                                   location_query, work_country, diversify)

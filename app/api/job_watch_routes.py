"""Explicit, local-only, user-triggered saved searches (never background monitoring)."""
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from app.api.intelligence_routes import search_intelligence
from app.api.opportunity_routes import local_request_only
from app.services.job_intelligence import AdvancedFilters
from app.services.job_watch_store import WatchStore, WatchNotFound, WatchLimitReached

router = APIRouter(prefix='/api/v1/job-watches', tags=['Saved Job Searches'],
                   dependencies=[Depends(local_request_only)])

class WatchCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=2, max_length=80)
    filters: AdvancedFilters


def get_store() -> WatchStore:
    return WatchStore()

@router.post('', status_code=201)
def create_watch(data: WatchCreate, store: WatchStore = Depends(get_store)):
    try:
        return store.create(data.name, data.filters)
    except WatchLimitReached as exc:
        raise HTTPException(400, 'A maximum of 20 saved searches is supported') from exc

@router.get('')
def list_watches(store: WatchStore = Depends(get_store)):
    return {'watches':store.list()}

@router.delete('/{identifier}', status_code=204)
def delete_watch(identifier: str, store: WatchStore = Depends(get_store)):
    try: store.delete(identifier)
    except WatchNotFound as exc: raise HTTPException(404, 'Saved search not found') from exc
    return Response(status_code=204)

@router.post('/{identifier}/check')
async def check_watch(identifier: str, store: WatchStore = Depends(get_store)):
    try:
        watch = await run_in_threadpool(store.get, identifier)
    except WatchNotFound as exc:
        raise HTTPException(404, 'Saved search not found') from exc
    result = await run_in_threadpool(search_intelligence, AdvancedFilters.model_validate(watch['filters']))
    if result.sources_checked and all(result.source_fetched_counts.get(s, 0) == 0 for s in result.sources_checked) \
       and any('unavailable' in w for w in result.warnings):
        raise HTTPException(503, 'No usable sources responded; saved baseline was not changed')
    try: return await run_in_threadpool(store.record_scan, identifier, result)
    except WatchNotFound as exc: raise HTTPException(404, 'Saved search not found') from exc

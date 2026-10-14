"""Phase 3.1 read-only job-discovery API."""
from fastapi import APIRouter, Query
from starlette.concurrency import run_in_threadpool
from app.schemas.jobs import JobSearchResponse
from app.services.job_discovery import JobDiscovery

router = APIRouter(prefix="/api/v1/jobs", tags=["Job Discovery"])
_discovery = JobDiscovery()  # Per-process cache/budget; Phase 3.2 adds persistent store.

@router.get("/search", response_model=JobSearchResponse,
            summary="Discover published jobs from supported public APIs (read-only)")
async def search_jobs(
    query: str = Query(..., min_length=3, max_length=80,
                       description="Job title or keyword, e.g. machine learning engineer"),
    limit: int = Query(15, ge=1, le=50),
    remote_only: bool = Query(False, description="Return only posts explicitly labelled remote"),
):
    return await run_in_threadpool(_discovery.search, query, limit, remote_only)

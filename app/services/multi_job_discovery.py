"""Phase 3.4: batched, public/read-only multi-role job discovery.

One Remotive snapshot + one request per employer board per cache lifetime.
Only fixed provider hosts are used. No resume data is sent to job providers.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
import time
from typing import Any

import httpx

from app.schemas.jobs import JobListing
from app.services.job_discovery import (
    JobDiscovery, _dedup_key, _match_score, configured_boards,
    normalize_ashby, normalize_greenhouse, normalize_lever,
)
from app.services.job_matching import title_relevance


ROLE_CAP = 5

# Broad mentions of AI are not enough to make a sales/product/annotation
# position an engineering role. Apply this exclusion only for engineering
# role searches, so a user explicitly searching "Product Owner" can still
# discover those jobs using the generic title matcher.
_NON_ENGINEERING_TITLES = re.compile(
    r"\b(?:sales|business development|partnerships?|alliances?|"
    r"go[- ]to[- ]market|gtm|account executive|recruit(?:er|ing|ment)|"
    r"marketing|marketer|growth marketer|demand generation|product owner|product manager|technical product owner|"
    r"product management|code trainer|ai trainer|data annotat\w*|"
    r"growth manager|customer success|prompt annotat\w*)\b",
    re.IGNORECASE,
)


def _engineering_role_query(role: str) -> bool:
    return bool(re.search(
        r"\b(?:ai|ml|machine learning|computer vision|rag|retrieval|"
        r"deep learning|llm|nlp|genai)\b", role, re.IGNORECASE,
    ))


def _role_strength(title: str, role: str) -> int:
    """Title-only retrieval grade, not evidence of a candidate's eligibility."""
    t = title.casefold()
    r = role.casefold()
    if r in t:
        return 4
    if re.search(r"\b(?:engineer|developer|scientist|researcher)\b", t):
        return 3
    if re.search(r"\barchitect\b", t):
        return 2
    return 1


def _specific_role_match(title: str, role: str) -> bool:
    """Prefer actual job-title intent over loose AI-family co-occurrence.

    Generic role-family matching in /recommend is intentionally broader; this
    endpoint has explicit distinct target titles and needs stricter retrieval.
    """
    t = title.casefold()
    r = role.casefold()
    if _engineering_role_query(role) and _NON_ENGINEERING_TITLES.search(title):
        return False
    if "machine learning" in r or re.search(r"\bml engineer\b", r):
        return "machine learning" in t or bool(re.search(r"\bml(?:/ai)?\b", t))
    if "computer vision" in r:
        return "computer vision" in t or "vision engineer" in t
    if re.search(r"\brag\b", r) or "retrieval" in r:
        return bool(re.search(r"\brag\b|retrieval", t))
    if "data scientist" in r or "data science" in r:
        return "data scientist" in t or "data science" in t
    if "ai engineer" in r or "applied ai" in r or "ai developer" in r:
        return bool(re.search(r"\bai\b|artificial intelligence|generative ai|genai", t))
    if "deep learning" in r:
        return "deep learning" in t
    if "power bi" in r:
        return "power bi" in t or "business intelligence" in t
    return title_relevance(title, role)[0]


def parse_roles(roles: str) -> list[str]:
    """Validate a comma-separated list of 1–5 distinctive target job titles."""
    if not isinstance(roles, str) or len(roles) > 400:
        raise ValueError("roles must contain 1–5 titles (maximum 400 characters).")
    result: list[str] = []
    seen: set[str] = set()
    for raw in roles.split(","):
        role = " ".join(raw.strip().split())
        if not 3 <= len(role) <= 80 or any(ord(x) < 32 for x in role):
            raise ValueError("Each role must be between 3 and 80 characters.")
        if role.casefold() not in seen:
            result.append(role)
            seen.add(role.casefold())
    if not 1 <= len(result) <= ROLE_CAP:
        raise ValueError("Provide between 1 and 5 unique job titles.")
    return result


@dataclass(frozen=True)
class RoleHit:
    job: JobListing
    matched_roles: tuple[str, ...]
    retrieval_score: int


@dataclass
class MultiResult:
    roles: list[str]
    hits: list[RoleHit]
    checked: list[str]
    warnings: list[str]
    jobs_considered: int
    source_result_counts: dict[str, int]
    source_fetched_counts: dict[str, int]


class MultiJobDiscovery:
    def __init__(self, underlying: JobDiscovery, clock: Any = time.monotonic):
        self.underlying = underlying
        self.clock = clock
        self._board_cache: dict[tuple[str, str], tuple[float, list[JobListing]]] = {}

    def _employer_board(self, source: str, token: str) -> list[JobListing]:
        key = (source, token.casefold())
        cached = self._board_cache.get(key)
        if cached and self.clock() - cached[0] < 15 * 60:
            return cached[1]
        if source == "greenhouse":
            data = self.underlying._read(
                f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs",
                {"content": "true"},
            )
            if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
                raise ValueError("Unexpected Greenhouse response")
            jobs = normalize_greenhouse(data, token)
        elif source == "lever":
            data = self.underlying._read(
                f"https://api.lever.co/v0/postings/{token}",
                {"mode": "json", "limit": 100},
            )
            if not isinstance(data, list):
                raise ValueError("Unexpected Lever response")
            jobs = normalize_lever(data, token)
        elif source == "ashby":
            data = self.underlying._read(
                f"https://api.ashbyhq.com/posting-api/job-board/{token}",
                {"includeCompensation": "true"},
            )
            if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
                raise ValueError("Unexpected Ashby response")
            jobs = normalize_ashby(data, token)
        else:
            raise ValueError("Unsupported provider")
        self._board_cache[key] = (self.clock(), jobs)
        return jobs

    def search_multi(self, roles: list[str], limit: int = 20,
                     remote_only: bool = False, location_query: str | None = None,
                     *, internal_pool: bool = False) -> MultiResult:
        if not 1 <= len(roles) <= ROLE_CAP or roles != parse_roles(",".join(roles)):
            raise ValueError("Invalid or duplicate roles")
        if not 1 <= limit <= (200 if internal_pool else 30):
            raise ValueError("limit must be between 1 and 30")
        loc = " ".join((location_query or "").split()).casefold()
        if len(loc) > 80 or any(ord(c) < 32 for c in loc):
            raise ValueError("Invalid location_query")

        all_jobs: list[JobListing] = []
        sources: list[str] = []
        warnings: list[str] = []
        fetched_by_source: dict[str, int] = {}

        def fetch(label: str, loader: Any) -> None:
            sources.append(label)
            fetched_by_source[label] = 0
            try:
                jobs = loader()
                fetched_by_source[label] = len(jobs)
                all_jobs.extend(jobs)
            except (httpx.HTTPError, ValueError, TypeError, KeyError, RuntimeError):
                warnings.append(f"{label} unavailable; other sources may still work.")

        import os
        if os.getenv("JOB_REMOTIVE_ENABLED", "true").casefold() == "true":
            # Download once with no search term so all provided roles have a chance.
            fetch("remotive", lambda: self.underlying._remotive(""))
            warnings.append("Remotive snapshot is limited, may lag by 24h; show Remotive attribution and provided URLs.")
        for source, env in (
            ("greenhouse", "JOB_GREENHOUSE_BOARDS"),
            ("lever", "JOB_LEVER_SITES"),
            ("ashby", "JOB_ASHBY_BOARDS"),
        ):
            for token in configured_boards(env):
                fetch(f"{source}:{token}", lambda source=source, token=token: self._employer_board(source, token))

        if not sources:
            warnings.append("No sources enabled: configure JOB_REMOTIVE_ENABLED or employer boards in .env.")
        if not any(x.startswith(("greenhouse:", "lever:", "ashby:")) for x in sources):
            warnings.append("No employer boards configured; only Remotive's remote snapshot is included.")
        if loc:
            warnings.append("Location filter is text matching only; it does not verify work permits, visa eligibility, or hiring regions.")
        if remote_only:
            warnings.append("Remote does not mean worldwide: employer country restrictions and work authorization are not verified.")

        hits: list[RoleHit] = []
        for job in all_jobs:
            if remote_only and job.remote is not True:
                continue
            location = (job.location or "").casefold()
            if loc and loc not in location and not any(x in location for x in ("worldwide", "anywhere", "global")):
                continue
            related = [r for r in roles if _specific_role_match(job.title, r)]
            if not related:
                continue
            # Strict title matching is much more important than mentions buried in a listing.
            retrieval_score = max(
                (32 if _role_strength(job.title, r) == 4 else
                 28 if _role_strength(job.title, r) == 3 else
                 22 if _role_strength(job.title, r) == 2 else 16)
                + _match_score(job, r)
                for r in related
            )
            hits.append(RoleHit(job=job, matched_roles=tuple(related), retrieval_score=retrieval_score))

        hits.sort(key=lambda h: (-h.retrieval_score, h.job.title.casefold(), h.job.id))
        unique: list[RoleHit] = []
        seen_ids: set[str] = set()
        seen_jobs: set[tuple[str, str, str]] = set()
        for hit in hits:
            key = _dedup_key(hit.job)
            if hit.job.id in seen_ids or key in seen_jobs:
                continue
            seen_ids.add(hit.job.id)
            seen_jobs.add(key)
            unique.append(hit)
            if len(unique) >= limit:
                break
        selected_by_source: dict[str, int] = {source: 0 for source in sources}
        for hit in unique:
            parts = hit.job.id.split(":", 2)
            source_key = ":".join(parts[:2]) if len(parts) > 2 else hit.job.source
            if source_key in selected_by_source:
                selected_by_source[source_key] += 1
        empty_sources = [source for source in sources
                         if fetched_by_source.get(source, 0) > 0 and selected_by_source.get(source, 0) == 0]
        if empty_sources:
            warnings.append("Some sources returned jobs but none appeared in the top results: "
                            + ", ".join(empty_sources) + ".")
        blank = sum(1 for hit in unique if not hit.job.description.strip())
        if blank:
            warnings.append(f"{blank} displayed job(s) lack descriptions: verify the original postings before interpreting fit.")
        if unique:
            from collections import Counter
            company_counts = Counter(hit.job.company.casefold() for hit in unique)
            company, count = company_counts.most_common(1)[0]
            if count > len(unique) / 2 and len(unique) >= 6:
                warnings.append("More than half of results come from one company; add more employer boards to diversify discovery.")
        return MultiResult(roles=roles, hits=unique, checked=sources,
                           warnings=warnings, jobs_considered=len(all_jobs),
                           source_result_counts=selected_by_source,
                           source_fetched_counts=fetched_by_source)

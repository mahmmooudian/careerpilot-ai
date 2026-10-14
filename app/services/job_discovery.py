"""Read-only public job discovery. No scraping, candidate data transfer, or applying.

All outbound HTTP requests use fixed source hostnames and strict board-token
validation, preventing URL-supplied SSRF. Tests never depend on network.
"""
from __future__ import annotations

from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
import os
import re
import time
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from app.schemas.jobs import JobListing, JobSearchResponse

BOARD_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")
SEARCH_TERMS = {"a", "an", "the", "and", "for", "of", "in", "to", "with"}

class _PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored = 0
    def handle_data(self, value: str):
        if not self._ignored:
            self.parts.append(value)
    def handle_starttag(self, tag: str, attrs: Any):
        if tag in {"script", "style"}:
            self._ignored += 1
        elif not self._ignored and tag in {"p", "div", "br", "li", "h1", "h2", "h3"}:
            self.parts.append(" ")
    def handle_endtag(self, tag: str):
        if tag in {"script", "style"} and self._ignored:
            self._ignored -= 1

def clean_description(value: str | None) -> str:
    parser = _PlainText()
    parser.feed(unescape(value or ""))
    return re.sub(r"\s+", " ", unescape(" ".join(parser.parts))).strip()[:5000]

def configured_boards(key: str) -> list[str]:
    """Only limited slugs from the .env file are allowed in outbound URL paths."""
    values = re.split(r"[,;]", os.getenv(key, ""))
    seen: set[str] = set()
    result: list[str] = []
    for raw in values:
        slug = raw.strip()
        if slug and BOARD_TOKEN.fullmatch(slug) and slug.casefold() not in seen:
            result.append(slug)
            seen.add(slug.casefold())
        if len(result) >= 8: break
    return result

def is_https_url(value: Any) -> bool:
    if not isinstance(value, str): return False
    try:
        x = urlsplit(value)
        return x.scheme == "https" and bool(x.netloc) and x.username is None and x.password is None
    except ValueError:
        return False

def _to_job(**values: Any) -> JobListing | None:
    if not values.get("title") or not values.get("company") or not is_https_url(values.get("url")):
        return None
    try:
        return JobListing(**values)
    except (ValueError, TypeError):
        return None

def normalize_remotive(data: dict[str, Any]) -> list[JobListing]:
    result = []
    for x in data.get("jobs", [])[:500]:
        if not isinstance(x, dict): continue
        job = _to_job(id=f"remotive:{x.get('id')}", source="remotive", title=x.get("title"),
            company=x.get("company_name"), location=x.get("candidate_required_location"), remote=True,
            description=clean_description(x.get("description")), url=x.get("url"),
            published_at=x.get("publication_date"), salary=x.get("salary") or None)
        if job: result.append(job)
    return result

def normalize_greenhouse(data: dict[str, Any], board: str) -> list[JobListing]:
    result = []
    for x in data.get("jobs", [])[:1000]:
        if not isinstance(x, dict): continue
        location = (x.get("location") or {}).get("name", "")
        job = _to_job(id=f"greenhouse:{board}:{x.get('id')}",source="greenhouse",
            title=x.get("title"), company=board, location=location or None,
            remote=(True if "remote" in location.casefold() else None),
            description=clean_description(x.get("content")), url=x.get("absolute_url"),
            published_at=x.get("updated_at"))
        if job: result.append(job)
    return result

def lever_full_description(posting: dict[str, Any]) -> str:
    """Assemble the full Lever posting text from public v0 posting fields.

    Lever may place requirements under lists[].content and additionalPlain
    instead of descriptionPlain. Treat all provider HTML as untrusted text.
    """
    fragments: list[str] = []
    for key in ("descriptionPlain", "description", "descriptionHtml"):
        value = posting.get(key)
        if isinstance(value, str) and value.strip():
            fragments.append(value)
            break  # alternative formats of the same section
    for section in (posting.get("lists") or []):
        if not isinstance(section, dict):
            continue
        heading = section.get("text")
        content = section.get("content") or section.get("contentPlain")
        if isinstance(heading, str) and heading.strip():
            fragments.append(heading)
        if isinstance(content, str) and content.strip():
            fragments.append(content)
    for key in ("additionalPlain", "additional"):
        value = posting.get(key)
        if isinstance(value, str) and value.strip():
            fragments.append(value)
            break
    return clean_description(" ".join(fragments))


def normalize_lever(data: list[dict[str, Any]], site: str) -> list[JobListing]:
    result = []
    for x in data[:100]:
        if not isinstance(x, dict):continue
        categories=x.get("categories") or {}
        location=categories.get("location") or ""
        worktype=(x.get("workplaceType") or "").casefold()
        job = _to_job(id=f"lever:{site}:{x.get('id')}", source="lever", title=x.get("text"),
            company=site, location=location or None,
            remote=(True if worktype=="remote" or "remote" in location.casefold() else False if worktype=="on-site" else None),
            description=lever_full_description(x),
            url=x.get("hostedUrl"), published_at=None)
        if job: result.append(job)
    return result

def normalize_ashby(data: dict[str, Any], board: str) -> list[JobListing]:
    result = []
    for x in data.get("jobs", [])[:1000]:
        if not isinstance(x, dict) or x.get("isListed") is False:continue
        job = _to_job(id=f"ashby:{board}:{x.get('id') or x.get('jobUrl')}",source="ashby",
            title=x.get("title"),company=board,location=x.get("location"),
            remote=(x.get("isRemote") if isinstance(x.get("isRemote"), bool) else None),
            description=clean_description(x.get("descriptionPlain") or x.get("descriptionHtml")),
            url=x.get("jobUrl"),published_at=x.get("publishedAt"),
            salary=(x.get("compensation") or {}).get("scrapeableCompensationSalarySummary"))
        if job:result.append(job)
    return result

def _match_score(job: JobListing, query: str) -> int:
    """Keyword retrieval ranking ONLY. Not a candidate/job match percentage."""
    terms=[t for t in re.findall(r"[\w+#.-]+", query.casefold()) if t not in SEARCH_TERMS]
    title=job.title.casefold(); desc=job.description.casefold()
    return sum(5 if term in title else 1 if term in desc else 0 for term in terms)

def _dedup_key(job: JobListing) -> tuple[str, str, str]:
    return (re.sub(r"[^a-z0-9]+", "", job.company.casefold()),
            re.sub(r"[^a-z0-9]+", "", job.title.casefold()),
            re.sub(r"[^a-z0-9]+", "", (job.location or "").casefold()))

class JobDiscovery:
    def __init__(self, client: httpx.Client | None = None, clock: Any = time.monotonic):
        self._client = client
        self._clock = clock
        self._cache: dict[str, tuple[float, list[JobListing]]] = {}
        self._remotive_requests = 0
        self._remotive_day = datetime.now(timezone.utc).date()

    def _read(self, url: str, params: dict[str, Any] | None = None) -> Any:
        if self._client is not None:
            response = self._client.get(url, params=params)
        else:
            with httpx.Client(timeout=12.0, follow_redirects=False,
                              headers={"User-Agent": "CareerPilotAI/0.3 (read-only job discovery)",
                                       "Accept": "application/json"}) as client:
                response = client.get(url, params=params)
        response.raise_for_status()
        return response.json()

    def _remotive(self, query: str) -> list[JobListing]:
        key = query.strip().casefold()
        existing = self._cache.get(key)
        if existing and self._clock() - existing[0] < 6*60*60:
            return existing[1]
        today = datetime.now(timezone.utc).date()
        if today != self._remotive_day:
            self._remotive_day = today
            self._remotive_requests = 0
        if self._remotive_requests >= 4:
            raise RuntimeError("Daily Remotive request budget reached (4); try a cached query tomorrow.")
        self._remotive_requests += 1
        # Multi-role search uses one unfiltered Remotive snapshot, not one call per role.
        # Broad snapshot is limited; results are not a complete global job index.
        params = {"search": query, "limit": 100} if query else {"limit": 500}
        data = self._read("https://remotive.com/api/remote-jobs", params)
        if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
            raise ValueError("Unexpected Remotive API response")
        results = normalize_remotive(data)
        self._cache[key] = (self._clock(), results)
        return results

    def search(self, query: str, limit: int = 15, remote_only: bool = False) -> JobSearchResponse:
        query = query.strip()
        warnings: list[str] = []
        sources: list[str] = []
        results: list[JobListing] = []

        def fetch(label: str, loader: Any) -> None:
            sources.append(label)
            try:
                results.extend(loader())
            except (httpx.HTTPError, ValueError, TypeError, KeyError, RuntimeError) as exc:
                # No raw error details/URLs in public output.
                warnings.append(f"{label} unavailable: {type(exc).__name__}. Other sources may still work.")

        if os.getenv("JOB_REMOTIVE_ENABLED", "true").lower() == "true":
            fetch("remotive", lambda: self._remotive(query))
        for board in configured_boards("JOB_GREENHOUSE_BOARDS"):
            fetch(f"greenhouse:{board}", lambda board=board: normalize_greenhouse(
                self._read(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs", {"content": "true"}), board))
        for site in configured_boards("JOB_LEVER_SITES"):
            fetch(f"lever:{site}", lambda site=site: normalize_lever(
                self._read(f"https://api.lever.co/v0/postings/{site}", {"mode": "json", "limit": 100}),site))
        for board in configured_boards("JOB_ASHBY_BOARDS"):
            fetch(f"ashby:{board}", lambda board=board: normalize_ashby(
                self._read(f"https://api.ashbyhq.com/posting-api/job-board/{board}", {"includeCompensation": "true"}),board))
        if not sources:
            warnings.append("No job sources enabled; configure JOB_REMOTIVE_ENABLED or a board in .env")
        if not any(x.startswith("greenhouse:") or x.startswith("ashby:") or x.startswith("lever:") for x in sources):
            warnings.append("Only remote jobs are searched. Configure employer boards to expand coverage.")
        if any(x.startswith("remotive") for x in sources):
            warnings.append("Remotive listings can be delayed by 24h. Attribute Remotive and use the provided Remotive URL.")

        eligible = [j for j in results if not remote_only or j.remote is True]
        matched = [(j, _match_score(j, query)) for j in eligible]
        matched = [(j,s) for j,s in matched if s > 0]  # avoid unrelated board posts
        matched.sort(key=lambda item: (-item[1],item[0].source,item[0].title.casefold()))
        unique: list[JobListing] = []
        seen: set[tuple[str,str,str]] = set()
        for job, _ in matched:
            key=_dedup_key(job)
            if key in seen:continue
            seen.add(key)
            unique.append(job)
            if len(unique) >= limit:break
        return JobSearchResponse(query=query,count=len(unique),jobs=unique,
                                 sources_checked=sources,warnings=warnings)

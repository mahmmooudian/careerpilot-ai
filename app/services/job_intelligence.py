"""Read-only advanced discovery diagnostics.  These rankings are not eligibility checks.

No resume, identity, login, or job application is sent to hiring sites. The
published_at field is untrusted/optional; unknown dates remain unknown.
"""
from __future__ import annotations
from collections import Counter
from datetime import datetime, timezone
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.grouped import JobGroupResponse, JobVariantResponse
from app.services.job_grouping import experience_year_mentions, group_results
from app.services.multi_job_discovery import MultiResult, RoleHit

Source = Literal['all', 'remotive', 'greenhouse', 'lever', 'ashby']
Seniority = Literal['any', 'junior', 'mid', 'senior']

class AdvancedFilters(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    roles: str = Field(default='AI Engineer,Machine Learning Engineer,RAG Engineer', min_length=3, max_length=400)
    limit: int = Field(default=15, ge=1, le=30)
    remote_only: bool = True
    location_query: str | None = Field(default=None, max_length=80)
    work_country: str | None = Field(default=None, max_length=80)
    diversify: bool = True
    source: Source = 'all'
    seniority: Seniority = 'any'
    max_age_days: int | None = Field(default=None, ge=1, le=365)
    include_unknown_dates: bool = False
    max_years_mentioned: int | None = Field(default=None, ge=0, le=25)
    min_description_chars: int = Field(default=0, ge=0, le=500)
    required_keywords: str | None = Field(default=None, max_length=150)
    excluded_keywords: str | None = Field(default=None, max_length=150)

    @field_validator('location_query', 'work_country')
    @classmethod
    def no_control_characters(cls, value):
        if value and any(ord(c) < 32 for c in value):
            raise ValueError('Control characters are not permitted')
        return value

    @field_validator('required_keywords', 'excluded_keywords')
    @classmethod
    def keyword_phrases(cls, value):
        if not value:
            return None
        phrases = [v.strip() for v in value.split(',')]
        if len(phrases) > 5 or any(not 2 <= len(p) <= 35 for p in phrases):
            raise ValueError('Use 1–5 comma-separated phrases (2–35 characters each)')
        if any(any(ord(c) < 32 for c in p) for p in phrases):
            raise ValueError('Control characters are not permitted')
        return ','.join(phrases)

class IntelligenceVariant(JobVariantResponse):
    freshness: Literal['recent', 'older', 'unknown']
    age_days: int | None = None

class IntelligenceGroup(JobGroupResponse):
    variants: list[IntelligenceVariant]

class AdvancedSearchResponse(BaseModel):
    schema_version: Literal['1.0'] = '1.0'
    roles: list[str]
    filters: AdvancedFilters
    count: int
    groups_found: int
    jobs_considered: int
    matching_pool: int
    filtered_variants: int
    unknown_date_variants: int
    excluded_counts: dict[str, int]
    grouped_jobs: list[IntelligenceGroup]
    sources_checked: list[str]
    source_fetched_counts: dict[str, int]
    selected_source_counts: dict[str, int]
    warnings: list[str]


def seniority_of(title: str) -> str:
    if re.search(r'\b(junior|entry[ -]?level|intern|graduate|trainee)\b', title, re.I):
        return 'junior'
    if re.search(r'\b(senior|sr\.?|lead|staff|principal|architect|head|director)\b', title, re.I):
        return 'senior'
    return 'mid'


def posting_age(value: str | None, reference: datetime | None = None) -> int | None:
    if not value:
        return None
    now = reference or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    try:
        published = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        delta = (now.astimezone(timezone.utc) - published.astimezone(timezone.utc)).total_seconds()
        if delta < -86400 or published.year < 2000:  # badly-dated feed, do not claim fresh
            return None
        return max(0, int(delta // 86400))
    except (TypeError, ValueError, OverflowError, AttributeError):
        return None


def keyword_set(value: str | None) -> list[str]:
    return [x.casefold().strip() for x in value.split(',')] if value else []


def apply_advanced_filters(hits: list[RoleHit], options: AdvancedFilters,
                           reference: datetime | None = None):
    included: list[RoleHit] = []
    excluded: Counter[str] = Counter()
    unknown = 0
    required = keyword_set(options.required_keywords)
    forbidden = keyword_set(options.excluded_keywords)
    for hit in hits:
        job = hit.job
        if options.source != 'all' and job.source != options.source:
            excluded['source'] += 1; continue
        if options.seniority != 'any' and seniority_of(job.title) != options.seniority:
            excluded['seniority'] += 1; continue
        if len(job.description.strip()) < options.min_description_chars:
            excluded['description_quality'] += 1; continue
        # Requirement keyword filters intentionally operate on job text, not applicant evidence.
        searchable = f'{job.title} {job.description}'.casefold()
        if required and not all(word in searchable for word in required):
            excluded['required_keywords'] += 1; continue
        if forbidden and any(word in searchable for word in forbidden):
            excluded['excluded_keywords'] += 1; continue
        if options.max_years_mentioned is not None:
            mentions = experience_year_mentions(hit)
            # Caution: this is merely an explicit N+ years *mention*, not proof of requirement.
            if mentions and max(mentions) > options.max_years_mentioned:
                excluded['years_mentions'] += 1; continue
        age = posting_age(job.published_at, reference)
        if age is None:
            unknown += 1
        if options.max_age_days is not None:
            if age is None and not options.include_unknown_dates:
                excluded['unknown_date'] += 1; continue
            if age is not None and age > options.max_age_days:
                excluded['older_than_max_age'] += 1; continue
        included.append(hit)
    return included, dict(excluded), unknown


def advanced_search_result(found: MultiResult, options: AdvancedFilters,
                           reference: datetime | None = None) -> AdvancedSearchResponse:
    hits, excluded, unknown = apply_advanced_filters(found.hits, options, reference)
    groups, total = group_results(hits, limit=options.limit, work_country=options.work_country,
                                  diversify=options.diversify)
    source_counts: Counter[str] = Counter()
    serialized = []
    for group in groups:
        variants = []
        for v in group.variants:
            job = v.hit.job
            age = posting_age(job.published_at, reference)
            source_counts[job.source] += 1
            variants.append(IntelligenceVariant(
                job=job, geographic_status=v.geographic_status,
                geographic_review_flags=list(v.review_flags),
                experience_year_mentions=list(v.years_mentions),
                age_days=age, freshness='unknown' if age is None else
                ('recent' if age <= 30 else 'older'),
            ))
        serialized.append(IntelligenceGroup(
            group_id=group.group_id, title=group.title, company=group.company,
            retrieval_score=group.retrieval_score,
            matched_roles=list(group.matched_roles), variant_count=len(variants),
            variants=variants,
        ))
    warnings = list(found.warnings)
    if len(found.hits) >= 200:
        warnings.append('Advanced filters sampled a maximum of 200 title-relevant results; additional matches may exist.')
    if unknown:
        warnings.append(f'{unknown} title-matching, otherwise-filtered posting(s) have missing/invalid dates; unknown does not mean new.')
    if options.max_age_days is not None:
        warnings.append('Freshness uses the source-provided publication timestamp when available; it is not a live verification that the vacancy is still open.')
    if options.max_years_mentioned is not None:
        warnings.append('Years filter is based on N+ years phrases and may be conservative; verify each original requirement.')
    warnings.append('Remote status, preferred country and job relevance do not verify visa, work authorization or eligibility.')
    warnings.append('No LinkedIn scraping or applications are performed. Additional Greenhouse/Lever/Ashby boards must be explicitly configured.')
    return AdvancedSearchResponse(
        roles=found.roles, filters=options, count=len(serialized), groups_found=total,
        jobs_considered=found.jobs_considered, matching_pool=len(found.hits),
        filtered_variants=len(hits), unknown_date_variants=unknown,
        excluded_counts=excluded, grouped_jobs=serialized,
        sources_checked=found.checked, source_fetched_counts=found.source_fetched_counts,
        selected_source_counts=dict(source_counts), warnings=warnings,
    )

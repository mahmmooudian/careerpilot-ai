"""Phase 3.6: group cross-location job variants without losing their individual URLs.

Title grouping and diversity are discovery features, not applicant-eligibility checks.
Any geographic information is a review hint only. No resume is handled here.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from dataclasses import dataclass
import re
from typing import Iterable

from app.services.multi_job_discovery import RoleHit


def normalize_group_title(value: str) -> str:
    """Normalize punctuation only; preserve seniority and role distinctions."""
    value = value.casefold().replace("&", " and ")
    value = re.sub(r"[^\w]+", " ", value, flags=re.UNICODE)
    return " ".join(value.split())


def group_identity(hit: RoleHit) -> tuple[str, str]:
    # Do not collapse senior vs junior or AI engineer vs solutions architect.
    return (" ".join(hit.job.company.casefold().split()), normalize_group_title(hit.job.title))


def review_geography(hit: RoleHit, work_country: str | None) -> tuple[str, list[str]]:
    """No optimistic eligibility inference; only text-evidenced review prompts."""
    location = (hit.job.location or "").strip()
    description = hit.job.description[:5000]
    messages = []
    if hit.job.remote is True:
        messages.append("Remote is not necessarily worldwide; verify eligible hiring countries and work authorization.")
    if not location:
        messages.append("Employer has not specified a location; geographic eligibility is unknown.")
    elif work_country:
        country = work_country.strip()
        if re.search(r"\b" + re.escape(country) + r"\b", location, flags=re.IGNORECASE):
            messages.append("Preferred country appears in the posting location, but work authorization is not proven.")
        elif re.search(r"\b(?:worldwide|anywhere|global)\b", location, flags=re.IGNORECASE):
            messages.append("Worldwide wording is present; verify any nationality, residency or time-zone restrictions.")
        else:
            messages.append("Preferred country is not explicitly named in this location; employer verification required.")
    else:
        messages.append("No country preference supplied; geographic eligibility cannot be assessed.")
    if re.search(r"\b(?:eligible (?:locations?|countries)|must (?:be )?(?:based|located|reside)|residents? of|only (?:hiring|accepting))\b", description, flags=re.IGNORECASE):
        messages.append("Posting text includes hiring-location or residency wording; review the original description.")
    if re.search(r"\b(?:not a fit|not suitable)\b.{0,130}\b(?:early.career|junior)\b", description, flags=re.I|re.S):
        messages.append("Posting explicitly discourages early-career applicants.")
    return "needs_review", messages


def experience_year_mentions(hit: RoleHit) -> list[int]:
    # These are MENTIONS, not necessarily minimum required years.
    return sorted({int(x) for x in re.findall(
        r"(?<!\d)(\d{1,2})\s*\+\s*years?\b", hit.job.description[:5000], flags=re.I
    ) if 1 <= int(x) <= 25})


@dataclass(frozen=True)
class GroupedVariant:
    hit: RoleHit
    geographic_status: str
    review_flags: tuple[str, ...]
    years_mentions: tuple[int, ...]


@dataclass(frozen=True)
class JobGroup:
    group_id: str
    title: str
    company: str
    retrieval_score: int
    matched_roles: tuple[str, ...]
    variants: tuple[GroupedVariant, ...]


def _group_id(key: tuple[str, str]) -> str:
    # Stable hash, no personal information.
    import hashlib
    return hashlib.sha256((key[0] + "\x00" + key[1]).encode("utf-8")).hexdigest()[:16]


def group_results(hits: Iterable[RoleHit], *, work_country: str | None = None,
                  limit: int = 20, diversify: bool = True) -> tuple[list[JobGroup], int]:
    """Group identical title/company across regions, then diversify displayed groups.

    Only exact normalized titles group, independent URLs and locations retained.
    A soft per-company penalty improves variety without concealing all postings
    if only one company has relevant jobs.
    """
    by_key: dict[tuple[str, str], list[RoleHit]] = defaultdict(list)
    for hit in hits:
        by_key[group_identity(hit)].append(hit)
    groups = []
    for key, variants in by_key.items():
        variants.sort(key=lambda h: (-h.retrieval_score, h.job.location or "", h.job.id))
        lead = variants[0]
        matched = tuple(dict.fromkeys(r for v in variants for r in v.matched_roles))
        group_variants_list = []
        for v in variants:
            status, flags = review_geography(v, work_country)
            group_variants_list.append(GroupedVariant(
                hit=v, geographic_status=status, review_flags=tuple(flags),
                years_mentions=tuple(experience_year_mentions(v)),
            ))
        group_variants = tuple(group_variants_list)
        groups.append(JobGroup(
            group_id=_group_id(key), title=lead.job.title, company=lead.job.company,
            retrieval_score=lead.retrieval_score, matched_roles=matched,
            variants=group_variants,
        ))
    groups.sort(key=lambda g: (-g.retrieval_score, g.title.casefold(), g.group_id))
    total_groups = len(groups)
    selected: list[JobGroup] = []
    counts: Counter[str] = Counter()
    # Group scores are discovery signals; avoid a misleading candidate match %.
    while groups and len(selected) < limit:
        if diversify:
            # Limit preference shift to 12 points, so very low relevance cannot
            # leapfrog genuinely good jobs solely for diversity.
            best = max(range(len(groups)), key=lambda i: (
                groups[i].retrieval_score - 6 * min(counts[groups[i].company.casefold()], 2),
                groups[i].retrieval_score, -i,
            ))
        else:
            best = 0
        chosen = groups.pop(best)
        selected.append(chosen)
        counts[chosen.company.casefold()] += 1
    return selected, total_groups

"""Phase 3.7: one-pass resume analysis with per-location grouped job matching.

This module never declares geographic eligibility, submits applications, or treats
keyword retrieval scores as a person's chance of being hired.
"""
from __future__ import annotations
from collections import Counter
from typing import Iterable

from app.schemas.candidate import CandidateProfile
from app.schemas.grouped import CandidateMatchedGroup, CandidateMatchedVariant
from app.services.job_grouping import group_results
from app.services.job_matching import match_job
from app.services.multi_job_discovery import RoleHit


def match_groups(
    hits: Iterable[RoleHit], profile: CandidateProfile, *,
    work_country: str | None = None, limit: int = 10, diversify: bool = True,
) -> tuple[list[CandidateMatchedGroup], int]:
    """Scores every discovered geographic variant, then groups by employer/title.

    The 'best' variant is the one with highest technical score, NOT a determination
    that the applicant may legally work at the location. All group variants remain
    visible for independent review.
    """
    groups, _ = group_results(hits, limit=200, work_country=work_country, diversify=False)
    scored: list[CandidateMatchedGroup] = []
    for group in groups:
        variants = []
        for variant in group.variants:
            eligible_matches = [
                m for role in variant.hit.matched_roles
                if (m := match_job(variant.hit.job, profile, role, work_country)) is not None
            ]
            if not eligible_matches:
                continue
            best_match = max(eligible_matches, key=lambda m: (m.match_score, m.job.id))
            variants.append(CandidateMatchedVariant(
                match=best_match,
                geographic_status=variant.geographic_status,
                geographic_review_flags=list(variant.review_flags),
                experience_year_mentions=list(variant.years_mentions),
            ))
        if not variants:
            continue
        variants.sort(key=lambda v: (-v.match.match_score, v.match.job.id))
        scored.append(CandidateMatchedGroup(
            group_id=group.group_id, company=group.company, title=group.title,
            matched_roles=list(group.matched_roles),
            group_match_score=variants[0].match.match_score,
            best_scored_variant_id=variants[0].match.job.id,
            variant_count=len(variants), variants=variants,
        ))
    scored.sort(key=lambda g: (-g.group_match_score, g.title.casefold(), g.group_id))
    total = len(scored)
    selected: list[CandidateMatchedGroup] = []
    company_counts: Counter[str] = Counter()
    while scored and len(selected) < limit:
        if diversify:
            index = max(range(len(scored)), key=lambda i: (
                scored[i].group_match_score - 6 * min(company_counts[scored[i].company.casefold()], 2),
                scored[i].group_match_score,
                -i,
            ))
        else:
            index = 0
        choice = scored.pop(index)
        selected.append(choice)
        company_counts[choice.company.casefold()] += 1
    return selected, total

"""Explainable, conservative job ranking with no additional model call.

Never infer work authorization or years of commercial experience from a resume.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re

from app.schemas.candidate import CandidateProfile
from app.schemas.jobs import JobListing
from app.schemas.matching import JobMatch


def _has(text: str, term: str) -> bool:
    return re.search(r"(?<!\w)" + re.escape(term.casefold()) + r"(?!\w)", text.casefold()) is not None


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(_has(text, x) for x in terms)


AI_QUERY_TERMS = ("machine learning", "ml engineer", "ai engineer", "artificial intelligence", "deep learning", "llm", "rag", "agentic ai", "computer vision", "nlp", "ai", "mlops")
AI_TITLES = ("ai engineer", "ai architect", "ai researcher", "ai scientist", "artificial intelligence", "machine learning", "ml engineer", "mlops", "data scientist", "research scientist", "applied scientist", "computer vision", "nlp engineer", "llm", "rag engineer", "deep learning", "ai developer")
DATA_QUERY_TERMS = ("data scientist", "data science", "data analytics", "data analyst", "power bi")
DATA_TITLES = ("data scientist", "data analyst", "analytics engineer", "business intelligence", "bi analyst", "power bi", "machine learning")
BACKEND_QUERY_TERMS = ("backend", "back-end", "software engineer", "full stack", "full-stack", "python developer", "developer")
BACKEND_TITLES = ("backend", "back-end", "software engineer", "full stack", "full-stack", "python developer", "developer")

# Deliberately short, inspectable taxonomy, not an exhaustive skills ontology.
SKILL_ALIASES: dict[str, tuple[str, ...]] = {
    "Python": ("python",),
    "SQL": ("sql",),
    "PyTorch": ("pytorch",),
    "TensorFlow": ("tensorflow",),
    "Scikit-learn": ("scikit-learn", "sklearn"),
    "XGBoost": ("xgboost",),
    "RAG": ("rag", "retrieval-augmented generation"),
    "LLMs": ("llm", "llms", "large language model", "large language models"),
    "LangChain": ("langchain",),
    "LangGraph": ("langgraph",),
    "Pinecone": ("pinecone",),
    "Weaviate": ("weaviate",),
    "Vector databases": ("vector database", "vector databases", "vector db"),
    "Kubernetes": ("kubernetes", "k8s"),
    "Docker": ("docker",),
    "Databricks": ("databricks",),
    "React": ("react", "react.js", "reactjs"),
    "AWS": ("aws", "amazon web services"),
    "GCP": ("gcp", "google cloud platform"),
    "Azure": ("azure",),
    "OpenCV": ("opencv",),
    "Computer Vision": ("computer vision",),
    "Power BI": ("power bi",),
    "C#": ("c#",),
    ".NET": (".net", "dotnet"),
    "Golang": ("golang", "go language"),
    "Agentic AI": ("agentic ai", "ai agent", "ai agents", "agent architectures"),
    "Machine Learning": ("machine learning",),
}

# Requirements in a generic agency's broad marketing list must not be counted.
BOILERPLATE = (
    "not your tech stack?", "not your stack?", "we're placing senior developers",
    "we are placing senior developers", "reach out and we'll match you",
)


def core_description(description: str) -> str:
    text = description[:5000]
    lower = text.casefold()
    cuts = [lower.find(marker) for marker in BOILERPLATE if marker in lower]
    if cuts:
        text = text[:min(cuts)]
    return text[:3000]


def title_relevance(title: str, query: str) -> tuple[bool, int]:
    t = title.casefold()
    q = query.casefold().strip()
    if _contains_any(q, AI_QUERY_TERMS):
        valid = _contains_any(t, AI_TITLES)
        return valid, (37 if _has(t, q) else 30 if valid else 0)
    if _contains_any(q, DATA_QUERY_TERMS):
        valid = _contains_any(t, DATA_TITLES)
        return valid, (37 if _has(t, q) else 29 if valid else 0)
    if _contains_any(q, BACKEND_QUERY_TERMS):
        valid = _contains_any(t, BACKEND_TITLES)
        return valid, (37 if _has(t, q) else 27 if valid else 0)
    # For unfamiliar queries, require meaningful title overlap, never description-only.
    tokens = [t for t in re.findall(r"[a-z0-9+#.]+", q) if t not in {"a", "the", "and", "for", "engineer", "developer", "senior", "junior", "remote"}]
    valid = bool(tokens) and any(_has(title, token) for token in tokens)
    return valid, (35 if valid else 0)


def _candidate_evidence(profile: CandidateProfile) -> str:
    # Only actual candidate facts, not model recommended roles (inferences).
    # A verified skills line may contain an explicit category such as "LLM & RAG",
    # even if the LLM did not return "LLMs" as a separate skill name.
    pieces = [s.name for s in profile.skills]
    pieces += [s.source_quote for s in profile.skills]
    pieces += [profile.headline or ""]
    pieces += [p.name for p in profile.projects]
    # Do not treat LLM-supplied project technologies as verified on their own:
    # the project title quote does not necessarily evidence its technology list.
    # Never include recommended_roles: they are predictions, not CV evidence.
    return " | ".join(pieces)


def _skills_for_job(text: str, evidence: str) -> tuple[list[str], list[str]]:
    matched: list[str] = []
    missing: list[str] = []
    for name, aliases in SKILL_ALIASES.items():
        if any(_has(text, alias) for alias in aliases):
            if any(_has(evidence, alias) for alias in aliases):
                matched.append(name)
            else:
                missing.append(name)
    # Recruiters often list examples, not three separate mandatory skills:
    # "vector databases such as Pinecone or Weaviate" is an OR condition.
    if re.search(r"\bpinecone\s+or\s+weaviate\b|\bweaviate\s+or\s+pinecone\b", text, re.I):
        if "Pinecone" in matched or "Weaviate" in matched:
            missing = [s for s in missing if s not in {"Pinecone", "Weaviate", "Vector databases"}]
        else:
            has_vector_requirement = any(s in missing for s in ("Pinecone", "Weaviate", "Vector databases"))
            missing = [s for s in missing if s not in {"Pinecone", "Weaviate", "Vector databases"}]
            if has_vector_requirement:
                missing.append("Vector databases (Pinecone or Weaviate)")
    return matched, missing


def _freshness_bonus(value: str | None) -> int:
    if not value:
        return 0
    try:
        published = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        days = (datetime.now(timezone.utc) - published).days
        return 7 if 0 <= days <= 30 else 3 if 0 <= days <= 90 else 0
    except ValueError:
        return 0


def _country_assessment(job: JobListing, work_country: str | None) -> tuple[str, list[str]]:
    flags: list[str] = []
    location = (job.location or "").strip()
    if not work_country:
        flags.append("Remote work authorization and geographic eligibility not verified; specify work_country.")
        return "needs_review", flags
    if not location:
        flags.append("Employer has not provided eligible countries; verify work location directly.")
        return "needs_review", flags
    if _contains_any(location, ("worldwide", "anywhere", "global")):
        flags.append("Advertised worldwide, but work authorization and restrictions still need verification.")
        return "needs_review", flags
    if _has(location, work_country):
        flags.append("Country mentioned in posting; work authorization must still be verified.")
        return "needs_review", flags
    # Explicitly named broad region ≠ authorization for a particular country.
    flags.append(f"Posting lists '{location}', but eligibility for '{work_country}' is unconfirmed. Verify before applying.")
    return "needs_review", flags


def match_job(job: JobListing, profile: CandidateProfile, query: str, work_country: str | None = None) -> JobMatch | None:
    relevant, title_score = title_relevance(job.title, query)
    if not relevant:
        return None
    description = core_description(job.description)
    evidence = _candidate_evidence(profile)
    matches, missing = _skills_for_job(description, evidence)
    review_flags: list[str] = []
    eligibility, geographical = _country_assessment(job, work_country)
    review_flags.extend(geographical)
    if not description.strip():
        review_flags.append("Employer job description is missing; skill and experience fit cannot be assessed reliably.")
    if re.search(r"\bsenior\b|\bprincipal\b|\bstaff\b|\barchitect\b", job.title, re.I):
        review_flags.append("Senior/architect role: verify expected seniority against commercial experience.")
    years = sorted(set(int(v) for v in re.findall(r"\b(\d{1,2})\+?\s*years?\b", description, re.I)))
    if years:
        review_flags.append(f"Posting mentions {max(years)}+ years of experience; do not infer qualification from resume dates.")
    if re.search(r"\bnot a fit\b[^.]{0,150}\bearly.career\b", description, re.I | re.S):
        review_flags.append("Posting explicitly excludes early-career applicants.")
    # Transparent heuristic, not calibrated hiring-probability prediction.
    overlap_score = round(36 * len(matches) / max(3, len(matches) + len(missing)))
    # Projects are supporting evidence only when the job mentions a related
    # evidenced technology. The prior unconditional +10 boosted unrelated jobs.
    project_techs = " | ".join(tech for p in profile.projects for tech in p.technologies)
    validated_skill_evidence = " | ".join(s.name + " | " + s.source_quote for s in profile.skills)
    project_bonus = 6 if (matches and any(
        any(_has(project_techs, alias) and _has(validated_skill_evidence, alias)
            for alias in SKILL_ALIASES[name])
        for name in matches
    )) else 0
    seniority_flag = any("Senior/architect" in f for f in review_flags)
    explicit_exclusion = any("explicitly excludes early-career" in f for f in review_flags)
    experience_penalty = (12 if seniority_flag else 0) + (15 if explicit_exclusion else 0)
    score = max(0, min(100, title_score + overlap_score + project_bonus
                            + _freshness_bonus(job.published_at) - experience_penalty))
    if not description.strip():
        score = min(score, 35)  # Title alone must not be treated as strong evidence.

    level = "strong" if score >= 65 else "partial" if score >= 40 else "low"
    title_reason = (f"Exact title match for '{query}'." if _has(job.title, query)
                    else f"Job title is in the relevant role family for '{query}'.")
    rationale = (f"{title_reason} {len(matches)} evidenced skill match(es); "
                 f"{len(missing)} other mentioned technology/skill(s) to verify. "
                 "Eligibility and experience requirements are separate from this ranking score.")
    return JobMatch(job=job, match_score=score, relevance=level, eligibility=eligibility,
                    title_relevant=True, matched_skills=matches, missing_skills_to_verify=missing,
                    review_flags=review_flags, explanation=rationale)


def rank_jobs(jobs: list[JobListing], profile: CandidateProfile, query: str,
              work_country: str | None = None, limit: int = 10) -> list[JobMatch]:
    ranked = [m for job in jobs if (m := match_job(job, profile, query, work_country)) is not None]
    ranked.sort(key=lambda m: (-m.match_score, m.job.title.casefold(), m.job.id))
    return ranked[:limit]

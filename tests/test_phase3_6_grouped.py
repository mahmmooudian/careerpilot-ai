"""Phase 3.6 regression tests - no external network / no LLM required."""
import httpx
from fastapi.testclient import TestClient
from app.main import app
from app.api import multi_routes
from app.schemas.jobs import JobListing
from app.services.job_discovery import JobDiscovery
from app.services.job_grouping import group_results, review_geography, experience_year_mentions
from app.services.multi_job_discovery import MultiJobDiscovery, RoleHit


def hit(id, title, company, location, score=42, desc="Python"):
    return RoleHit(job=JobListing(
        id=id, source="lever", company=company, title=title,
        url=f"https://jobs.lever.co/{company.lower()}/{id.rsplit(':',1)[-1]}",
        location=location, remote=True, description=desc,
    ), matched_roles=("AI Engineer",), retrieval_score=score)


def test_groups_keep_all_location_variants_and_urls():
    items = [
        hit("lever:example:1", "Senior AI/ML Engineer", "Example", "Armenia"),
        hit("lever:example:2", "Senior AI/ML Engineer", "Example", "Ukraine"),
        hit("lever:example:3", "Junior AI/ML Engineer", "Example", "Armenia"),
    ]
    groups, count = group_results(items, limit=20)
    assert count == 2
    senior = next(g for g in groups if "Senior" in g.title)
    assert len(senior.variants) == 2
    assert {v.hit.job.location for v in senior.variants} == {"Ukraine", "Armenia"}
    assert len({str(v.hit.job.url) for v in senior.variants}) == 2
    assert all(v.geographic_status == "needs_review" for v in senior.variants)


def test_grouping_preserves_distinct_company_and_seniority():
    items = [hit("lever:example:1", "Senior AI Engineer", "Example", "France"),
             hit("lever:other:2", "Senior AI Engineer", "Other", "France"),
             hit("lever:example:3", "AI Engineer", "Example", "France")]
    assert group_results(items)[1] == 3


def test_group_ids_deterministic_and_location_independent():
    a = hit("lever:example:1", "AI Engineer", "Example", "Armenia")
    b = hit("lever:example:2", "AI Engineer", "Example", "Spain")
    assert group_results([a])[0][0].group_id == group_results([b])[0][0].group_id


def test_diversity_promotes_second_company_without_overpowering_relevance():
    # Second company's 38 beats repeated Company A's 42 after a 6pt penalty.
    items = [hit("lever:a:1", "AI Engineer", "A", "A", 43),
             hit("lever:a:2", "Senior AI Engineer", "A", "A", 42),
             hit("lever:b:3", "Applied AI Engineer", "B", "B", 38)]
    groups, _ = group_results(items, limit=2, diversify=True)
    assert [g.company for g in groups] == ["A", "B"]
    groups, _ = group_results(items, limit=2, diversify=False)
    assert [g.company for g in groups] == ["A", "A"]


def test_diversity_does_not_hide_jobs_when_only_one_company():
    items = [hit(f"lever:acme:{i}", f"AI Engineer {i}", "Acme", str(i), 40) for i in range(7)]
    grouped, count = group_results(items, limit=5)
    assert count == 7 and len(grouped) == 5


def test_geography_is_never_definitively_eligible():
    a = hit("lever:x:1", "AI Engineer", "X", "Armenia")
    status, flags = review_geography(a, "Armenia")
    assert status == "needs_review"
    assert any("authorization is not proven" in f for f in flags)
    _, flags = review_geography(a, "Germany")
    assert any("not explicitly named" in f for f in flags)
    _, flags = review_geography(a, None)
    assert any("No country preference" in f for f in flags)


def test_experience_is_only_a_mention_not_proven_eligibility():
    a = hit("lever:x:1", "Senior AI Engineer", "X", "USA", desc=(
        "Requirements: 8+ years building software. At least 5+ years in production. "
        "Not a fit: early-career engineers."))
    assert experience_year_mentions(a) == [5, 8]
    _, flags = review_geography(a, "USA")
    assert any("early-career" in f for f in flags)


def test_grouped_api_responds_with_source_counts_and_variants(monkeypatch):
    monkeypatch.setenv("JOB_REMOTIVE_ENABLED", "false")
    monkeypatch.setenv("JOB_GREENHOUSE_BOARDS", "")
    monkeypatch.setenv("JOB_ASHBY_BOARDS", "")
    monkeypatch.setenv("JOB_LEVER_SITES", "demo")
    def handle(request):
        return httpx.Response(200, json=[
            {"id":"a","text":"Senior AI Engineer","workplaceType":"remote",
             "categories":{"location":"Armenia"}, "hostedUrl":"https://jobs.lever.co/demo/a",
             "descriptionPlain":"Requires 6+ years production experience"},
            {"id":"b","text":"Senior AI Engineer","workplaceType":"remote",
             "categories":{"location":"Ukraine"}, "hostedUrl":"https://jobs.lever.co/demo/b",
             "descriptionPlain":"Requires 6+ years production experience"},
            {"id":"c","text":"Junior AI Engineer","workplaceType":"remote",
             "categories":{"location":"Yerevan"}, "hostedUrl":"https://jobs.lever.co/demo/c",
             "descriptionPlain":"Python"},
        ])
    svc = MultiJobDiscovery(JobDiscovery(client=httpx.Client(transport=httpx.MockTransport(handle))))
    monkeypatch.setattr(multi_routes, "_multi", svc)
    with TestClient(app) as c:
        resp = c.get("/api/v1/jobs/search/multi/grouped", params={
            "roles":"AI Engineer", "limit":10, "remote_only": "true",
            "work_country":"Armenia"})
    assert resp.status_code == 200, resp.text
    j = resp.json()
    assert j["count"] == j["groups_found"] == 2
    assert j["source_fetched_counts"]["lever:demo"] == 3
    assert j["source_group_counts"]["lever:demo"] == 2
    senior = next(g for g in j["grouped_jobs"] if "Senior" in g["title"])
    assert senior["variant_count"] == 2
    assert {v["job"]["location"] for v in senior["variants"]} == {"Armenia", "Ukraine"}
    assert all(v["geographic_status"] == "needs_review" for v in senior["variants"])
    assert all(v["experience_year_mentions"] == [6] for v in senior["variants"])

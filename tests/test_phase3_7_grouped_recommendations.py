"""Phase 3.7 offline regressions (no external AI key or live job API)."""
import httpx
from fastapi.testclient import TestClient

from app.api import multi_routes, grouped_recommendation_routes
from app.main import app
from app.schemas.candidate import CandidateProfile, EvidenceItem
from app.schemas.jobs import JobListing
from app.services.grouped_recommendations import match_groups
from app.services.job_discovery import JobDiscovery
from app.services.multi_job_discovery import MultiJobDiscovery, RoleHit, _specific_role_match
from tests.test_api import make_pdf


def hit(jobid, title, company, location, desc="Requires Python RAG", score=40):
    return RoleHit(job=JobListing(
        id=f"lever:{company}:{jobid}", source="lever", title=title, company=company,
        location=location, remote=True, description=desc,
        url=f"https://jobs.lever.co/{company}/{jobid}"
    ), matched_roles=("AI Engineer",), retrieval_score=score)


def profile():
    return CandidateProfile(skills=[EvidenceItem(name="Python", source_quote="Programming: Python")])


def test_marketer_does_not_leak_into_engineering_role():
    assert not _specific_role_match("Growth Marketer, AI-Native", "AI Engineer")
    assert not _specific_role_match("AI Content Marketer", "AI Engineer")
    assert not _specific_role_match("AI Marketing Specialist", "AI Engineer")
    assert _specific_role_match("Junior AI/ML Engineer", "AI Engineer")
    assert _specific_role_match("Growth Marketer, AI-Native", "Growth Marketer")


def test_grouped_recommendation_preserves_each_location_and_best_score():
    hits = [
        hit("1", "Junior AI Engineer", "a", "Yerevan", "Python RAG"),
        hit("2", "Junior AI Engineer", "a", "Ukraine", "Python RAG LangChain"),
        hit("3", "Senior AI Engineer", "a", "USA", "Python RAG; 8+ years commercial experience"),
    ]
    groups, count = match_groups(hits, profile(), work_country="Armenia", limit=10)
    assert len(groups) == count == 2
    junior = next(x for x in groups if "Junior" in x.title)
    assert junior.variant_count == 2
    assert {v.match.job.location for v in junior.variants} == {"Ukraine", "Yerevan"}
    assert junior.group_match_score == max(v.match.match_score for v in junior.variants)
    assert junior.best_scored_variant_id == junior.variants[0].match.job.id
    assert all(v.geographic_status == "needs_review" for v in junior.variants)
    assert all(v.match.eligibility == "needs_review" for v in junior.variants)
    assert all(any("authorization" in f or "verification" in f for f in v.geographic_review_flags)
               for v in junior.variants)


def test_candidate_score_overrides_retrieval_order_and_deprioritizes_senior():
    hits = [
        hit("1", "Senior AI Engineer", "a", "USA", "8+ years production. LangChain Kubernetes.", score=90),
        hit("2", "Junior AI Engineer", "b", "Yerevan", "Python RAG", score=38),
    ]
    groups, _ = match_groups(hits, profile(), diversify=False)
    assert groups[0].title == "Junior AI Engineer"


def test_groups_with_same_company_do_not_sum_scores():
    hits = [hit(str(i), "Junior AI Engineer", "a", f"Country {i}", "Python", 40) for i in range(10)]
    groups, total = match_groups(hits, profile(), limit=3)
    assert total == len(groups) == 1
    assert groups[0].variant_count == 10
    assert groups[0].group_match_score <= 100


def test_api_consent_malformed_roles_and_one_extraction(monkeypatch):
    monkeypatch.setenv("JOB_REMOTIVE_ENABLED", "false")
    monkeypatch.setenv("JOB_GREENHOUSE_BOARDS", "")
    monkeypatch.setenv("JOB_ASHBY_BOARDS", "")
    monkeypatch.setenv("JOB_LEVER_SITES", "demo")
    calls = []
    def responder(request):
        calls.append(request.url.host)
        return httpx.Response(200, json=[
            {"id":"one", "text":"Junior AI Engineer", "workplaceType":"remote",
             "categories":{"location":"Yerevan"}, "hostedUrl":"https://jobs.lever.co/demo/one",
             "descriptionPlain":"Python RAG, 2+ years"},
            {"id":"two", "text":"Junior AI Engineer", "workplaceType":"remote",
             "categories":{"location":"Ukraine"}, "hostedUrl":"https://jobs.lever.co/demo/two",
             "descriptionPlain":"Python RAG, 2+ years"},
            {"id":"three", "text":"Growth Marketer, AI-Native", "workplaceType":"remote",
             "categories":{"location":"New York"}, "hostedUrl":"https://jobs.lever.co/demo/three",
             "descriptionPlain":"Python AI"},
        ])
    svc=MultiJobDiscovery(JobDiscovery(client=httpx.Client(transport=httpx.MockTransport(responder))))
    monkeypatch.setattr(multi_routes, "_multi", svc)
    extraction_calls = []
    def extract(text):
        extraction_calls.append(text)
        return profile(), "mock-model", []
    monkeypatch.setattr(grouped_recommendation_routes, "extract_profile", extract)
    with TestClient(app) as client:
        bad = client.post("/api/v1/jobs/recommend/multi/grouped",
            data={"consent_to_external_processing":"false"},
            files={"file":("resume.pdf",make_pdf("Python skill"),"application/pdf")})
        assert bad.status_code == 400
        bad_roles = client.post("/api/v1/jobs/recommend/multi/grouped",
            data={"consent_to_external_processing":"true", "roles":"AI Engineer,"},
            files={"file":("resume.pdf",make_pdf("Python skill"),"application/pdf")})
        assert bad_roles.status_code == 422
        assert not extraction_calls and not calls
        response = client.post("/api/v1/jobs/recommend/multi/grouped",
            data={"consent_to_external_processing":"true", "roles":"AI Engineer",
                  "limit":"10", "diversify":"true", "work_country":"Armenia"},
            files={"file":("resume.pdf",make_pdf("Python skill"),"application/pdf")})
    assert response.status_code == 200, response.text
    data = response.json()
    assert len(extraction_calls) == 1
    assert calls == ["api.lever.co"]
    assert data["count"] == 1 and data["groups_found"] == 1
    assert len(data["grouped_matches"][0]["variants"]) == 2
    assert data["source_fetched_counts"]["lever:demo"] == 3
    assert data["grouped_matches"][0]["best_scored_variant_id"].startswith("lever:demo:")
    assert all(v["match"]["eligibility"] == "needs_review"
        for v in data["grouped_matches"][0]["variants"])
    assert any("technical rank only" in w for w in data["warnings"])


def test_no_source_returns_valid_empty_grouped_response(monkeypatch):
    monkeypatch.setenv("JOB_REMOTIVE_ENABLED", "false")
    for v in ("JOB_GREENHOUSE_BOARDS", "JOB_ASHBY_BOARDS", "JOB_LEVER_SITES"):
        monkeypatch.setenv(v, "")
    svc=MultiJobDiscovery(JobDiscovery(client=httpx.Client(transport=httpx.MockTransport(lambda req: None))))
    monkeypatch.setattr(multi_routes, "_multi", svc)
    monkeypatch.setattr(grouped_recommendation_routes, "extract_profile", lambda text: (profile(),"mock", []))
    with TestClient(app) as client:
        response = client.post("/api/v1/jobs/recommend/multi/grouped",
            data={"consent_to_external_processing":"true","roles":"AI Engineer"},
            files={"file":("resume.pdf",make_pdf("Python skill"),"application/pdf")})
    assert response.status_code == 200, response.text
    assert response.json()["grouped_matches"] == []
    assert response.json()["count"] == 0

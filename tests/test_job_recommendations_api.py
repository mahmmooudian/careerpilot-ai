"""API contract tests: external AI opt-in and read-only matching orchestration."""
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.candidate import CandidateProfile, EvidenceItem
from app.schemas.jobs import JobListing, JobSearchResponse
from app.api import recommendation_routes as routes
from tests.test_api import make_pdf

client = TestClient(app)


def test_recommend_requires_external_consent():
    res = client.post("/api/v1/jobs/recommend", files={"file": ("cv.pdf", make_pdf("Python and AI Engineer resume"), "application/pdf")})
    assert res.status_code == 400


def test_recommend_response_filters_irrelevance(monkeypatch):
    profile = CandidateProfile(skills=[EvidenceItem(name="Python", source_quote="Python")])
    monkeypatch.setattr(routes, "extract_profile", lambda _: (profile, "test-model", []))
    called = []

    def fake_search(query, limit, remote):
        called.append((query, limit, remote))
        items = [JobListing(id="1", source="remotive", title="Senior AI Engineer", company="Example",
                            remote=True, url="https://example.com/1", description="Python required"),
                 JobListing(id="2", source="remotive", title="Inside Sales Contractor", company="Example",
                            remote=True, url="https://example.com/2", description="machine learning startups")]
        return JobSearchResponse(query=query, count=len(items), jobs=items, sources_checked=["remotive"])

    monkeypatch.setattr(routes._discovery, "search", fake_search)
    res = client.post("/api/v1/jobs/recommend", data={"consent_to_external_processing":"true",
                                                "query":"machine learning", "work_country":"Iran", "limit":"10"},
                      files={"file": ("cv.pdf", make_pdf("Python and AI Engineer resume"), "application/pdf")})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["count"] == 1
    assert body["jobs_considered"] == 2
    assert body["matches"][0]["job"]["title"] == "Senior AI Engineer"
    assert body["matches"][0]["eligibility"] == "needs_review"
    assert called[0][0] == "machine learning"
    assert called[0][2] is True


def test_malformed_consent_must_fail_before_provider(monkeypatch):
    monkeypatch.setattr(routes, "extract_profile", lambda _: (_ for _ in ()).throw(AssertionError("must not call")))
    res = client.post("/api/v1/jobs/recommend", data={"consent_to_external_processing":"false"},
                      files={"file": ("cv.pdf", make_pdf("Python and AI Engineer resume"), "application/pdf")})
    assert res.status_code == 400

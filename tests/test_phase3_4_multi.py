"""Offline Phase 3.4 tests: batched, deduplicated, low-call, consent-gated."""
import httpx
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.schemas.candidate import CandidateProfile, EvidenceItem
from app.services.job_discovery import JobDiscovery
from app.services.multi_job_discovery import MultiJobDiscovery, parse_roles
from app.api import multi_routes
from tests.test_api import make_pdf


def all_providers(monkeypatch, remotive=True):
    monkeypatch.setenv("JOB_REMOTIVE_ENABLED", "true" if remotive else "false")
    monkeypatch.setenv("JOB_GREENHOUSE_BOARDS", "gh-company")
    monkeypatch.setenv("JOB_LEVER_SITES", "lever-company")
    monkeypatch.setenv("JOB_ASHBY_BOARDS", "ash-company")


def mock_providers(request):
    host = request.url.host
    if host == "remotive.com":
        return httpx.Response(200, json={"jobs": [
            {"id": 1,"title":"Machine Learning Engineer", "company_name":"Example One",
             "candidate_required_location":"Worldwide", "url":"https://remotive.com/remote-jobs/1",
             "description":"Python PyTorch"},
            {"id": 2,"title":"Inside Sales Contractor", "company_name":"SalesCo",
             "candidate_required_location":"Worldwide", "url":"https://remotive.com/remote-jobs/2",
             "description":"machine learning artificial intelligence"},
        ]})
    if host == "boards-api.greenhouse.io":
        return httpx.Response(200, json={"jobs": [
            {"id":3,"title":"Applied AI Engineer", "location":{"name":"Berlin, Germany"},
             "absolute_url":"https://job-boards.greenhouse.io/gh-company/jobs/3",
             "content":"Python RAG"}]})
    if host == "api.lever.co":
        return httpx.Response(200, json=[
            {"id":"4", "text":"RAG Engineer", "workplaceType":"remote",
             "categories":{"location":"Remote EU"}, "descriptionPlain":"Python LLM",
             "hostedUrl":"https://jobs.lever.co/lever-company/4"}])
    if host == "api.ashbyhq.com":
        return httpx.Response(200, json={"jobs": [
            {"id":"5","title":"Computer Vision Engineer", "location":"Remote Europe",
             "isRemote":True, "jobUrl":"https://jobs.ashbyhq.com/ash-company/5",
             "descriptionPlain":"OpenCV"}]})
    raise AssertionError(f"unexpected outbound host {host}")


def test_roles_parser_contract():
    assert parse_roles(" AI Engineer , RAG Engineer, ai engineer ") == ["AI Engineer","RAG Engineer"]
    for roles in ("", "ai", "AI Engineer,", "a"*81, ",".join(f"Role{i}" for i in range(6))):
        with pytest.raises(ValueError):
            parse_roles(roles)


def test_fetch_each_source_once_and_cache(monkeypatch):
    all_providers(monkeypatch)
    calls = []
    def handler(request):
        calls.append(request)
        return mock_providers(request)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    svc = MultiJobDiscovery(JobDiscovery(client=client, clock=lambda:100), clock=lambda:100)
    roles = ["Machine Learning Engineer", "AI Engineer", "RAG Engineer", "Computer Vision Engineer"]
    first = svc.search_multi(roles, 20)
    second = svc.search_multi(roles, 20)
    assert len(calls) == 4  # 1 Remotive + 3 boards across both queries
    assert len(first.hits) == len(second.hits) == 4
    assert len(first.checked) == 4
    assert not any(x.job.title == "Inside Sales Contractor" for x in first.hits)
    assert all(x.matched_roles for x in first.hits)
    assert sum(req.url.host == "remotive.com" for req in calls) == 1
    assert all(req.url.scheme == "https" for req in calls)


def test_remote_unknown_and_location_are_distinct(monkeypatch):
    all_providers(monkeypatch, remotive=False)
    svc = MultiJobDiscovery(JobDiscovery(client=httpx.Client(transport=httpx.MockTransport(mock_providers))))
    x = svc.search_multi(["AI Engineer", "RAG Engineer"], remote_only=True)
    assert [h.job.title for h in x.hits] == ["RAG Engineer"]
    y = svc.search_multi(["AI Engineer", "RAG Engineer"], remote_only=False, location_query="Germany")
    assert [h.job.title for h in y.hits] == ["Applied AI Engineer"]
    assert any("work permits" in w for w in y.warnings)


def test_bad_source_does_not_hide_other_sources(monkeypatch):
    all_providers(monkeypatch)
    def handler(request):
        if request.url.host == "api.lever.co":
            return httpx.Response(503)
        return mock_providers(request)
    svc=MultiJobDiscovery(JobDiscovery(client=httpx.Client(transport=httpx.MockTransport(handler))))
    x=svc.search_multi(["AI Engineer", "Computer Vision Engineer"])
    assert x.hits
    assert any("lever:lever-company unavailable" in w for w in x.warnings)


def test_multi_search_api_and_malformed_roles(monkeypatch):
    all_providers(monkeypatch)
    svc = MultiJobDiscovery(JobDiscovery(client=httpx.Client(transport=httpx.MockTransport(mock_providers))))
    monkeypatch.setattr(multi_routes, "_multi", svc)
    with TestClient(app) as c:
        r=c.get("/api/v1/jobs/search/multi",params={"roles":"AI Engineer,RAG Engineer","limit":10})
        assert r.status_code==200, r.text
        data=r.json()
        assert data["count"]==2
        assert "matched_roles" in data["jobs"][0]
        assert "sources_checked" in data
        bad=c.get("/api/v1/jobs/search/multi",params={"roles":"AI Engineer,","limit":10})
        assert bad.status_code==422


def test_multi_recommend_one_extraction_and_approval_gate(monkeypatch):
    all_providers(monkeypatch)
    svc = MultiJobDiscovery(JobDiscovery(client=httpx.Client(transport=httpx.MockTransport(mock_providers))))
    monkeypatch.setattr(multi_routes, "_multi", svc)
    calls=[]
    def fake_extract(text):
        calls.append(text)
        return CandidateProfile(skills=[EvidenceItem(name="Python", source_quote="Python")]), "mock-model", []
    monkeypatch.setattr(multi_routes, "extract_profile", fake_extract)
    with TestClient(app) as c:
        fail=c.post("/api/v1/jobs/recommend/multi", data={"consent_to_external_processing":"false"},
            files={"file":("resume.pdf",make_pdf("Python experience"),"application/pdf")})
        assert fail.status_code==400
        assert not calls
        ok=c.post("/api/v1/jobs/recommend/multi", data={
            "consent_to_external_processing":"true","roles":"AI Engineer,RAG Engineer",
            "remote_only":"false","work_country":"Germany", "limit":5},
            files={"file":("resume.pdf",make_pdf("Python experience"),"application/pdf")})
        assert ok.status_code==200,ok.text
        doc=ok.json()
        assert doc["count"] >= 1
        assert len(calls)==1
        assert len(doc["matched_roles_by_job"])==doc["count"]
        assert all(m["eligibility"] != "eligible" for m in doc["matches"])


def test_config_token_injection_blocked(monkeypatch):
    monkeypatch.setenv("JOB_REMOTIVE_ENABLED", "false")
    monkeypatch.setenv("JOB_GREENHOUSE_BOARDS", "http://evil.com,../escape,valid")
    monkeypatch.setenv("JOB_LEVER_SITES", "")
    monkeypatch.setenv("JOB_ASHBY_BOARDS", "")
    hosts=[]
    def handler(request):
        hosts.append(request.url.host)
        return httpx.Response(200,json={"jobs":[]})
    svc=MultiJobDiscovery(JobDiscovery(client=httpx.Client(transport=httpx.MockTransport(handler))))
    svc.search_multi(["AI Engineer"])
    assert hosts==["boards-api.greenhouse.io"]

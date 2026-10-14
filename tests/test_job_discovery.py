"""Offline tests: no job API calls or application submissions."""
import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.job_discovery import (
    JobDiscovery, clean_description, configured_boards, normalize_ashby,
    normalize_greenhouse, normalize_lever, normalize_remotive,
)


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_remotive_search_normalizes_attribution_and_url(monkeypatch):
    monkeypatch.setenv("JOB_REMOTIVE_ENABLED", "true")
    monkeypatch.setenv("JOB_GREENHOUSE_BOARDS", "")
    monkeypatch.setenv("JOB_LEVER_SITES", "")
    monkeypatch.setenv("JOB_ASHBY_BOARDS", "")
    calls = []
    def handle(request):
        calls.append(str(request.url))
        assert request.url.host == "remotive.com"
        assert "machine" in str(request.url)
        return httpx.Response(200, json={"jobs": [
            {"id": 17, "title": "Machine Learning Engineer", "company_name": "ExampleCo",
             "candidate_required_location": "Worldwide", "url": "https://remotive.com/remote-jobs/17",
             "description": "<p>We use <b>PyTorch</b></p>", "publication_date": "2026-10-01"}
        ]})
    service = JobDiscovery(client=_client(handle))
    result = service.search("machine learning", limit=5, remote_only=True)
    assert result.count == 1
    job = result.jobs[0]
    assert job.source == "remotive"
    assert str(job.url) == "https://remotive.com/remote-jobs/17"
    assert job.description == "We use PyTorch"
    assert calls and "remotive" in result.sources_checked
    assert "Remotive" in " ".join(result.warnings)


def test_remotive_cache_saves_requests(monkeypatch):
    monkeypatch.setenv("JOB_REMOTIVE_ENABLED", "true")
    for key in ("JOB_GREENHOUSE_BOARDS", "JOB_LEVER_SITES", "JOB_ASHBY_BOARDS"):
        monkeypatch.setenv(key, "")
    calls = []
    def handle(request):
        calls.append(request)
        return httpx.Response(200, json={"jobs": []})
    service=JobDiscovery(client=_client(handle), clock=lambda: 10)
    service.search("ML Engineer")
    service.search("ML Engineer")
    assert len(calls) == 1


def test_remotive_daily_budget_fails_gracefully(monkeypatch):
    monkeypatch.setenv("JOB_REMOTIVE_ENABLED", "true")
    for key in ("JOB_GREENHOUSE_BOARDS", "JOB_LEVER_SITES", "JOB_ASHBY_BOARDS"):
        monkeypatch.setenv(key, "")
    calls = []
    def handle(request):
        calls.append(request)
        return httpx.Response(200, json={"jobs": []})
    service=JobDiscovery(client=_client(handle))
    for q in ("machine", "pytorch", "computer", "vision", "analytics"):
        last = service.search(q)
    assert len(calls)==4
    assert last.count == 0
    assert any("remotive unavailable" in x for x in last.warnings)


def test_ats_adapters_and_remote_unknown():
    greenhouse=normalize_greenhouse({"jobs":[
        {"id":1,"title":"Data Scientist","location":{"name":"Remote - Germany"},
         "absolute_url":"https://job-boards.greenhouse.io/example/jobs/1","content":"<p>SQL</p>"}]},"example")
    assert greenhouse[0].remote is True
    assert greenhouse[0].company == "example"
    lever=normalize_lever([{"id":"ab", "text":"AI Engineer", "categories":{"location":"Berlin"},
                           "hostedUrl":"https://jobs.lever.co/abc/ab", "descriptionPlain":"LLM tools"}],"abc")
    assert lever[0].remote is None
    ashby=normalize_ashby({"jobs":[
        {"id":"id","title":"ML Engineer","location":"Dublin", "isRemote": False,
         "jobUrl":"https://jobs.ashbyhq.com/example/id", "descriptionPlain":"Machine Learning"},
        {"id":"secret","isListed":False,"title":"Hidden", "jobUrl":"https://jobs.ashbyhq.com/test/secret"}
    ]},"example")
    assert len(ashby)==1 and ashby[0].remote is False


def test_board_tokens_reject_ssrf(monkeypatch):
    monkeypatch.setenv("JOB_GREENHOUSE_BOARDS", "abc,../../etc/passwd,https://evil.com,abc,name_ok")
    assert configured_boards("JOB_GREENHOUSE_BOARDS") == ["abc", "name_ok"]


def test_suspicious_url_rejected():
    data={"jobs":[{"id":3,"title":"Data Scientist","company_name":"Bad",
                   "url":"javascript:alert(1)","description":"Python"}]}
    assert normalize_remotive(data)==[]


def test_remote_filter_does_not_assume_eligibility(monkeypatch):
    monkeypatch.setenv("JOB_REMOTIVE_ENABLED", "false")
    monkeypatch.setenv("JOB_GREENHOUSE_BOARDS", "test")
    monkeypatch.setenv("JOB_LEVER_SITES", "")
    monkeypatch.setenv("JOB_ASHBY_BOARDS", "")
    def handle(request):
        return httpx.Response(200,json={"jobs": [{
            "id":1, "title":"AI Engineer", "location":{"name":"Berlin"},
            "absolute_url":"https://job-boards.greenhouse.io/test/jobs/1"}]})
    service=JobDiscovery(client=_client(handle))
    assert service.search("AI Engineer",remote_only=True).count==0
    assert service.search("AI Engineer",remote_only=False).count==1


def test_provider_failure_is_isolated(monkeypatch):
    monkeypatch.setenv("JOB_REMOTIVE_ENABLED", "false")
    monkeypatch.setenv("JOB_GREENHOUSE_BOARDS", "missing")
    monkeypatch.setenv("JOB_LEVER_SITES", "abc")
    monkeypatch.setenv("JOB_ASHBY_BOARDS", "")
    def handle(request):
        if "greenhouse" in request.url.host:
            return httpx.Response(500)
        return httpx.Response(200,json=[{
            "id":"123","text":"Machine Learning Engineer", "categories":{"location":"Remote"},
            "hostedUrl":"https://jobs.lever.co/abc/123", "descriptionPlain":"PyTorch"}])
    result=JobDiscovery(client=_client(handle)).search("machine learning")
    assert result.count==1
    assert any("greenhouse:missing unavailable" in w for w in result.warnings)


def test_keyword_scoring_vs_personalized_matching(monkeypatch):
    monkeypatch.setenv("JOB_REMOTIVE_ENABLED", "false")
    monkeypatch.setenv("JOB_GREENHOUSE_BOARDS", "")
    monkeypatch.setenv("JOB_LEVER_SITES", "abc")
    monkeypatch.setenv("JOB_ASHBY_BOARDS", "")
    def handle(request):
        return httpx.Response(200,json=[
            {"id":"a","text":"Marketing Manager","hostedUrl":"https://jobs.lever.co/abc/a", "description":"Sales"},
            {"id":"b","text":"Machine Learning Engineer","hostedUrl":"https://jobs.lever.co/abc/b", "description":"PyTorch"},
            {"id":"c","text":"Software Engineer","hostedUrl":"https://jobs.lever.co/abc/c", "description":"<p>Machine learning models</p>"}
        ])
    result=JobDiscovery(client=_client(handle)).search("machine learning",limit=2)
    assert [j.title for j in result.jobs]==["Machine Learning Engineer","Software Engineer"]
    assert not hasattr(result.jobs[0],"match_percentage")


def test_api_validates_parameters():
    with TestClient(app) as c:
        assert c.get("/api/v1/jobs/search",params={"query":"a"}).status_code==422
        assert c.get("/api/v1/jobs/search",params={"query":"machine learning","limit":100}).status_code==422
    assert "Job Discovery" in [tag["name"] for tag in app.openapi()["tags"]] if "tags" in app.openapi() else True


def test_description_html_is_plain_text():
    assert clean_description("<script>alert('x')</script><p>Python &amp; SQL</p>") == "Python & SQL"

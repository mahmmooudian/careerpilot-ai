"""Phase 3.5: tests for false-positive titles and incomplete provider postings.

No network access, no credentials, and no applicant data required.
"""
import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.api import multi_routes
from app.schemas.candidate import CandidateProfile, EvidenceItem
from app.schemas.jobs import JobListing
from app.services.job_discovery import JobDiscovery, normalize_lever, lever_full_description
from app.services.job_matching import match_job
from app.services.multi_job_discovery import MultiJobDiscovery, _specific_role_match


def test_non_engineering_ai_title_is_not_an_ai_engineer():
    false_positives = [
        "Go to Market (GTM) Partnerships & Alliances Associate – AI Consulting Solutions",
        "Technical Product Owner | GenAI Delivery (Mid-level)",
        "Software Engineer / AI Code Trainer (Python, Web, Full Stack)",
        "Sales Manager – Generative AI",
        "AI Recruiter",
    ]
    assert all(not _specific_role_match(t, "AI Engineer") for t in false_positives)
    # Users searching for a non-engineering role should still be able to do so.
    assert _specific_role_match("Technical Product Owner | GenAI Delivery", "Product Owner")


def test_engineering_titles_and_multiple_roles_still_match():
    assert _specific_role_match("Junior AI/ML Engineer (GenAI, AWS)", "AI Engineer")
    assert _specific_role_match("Junior AI/ML Engineer (GenAI, AWS)", "Machine Learning Engineer")
    assert _specific_role_match("Senior AI Engineer", "AI Engineer")
    assert _specific_role_match("RAG Engineer", "RAG Engineer")
    assert _specific_role_match("Forward Deployed AI Architect", "AI Engineer")


def test_lever_rich_text_sections_and_html_cleaned():
    posting = {
        "id": "p1", "text": "AI Engineer", "hostedUrl": "https://jobs.lever.co/demo/p1",
        "workplaceType": "remote", "categories": {"location": "Yerevan"},
        "descriptionPlain": "Build customer-facing AI systems.",
        "lists": [{"text": "Requirements", "content": "<ul><li>Python</li><li>RAG</li><li>Docker</li></ul>"}],
        "additionalPlain": "Must have relevant commercial experience.",
    }
    value = normalize_lever([posting], "demo")[0]
    assert "Build customer-facing" in value.description
    assert "Requirements" in value.description
    assert all(x in value.description for x in ("Python", "RAG", "Docker", "commercial"))
    assert "<li>" not in value.description


def test_lever_missing_description_not_fabricated_and_no_script():
    posting = {"id": "p2", "text": "AI Engineer", "hostedUrl": "https://jobs.lever.co/demo/p2",
               "categories": {"location": "Yerevan"}, "workplaceType": "remote"}
    job = normalize_lever([posting], "demo")[0]
    assert job.description == ""
    assert "bad" not in lever_full_description({"description": "<script>bad</script><p>Good</p>"})


def test_missing_description_never_gets_strong_fit_score():
    job = JobListing(id="lever:demo:1", source="lever", title="AI Engineer", company="Demo",
                     location="Yerevan", remote=True, description="", url="https://jobs.lever.co/demo/1")
    profile = CandidateProfile(skills=[EvidenceItem(name="Python", source_quote="Python")])
    match = match_job(job, profile, "AI Engineer")
    assert match is not None
    assert match.match_score <= 35
    assert match.eligibility == "needs_review"
    assert any("description is missing" in x for x in match.review_flags)


def source_responder(request):
    if request.url.host == "remotive.com":
        return httpx.Response(200, json={"jobs": [
            {"id":1,"title":"AI Engineer","company_name":"RemoteCo",
             "candidate_required_location":"Worldwide","url":"https://remotive.com/remote-jobs/1",
             "description":"Python and RAG"}
        ]})
    if request.url.host == "api.lever.co":
        return httpx.Response(200, json=[
            {"id":"a", "text":"Junior AI/ML Engineer", "categories":{"location":"Armenia"},
             "workplaceType":"remote", "hostedUrl":"https://jobs.lever.co/demo/a",
             "descriptionPlain":"Python LLM"},
            {"id":"b", "text":"GTM Partnerships – AI Consulting", "categories":{"location":"Armenia"},
             "workplaceType":"remote", "hostedUrl":"https://jobs.lever.co/demo/b"},
            {"id":"c", "text":"Technical Product Owner | GenAI Delivery", "categories":{"location":"Armenia"},
             "workplaceType":"remote", "hostedUrl":"https://jobs.lever.co/demo/c"},
        ])
    if request.url.host == "boards-api.greenhouse.io":
        return httpx.Response(200, json={"jobs":[
            {"id":3,"title":"Accountant", "location":{"name":"Remote"},
             "absolute_url":"https://job-boards.greenhouse.io/demo/jobs/3"}
        ]})
    if request.url.host == "api.ashbyhq.com":
        return httpx.Response(200, json={"jobs":[]})
    raise AssertionError("Unexpected provider")


def configured(monkeypatch):
    monkeypatch.setenv("JOB_REMOTIVE_ENABLED", "true")
    monkeypatch.setenv("JOB_LEVER_SITES", "demo")
    monkeypatch.setenv("JOB_GREENHOUSE_BOARDS", "demo")
    monkeypatch.setenv("JOB_ASHBY_BOARDS", "demo")


def test_source_counts_mean_selected_not_only_checked(monkeypatch):
    configured(monkeypatch)
    svc = MultiJobDiscovery(JobDiscovery(client=httpx.Client(transport=httpx.MockTransport(source_responder))))
    result = svc.search_multi(["AI Engineer", "Machine Learning Engineer"], limit=20, remote_only=True)
    assert len(result.checked) == 4
    assert result.jobs_considered == 5
    assert len(result.hits) == 2
    assert result.source_fetched_counts == {
        "remotive":1, "greenhouse:demo":1, "lever:demo":3, "ashby:demo":0
    }
    assert result.source_result_counts == {
        "remotive":1, "greenhouse:demo":0, "lever:demo":1, "ashby:demo":0
    }
    assert any("Remote does not mean worldwide" in w for w in result.warnings)
    assert any("Some sources returned jobs" in w for w in result.warnings)


def test_api_has_source_diagnostics_in_multisearch(monkeypatch):
    configured(monkeypatch)
    svc = MultiJobDiscovery(JobDiscovery(client=httpx.Client(transport=httpx.MockTransport(source_responder))))
    monkeypatch.setattr(multi_routes, "_multi", svc)
    with TestClient(app) as c:
        response = c.get("/api/v1/jobs/search/multi", params={
            "roles":"AI Engineer,Machine Learning Engineer", "remote_only":"true", "limit":20
        })
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["source_fetched_counts"]["lever:demo"] == 3
        assert data["source_result_counts"]["lever:demo"] == 1
        assert data["count"] == 2


def test_empty_desc_warning_in_multisearch(monkeypatch):
    monkeypatch.setenv("JOB_REMOTIVE_ENABLED", "false")
    monkeypatch.setenv("JOB_GREENHOUSE_BOARDS", "")
    monkeypatch.setenv("JOB_ASHBY_BOARDS", "")
    monkeypatch.setenv("JOB_LEVER_SITES", "demo")
    def response(request):
        return httpx.Response(200,json=[{"id":"no-desc","text":"AI Engineer","workplaceType":"remote",
          "hostedUrl":"https://jobs.lever.co/demo/no-desc","categories":{"location":"Remote US"}}])
    svc=MultiJobDiscovery(JobDiscovery(client=httpx.Client(transport=httpx.MockTransport(response))))
    out=svc.search_multi(["AI Engineer"],remote_only=True)
    assert out.hits and out.hits[0].job.description == ""
    assert any("lack descriptions" in w for w in out.warnings)


def test_source_counts_are_board_specific(monkeypatch):
    monkeypatch.setenv("JOB_REMOTIVE_ENABLED", "false")
    monkeypatch.setenv("JOB_GREENHOUSE_BOARDS", "")
    monkeypatch.setenv("JOB_ASHBY_BOARDS", "")
    monkeypatch.setenv("JOB_LEVER_SITES", "demo,extra")
    def response(request):
        board=request.url.path.split("/")[-1]
        return httpx.Response(200,json=[{"id":board, "text":"AI Engineer",
            "workplaceType":"remote","categories":{"location":"EU"},
            "hostedUrl":f"https://jobs.lever.co/{board}/{board}", "descriptionPlain":"Python"}])
    svc=MultiJobDiscovery(JobDiscovery(client=httpx.Client(transport=httpx.MockTransport(response))))
    result=svc.search_multi(["AI Engineer"],remote_only=True)
    assert result.source_result_counts["lever:demo"] == 1
    assert result.source_result_counts["lever:extra"] == 1

"""Phase 3.9 regressions: resume metadata strictly grounded; UI remains opt-in.

No network calls or actual personal CV required.
"""
import json
import httpx
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.candidate import CandidateProfile
from app.services.candidate_extractor import validate_evidence, extract_profile

SAMPLE = """Jane Doe
SUMMARY
ML / AI Engineer
PROFESSIONAL EXPERIENCE
AI Researcher
Example University | City, Country
Apr 2026 – Present
• Develop explainable machine learning systems.
AI Developer
Example Innovations Co. | City, Country
Feb 2025 – Nov 2025
• Built ML models.
Data Engineer
Example Innovations | City, Country
Mar 2025 – Sep 2025
• Built ETL.
SELECTED PROJECTS
Vision System
Technologies: PyTorch |Github
EDUCATION
B.Sc. Computer Science | Example University | 2019 - 2025
SKILLS
Python, PyTorch
"""


def _profile(**kwargs):
    base = {"experiences": [
        {"job_title": "AI Researcher", "source_quote": "AI Researcher"},
        {"job_title": "AI Developer", "source_quote": "AI Developer"},
        {"job_title": "Data Engineer", "source_quote": "Data Engineer"},
    ], "education": [{"degree": "B.Sc. Computer Science", "source_quote": "B.Sc. Computer Science"}]}
    return CandidateProfile.model_validate({**base, **kwargs})


def test_recover_exact_work_metadata_for_three_realistic_roles():
    profile, warnings = validate_evidence(_profile(), SAMPLE)
    assert [(v.organization, v.start_date, v.end_date) for v in profile.experiences] == [
        ("Example University", "Apr 2026", "Present"),
        ("Example Innovations Co.", "Feb 2025", "Nov 2025"),
        ("Example Innovations", "Mar 2025", "Sep 2025"),
    ]
    assert profile.education[0].institution == "Example University"
    assert all(v.organization in v.source_quote for v in profile.experiences)
    assert all(v.start_date in v.source_quote for v in profile.experiences)
    assert any("Recovered explicit employer/date" in w for w in warnings)


def test_no_fabricated_fields_when_only_titles_present():
    profile, warnings = validate_evidence(_profile(), "PROFESSIONAL EXPERIENCE\nAI Researcher\nAI Developer\nData Engineer\nEDUCATION\nB.Sc. Computer Science")
    assert all(e.organization is None and e.start_date is None and e.end_date is None for e in profile.experiences)
    assert profile.education[0].institution is None
    assert not any("Recovered" in w for w in warnings)


def test_no_metadata_from_projects_or_other_sections():
    raw = "PROFESSIONAL EXPERIENCE\nAI Researcher\nSELECTED PROJECTS\nExample University | 2026 - Present\nAI Developer\nFake Agency | Anywhere\nFeb 2025 – Nov 2025\nEDUCATION\nB.Sc. Computer Science"
    profile, _ = validate_evidence(_profile(), raw)
    assert all(x.organization is None for x in profile.experiences)


def test_no_bleed_between_adjacent_job_titles():
    raw = "PROFESSIONAL EXPERIENCE\nAI Researcher\nAI Developer\nExample Innovations Co. | Remote\nFeb 2025 – Nov 2025\nEDUCATION\nB.Sc. Computer Science"
    profile, _ = validate_evidence(_profile(), raw)
    assert profile.experiences[0].organization is None
    assert profile.experiences[0].start_date is None
    assert profile.experiences[1].organization == "Example Innovations Co."


def test_multiple_identical_titles_not_resolved_by_guess():
    raw = "PROFESSIONAL EXPERIENCE\nAI Researcher\nCompany A | Remote\nJan 2024 – Dec 2024\nAI Researcher\nCompany B | Remote\nJan 2025 – Present"
    profile = CandidateProfile.model_validate({"experiences": [
        {"job_title": "AI Researcher", "source_quote": "AI Researcher"}]})
    result, _ = validate_evidence(profile, raw)
    assert result.experiences[0].organization is None


def test_existing_evidenced_experience_not_overwritten():
    profile, _ = validate_evidence(_profile(experiences=[{
        "job_title": "AI Researcher", "organization": "Example University",
        "start_date": "Apr 2026", "end_date": "Present", "source_quote": "AI Researcher"}]), SAMPLE)
    assert profile.experiences[0].organization == "Example University"


def test_inline_role_employer_date_remains_grounded():
    raw = "PROFESSIONAL EXPERIENCE\nAI Developer — Demo Labs | Remote, Mar 2025 – Sep 2025\nEDUCATION\nB.Sc. Computer Science | Sample State University"
    profile, _ = validate_evidence(_profile(experiences=[{
        "job_title": "AI Developer", "source_quote": "AI Developer"}]), raw)
    assert profile.experiences[0].organization == "Demo Labs"
    assert profile.experiences[0].start_date == "Mar 2025"
    assert profile.education[0].institution == "Sample State University"


def test_mock_llm_missing_employer_becomes_deterministic_without_second_request(monkeypatch):
    monkeypatch.setenv('AI_API_KEY', 'fake-key')
    monkeypatch.setenv('AI_MODEL', 'fake-model')
    count = []
    def handler(request):
        count.append(request.url.path)
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(_profile().model_dump())}}]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result, model, _ = extract_profile(SAMPLE, client=client)
    assert len(count) == 1
    assert model == 'fake-model'
    assert result.experiences[0].organization == 'Example University'


def test_phase39_assets_include_review_sort_and_collapsed_flags():
    with TestClient(app) as client:
        html = client.get('/app').text
        js = client.get('/static/careerpilot.js').text
        css = client.get('/static/careerpilot.css').text
        health = client.get('/health').json()
    assert health['version'] == '1.0.0'
    assert 'id="sort-order"' in html
    assert 'id="candidate-experience-panel"' in html
    assert 'reviewPriority(group, matching)' in js
    assert 'sharedReviewFlags' in js
    assert 'if (first) details.open' not in js
    assert '.group-review' in css
    assert 'localStorage' not in js and 'sessionStorage' not in js
    assert "form.set('consent_to_external_processing', 'true')" in js


def test_api_still_requires_user_consent():
    with TestClient(app) as client:
        resp = client.post('/api/v1/jobs/recommend/multi/grouped',
                           data={'roles': 'AI Engineer', 'consent_to_external_processing': 'false'},
                           files={'file': ('cv.pdf', b'%PDF-fake', 'application/pdf')})
    assert resp.status_code in (400, 403, 422)


def test_accomplishment_line_is_not_assumed_to_be_an_employer():
    raw = "PROFESSIONAL EXPERIENCE\nAI Researcher\nBuilt experimental ML pipelines\nApr 2026 – Present"
    profile, _ = validate_evidence(_profile(experiences=[{
        "job_title": "AI Researcher", "source_quote": "AI Researcher"}]), raw)
    assert profile.experiences[0].organization is None
    assert profile.experiences[0].start_date == "Apr 2026"

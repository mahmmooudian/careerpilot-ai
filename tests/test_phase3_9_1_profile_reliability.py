"""Offline provider-response regressions for phase 3.9.1. No real CVs or API calls."""
import json
import httpx
import pytest

from app.services.candidate_extractor import AIExtractionError, extract_profile

CV = 'Test Engineer\nTechnical skills: Python\nEXPERIENCE\nAI Developer\nExample Labs | Remote\nFeb 2025 – Nov 2025\n'
GOOD = {"full_name": None, "headline": "Test Engineer", "location": None,
        "skills": [{"name": "Python", "source_quote": "Python"}],
        "experiences": [{"job_title": "AI Developer", "organization": None, "start_date": None,
                         "end_date": None, "source_quote": "AI Developer"}],
        "projects": [], "education": [], "certifications": [], "recommended_roles": []}


def response_for(data, reason="stop"):
    return httpx.Response(200, json={"choices": [{"finish_reason": reason,
                                                  "message": {"content": data}}]})


def setup(monkeypatch):
    monkeypatch.setenv('AI_API_KEY', 'mock-secret')
    monkeypatch.setenv('AI_BASE_URL', 'https://api.groq.com/openai/v1')
    monkeypatch.setenv('AI_MODEL', 'openai/gpt-oss-120b')


def test_truncated_json_recovers_once(monkeypatch):
    setup(monkeypatch)
    calls = []
    def handler(req):
        calls.append(json.loads(req.content))
        assert req.url.host == 'api.groq.com'
        assert req.headers['authorization'] == 'Bearer mock-secret'
        if len(calls) == 1:
            return response_for('{"skills": [', 'length')
        return response_for(json.dumps(GOOD))
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        result, model, warnings = extract_profile(CV, client=http)
    assert result.skills[0].name == 'Python'
    assert result.experiences[0].organization == 'Example Labs'
    assert result.experiences[0].start_date == 'Feb 2025'
    assert len(calls) == 2
    assert calls[0]['max_completion_tokens'] == 9000
    assert calls[1]['max_completion_tokens'] == 12000
    assert calls[1]['response_format'] == {'type': 'json_object'}
    assert 'bounded retry' in warnings[0]
    assert model == 'openai/gpt-oss-120b'


def test_invalid_schema_one_retry_recovers(monkeypatch):
    setup(monkeypatch)
    calls = []
    def handler(req):
        calls.append(1)
        return response_for('{"unexpected":"private"}') if len(calls) == 1 else response_for(json.dumps(GOOD))
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        profile, _, warnings = extract_profile(CV, client=http)
    assert profile.skills[0].name == 'Python'
    assert len(calls) == 2
    assert warnings and 'bounded retry' in warnings[0]


def test_syntactically_valid_but_truncated_finish_reason_retried(monkeypatch):
    setup(monkeypatch)
    count = 0
    def handler(req):
        nonlocal count
        count += 1
        return response_for(json.dumps(GOOD), 'length' if count == 1 else 'stop')
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        _, _, warnings = extract_profile(CV, client=http)
    assert count == 2
    assert warnings[0].startswith('AI provider initially')


def test_double_bad_output_fails_closed_without_leaking_private_data(monkeypatch):
    setup(monkeypatch)
    calls = []
    def handler(req):
        calls.append(1)
        return response_for('SECRET_CV_PAYLOAD { this is not JSON')
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(AIExtractionError) as exc:
            extract_profile(CV, client=http)
    assert len(calls) == 2
    assert exc.value.status_code == 502
    assert 'SECRET_CV_PAYLOAD' not in exc.value.detail
    assert 'No profile was accepted' in exc.value.detail


def test_provider_429_not_retried_and_not_leaked(monkeypatch):
    setup(monkeypatch)
    calls = []
    def handler(req):
        calls.append(1)
        return httpx.Response(429, text='PRIVATE CV AND TOKEN')
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(AIExtractionError) as exc:
            extract_profile(CV, client=http)
    assert len(calls) == 1
    assert exc.value.status_code == 502
    assert 'PRIVATE' not in exc.value.detail


def test_provider_refusal_not_retried(monkeypatch):
    setup(monkeypatch)
    calls = []
    def handler(req):
        calls.append(1)
        return response_for('not permitted', 'content_filter')
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(AIExtractionError) as exc:
            extract_profile(CV, client=http)
    assert len(calls) == 1
    assert exc.value.status_code == 502


def test_valid_profile_does_not_retry(monkeypatch):
    setup(monkeypatch)
    calls = []
    def handler(req):
        calls.append(1)
        return response_for(json.dumps(GOOD))
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        profile, _, warnings = extract_profile(CV, client=http)
    assert profile.skills[0].name == 'Python'
    assert len(calls) == 1
    assert not any('bounded retry' in warning for warning in warnings)


def test_empty_output_retries_once(monkeypatch):
    setup(monkeypatch)
    calls = []
    def handler(req):
        calls.append(1)
        return response_for('') if len(calls) == 1 else response_for(json.dumps(GOOD))
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        profile, _, warnings = extract_profile(CV, client=http)
    assert len(calls) == 2
    assert profile.skills[0].name == 'Python'
    assert warnings[0].startswith('AI provider initially')

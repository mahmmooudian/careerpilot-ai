"""Offline tests: no provider network calls or private CVs."""

import json

import httpx
import pytest

from app.schemas.candidate import CandidateProfile, EvidenceItem
from app.services.candidate_extractor import (
    AIExtractionError, extract_profile, validate_evidence,
)

RAW = """Jane Doe
AI Engineer
Technical skills: Python, PyTorch
Experience: ML Engineer at Sample Corp, 2024-2025
Projects: OCR Pipeline using Python
Education: BSc Computer Science from Example University
Certification: Data Science Foundation from Sample Academy
"""


def _valid_data():
    return {
        "full_name": "Jane Doe", "headline": "AI Engineer", "location": None,
        "skills": [
            {"name": "Python", "source_quote": "Python, PyTorch"},
            {"name": "Imaginary Cloud", "source_quote": "not present in resume"},
        ],
        "experiences": [{"job_title": "ML Engineer", "organization": "Sample Corp",
                         "start_date": "2024", "end_date": "2025",
                         "source_quote": "ML Engineer at Sample Corp, 2024-2025"}],
        "projects": [{"name": "OCR Pipeline", "technologies": ["Python"],
                      "source_quote": "OCR Pipeline using Python"}],
        "education": [{"degree": "BSc Computer Science", "institution": "Example University",
                       "source_quote": "BSc Computer Science from Example University"}],
        "certifications": [{"name": "Data Science Foundation", "issuer": "Sample Academy",
                            "source_quote": "Data Science Foundation from Sample Academy"}],
        "recommended_roles": [{"title": "Machine Learning Engineer", "rationale": "Has ML Engineer experience"}],
    }


def test_evidence_filter_and_name_verification():
    profile = CandidateProfile.model_validate(_valid_data())
    verified, warnings = validate_evidence(profile, RAW)
    assert verified.full_name == "Jane Doe"
    assert len(verified.skills) == 1
    assert verified.skills[0].name == "Python"
    assert warnings and "skills" in warnings[0]


def test_fake_name_is_removed():
    profile = CandidateProfile.model_validate({**_valid_data(), "full_name": "Another Person"})
    verified, warnings = validate_evidence(profile, RAW)
    assert verified.full_name is None
    assert any("name" in message.lower() for message in warnings)


def test_llm_mock_success(monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "test-secret")
    monkeypatch.setenv("AI_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setenv("AI_MODEL", "test-model")

    def handler(request):
        assert request.headers["authorization"] == "Bearer test-secret"
        assert request.url.path.endswith("/chat/completions")
        data = json.loads(request.content)
        assert data["response_format"] == {"type": "json_object"}
        assert "Jane Doe" in data["messages"][1]["content"]
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(_valid_data())}}]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        profile, model, warnings = extract_profile(RAW, client=http)
    assert profile.full_name == "Jane Doe"
    assert len(profile.skills) == 1
    assert len(profile.experiences) == 1
    assert model == "test-model"
    assert warnings


def test_no_key_is_503(monkeypatch):
    monkeypatch.delenv("AI_API_KEY", raising=False)
    with pytest.raises(AIExtractionError) as exc:
        extract_profile(RAW)
    assert exc.value.status_code == 503


def test_blank_text_is_422(monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "fake")
    with pytest.raises(AIExtractionError) as exc:
        extract_profile(" ")
    assert exc.value.status_code == 422


def test_bad_response_is_502(monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "fake")
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(
        200, json={"choices": [{"message": {"content": '{"nonsense":42}'}}]}
    ))) as http:
        with pytest.raises(AIExtractionError) as exc:
            extract_profile(RAW, client=http)
    assert exc.value.status_code == 502


def test_provider_rejection_does_not_leak_response_body(monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "fake")
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(
        401, text="SECRET_PRIVATE_PAYLOAD"
    ))) as http:
        with pytest.raises(AIExtractionError) as exc:
            extract_profile(RAW, client=http)
    assert exc.value.status_code == 502
    assert "SECRET_PRIVATE_PAYLOAD" not in exc.value.detail


def test_too_long_text_is_413(monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "fake")
    with pytest.raises(AIExtractionError) as exc:
        extract_profile("a" * 40001)
    assert exc.value.status_code == 413

REALISTIC_PROJECTS_TEXT = """\
Jane Doe
TECHNICAL SKILLS
Python, PyTorch, BM25
SELECTED PROJECTS
Adaptive Document Intelligence RAG\u200b
RAG | Hybrid Retrieval | Cross-Encoder Reranking | LLM Applications
● Built retrieval and reranking over documents.
Technologies: Python, PyTorch, BM25 |Github
Controlled Order Agent\u200b
Agentic AI | Tool Calling | Human-in-the-Loop
● Designed an approval-gated tool agent.
Technologies: Python, Pydantic |Github
Med-AGCNet\u200b
Deep Learning | Medical Imaging | Computer Vision
● Developed a custom CNN for medical imaging.
Technologies: PyTorch, CNN, Grad-CAM |Github
Water Network AI Analyzer\u200b
Industrial AI | ML | Optimization
● Predicted water network pressure.
Technologies: XGBoost, WNTR |Github
AI Model Performance Dashboard\u200b
Model Monitoring | Power BI | Analytics
● Developed a monitoring dashboard.
Technologies: Power BI, DAX |Github
ADDITIONAL PROJECTS
Real-Time Human Activity Recognition — MediaPipe Pose + LSTM pipeline.
Intelligent Persian Speech Analytics — Offline ASR using Whisper and Vosk.
Medical Image Compression using SVD — Scientific image-compression application.
Industrial ML Optimization — Model validation for operational data.
RESEARCH
Med-AGCNet: Medical Image Classification
"""


def test_project_headings_recover_missing_selected_projects():
    """A real PDF can yield invalid multi-line project quotes or miss projects."""
    from app.schemas.candidate import Project

    profile = CandidateProfile.model_validate({
        "projects": [
            {"name": "Adaptive Document Intelligence RAG", "technologies": ["BM25"],
             "source_quote": "not an exact contiguous quote"},
            {"name": "Real-Time Human Activity Recognition", "technologies": [],
             "source_quote": "Real-Time Human Activity Recognition"},
        ]
    })
    verified, warnings = validate_evidence(profile, REALISTIC_PROJECTS_TEXT)
    titles = {p.name for p in verified.projects}
    assert len(titles) == 9
    assert {"Adaptive Document Intelligence RAG", "Controlled Order Agent",
            "Med-AGCNet", "Water Network AI Analyzer", "AI Model Performance Dashboard"} <= titles
    assert verified.projects[0].technologies == ["BM25"]
    assert any("Repaired" in x for x in warnings)
    assert any("Recovered" in x for x in warnings)
    # Backfilled entries must not receive invented technology stacks.
    assert next(p for p in verified.projects if p.name == "Med-AGCNet").technologies == []


def test_project_without_supported_name_is_rejected_even_if_quote_exists():
    profile = CandidateProfile.model_validate({
        "projects": [{"name": "Fictional Project", "technologies": [],
                      "source_quote": "Python, PyTorch, BM25"}]
    })
    verified, warnings = validate_evidence(profile, REALISTIC_PROJECTS_TEXT)
    assert "Fictional Project" not in {p.name for p in verified.projects}
    assert any("unsupported projects" in x for x in warnings)


def test_non_project_text_not_automatically_backfilled():
    profile = CandidateProfile.model_validate({"projects": []})
    resume = "Jane Doe\nEXPERIENCE\nDesigned CNN training code\nEDUCATION\nBSc"
    verified, warnings = validate_evidence(profile, resume)
    assert verified.projects == []
    assert not any("Recovered" in x for x in warnings)

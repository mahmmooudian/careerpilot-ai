from fastapi.testclient import TestClient

from app.main import app
from app.schemas.candidate import CandidateProfile
from tests.test_resume_parser import make_pdf

client = TestClient(app)


def test_consent_required():
    res = client.post("/api/v1/resumes/analyze", files={"file": ("cv.pdf", make_pdf("Example CV"), "application/pdf")})
    assert res.status_code == 400
    assert "consent" in res.json()["detail"].lower()


def test_upload_and_profile_flow(monkeypatch):
    def mocked_extractor(raw_text):
        assert "Developer" in raw_text
        return CandidateProfile(full_name="Test User", recommended_roles=[]), "mock-model", ["test warning"]

    monkeypatch.setattr("app.api.routes.extract_profile", mocked_extractor)
    res = client.post(
        "/api/v1/resumes/analyze",
        files={"file": ("cv.pdf", make_pdf("Developer CV"), "application/pdf")},
        data={"consent_to_external_processing": "true"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["model"] == "mock-model"
    assert res.json()["profile"]["full_name"] == "Test User"
    assert res.json()["file_name"] == "cv.pdf"
    assert "test warning" in res.json()["warnings"]


def test_bad_input_still_rejected():
    res = client.post(
        "/api/v1/resumes/analyze",
        files={"file": ("fake.pdf", b"not pdf", "application/pdf")},
        data={"consent_to_external_processing": "true"},
    )
    assert res.status_code == 422

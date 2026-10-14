from fastapi.testclient import TestClient

from app.main import app
from tests.test_resume_parser import make_docx, make_pdf

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_resume_upload_pdf():
    response = client.post(
        "/api/v1/resumes/parse",
        files={"file": ("cv.pdf", make_pdf("Resume for AI Engineer"), "application/pdf")},
    )
    assert response.status_code == 200
    assert response.json()["file_type"] == "pdf"
    assert "AI Engineer" in response.json()["raw_text"]


def test_resume_upload_docx():
    response = client.post(
        "/api/v1/resumes/parse",
        files={"file": ("cv.docx", make_docx(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    assert response.status_code == 200
    assert "Python" in response.json()["raw_text"]


def test_invalid_file_http_status():
    response = client.post(
        "/api/v1/resumes/parse",
        files={"file": ("fake.pdf", b"junk", "application/pdf")},
    )
    assert response.status_code == 422


def test_missing_file_is_rejected():
    response = client.post("/api/v1/resumes/parse")
    assert response.status_code == 422


def test_oversized_upload_is_rejected():
    response = client.post(
        "/api/v1/resumes/parse",
        files={"file": ("too_big.pdf", b"x" * (8 * 1024 * 1024 + 1), "application/pdf")},
    )
    assert response.status_code == 413

from app.services.resume_parser import parse_resume
from tests.test_resume_parser import make_pdf


def test_editorial_resume_note_warned():
    result = parse_resume("resume.pdf", make_pdf(
        "AI Engineer work experience. Your current resume already documents the AI Researcher role."
    ))
    assert any("commentary" in warning.lower() for warning in result.warnings)

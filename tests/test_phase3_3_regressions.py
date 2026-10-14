"""Focused regression tests; synthetic resumes and jobs only, no external requests."""
from app.schemas.candidate import CandidateProfile, EvidenceItem, Project, RecommendedRole
from app.services.candidate_extractor import validate_evidence
from app.services.job_matching import match_job
from tests.test_candidate_extractor import REALISTIC_PROJECTS_TEXT
from tests.test_job_matching import job


def test_long_additional_project_heading_canonicalized_without_duplicate():
    data = [
        Project(name="Real-Time Human Activity Recognition — MediaPipe Pose + LSTM pipeline.",
                source_quote="Real-Time Human Activity Recognition — MediaPipe Pose + LSTM pipeline."),
        Project(name="Real-Time Human Activity Recognition",
                source_quote="Real-Time Human Activity Recognition", technologies=["MediaPipe"]),
        Project(name="Intelligent Persian Speech Analytics — Offline ASR using Whisper and Vosk.",
                source_quote="Intelligent Persian Speech Analytics — Offline ASR using Whisper and Vosk."),
        Project(name="Intelligent Persian Speech Analytics",
                source_quote="Intelligent Persian Speech Analytics"),
        Project(name="Medical Image Compression using SVD — Scientific image-compression application.",
                source_quote="Medical Image Compression using SVD — Scientific image-compression application."),
        Project(name="Medical Image Compression using SVD",
                source_quote="Medical Image Compression using SVD"),
        Project(name="Industrial ML Optimization — Model validation for operational data.",
                source_quote="Industrial ML Optimization — Model validation for operational data."),
        Project(name="Industrial ML Optimization", source_quote="Industrial ML Optimization"),
    ]
    verified, warnings = validate_evidence(CandidateProfile(projects=data), REALISTIC_PROJECTS_TEXT)
    titles = [p.name for p in verified.projects]
    assert len(titles) == len(set(titles)) == 9
    assert "Real-Time Human Activity Recognition" in titles
    assert "Real-Time Human Activity Recognition — MediaPipe Pose + LSTM pipeline." not in titles
    assert next(p for p in verified.projects if p.name == "Real-Time Human Activity Recognition").technologies == ["MediaPipe"]
    assert any("Collapsed 4 duplicate" in warning for warning in warnings)
    assert any("Recovered 5" in warning for warning in warnings)


def test_three_different_project_titles_do_not_merge_on_shared_prefix():
    resume = "SELECTED PROJECTS\nProject A\nTechnology | Tools\n● Built it.\nProject A Advanced\nTechnology | Tools\n● Built it.\nRESEARCH\n"
    p = CandidateProfile(projects=[Project(name="Project A", source_quote="Project A"),
                                   Project(name="Project A Advanced", source_quote="Project A Advanced")])
    got, _ = validate_evidence(p, resume)
    assert len(got.projects) == 2


def test_llm_and_agentic_in_verifiable_skill_quote_and_headline_match():
    p = CandidateProfile(headline="AI Engineer | Agentic AI",
        skills=[EvidenceItem(name="RAG", source_quote="LLM & RAG: Retrieval-Augmented Generation, Hybrid Search")],
        projects=[Project(name="Controlled Order Agent", source_quote="Controlled Order Agent")])
    m = match_job(job("Senior AI Engineer", "LLMs and agentic AI required; RAG also required."), p, "machine learning")
    assert m is not None
    assert {"LLMs", "Agentic AI", "RAG"} <= set(m.matched_skills)
    assert "LLMs" not in m.missing_skills_to_verify
    assert "Agentic AI" not in m.missing_skills_to_verify


def test_model_recommendations_are_not_skill_evidence():
    p = CandidateProfile(recommended_roles=[RecommendedRole(title="Agentic AI Engineer", rationale="Suggested")])
    m = match_job(job("AI Engineer", "Agentic AI required"), p, "machine learning")
    assert m is not None
    assert "Agentic AI" not in m.matched_skills
    assert "Agentic AI" in m.missing_skills_to_verify


def test_project_tech_is_not_skill_without_grounded_evidence():
    p = CandidateProfile(projects=[Project(name="My Demo", technologies=["Pinecone"], source_quote="My Demo")])
    m = match_job(job("AI Engineer", "Pinecone required"), p, "machine learning")
    assert m is not None
    assert "Pinecone" not in m.matched_skills
    assert "Pinecone" in m.missing_skills_to_verify


def test_project_bonus_no_longer_always_added():
    without_projects = CandidateProfile(skills=[EvidenceItem(name="Python", source_quote="Python")])
    with_irrelevant_project = CandidateProfile(skills=without_projects.skills,
                 projects=[Project(name="Water Network AI Analyzer", source_quote="Water Network AI Analyzer")])
    j = job("AI Engineer", "Python required")
    a = match_job(j, without_projects, "machine learning")
    b = match_job(j, with_irrelevant_project, "machine learning")
    assert a and b
    assert b.match_score == a.match_score


def test_explicit_early_career_exclusion_is_flagged_separately_from_skills():
    p = CandidateProfile(skills=[EvidenceItem(name="Python", source_quote="Python")])
    j = job("Senior Independent AI Engineer / Architect", "Python. Not a Fit: Early-career engineers.")
    m = match_job(j, p, "machine learning")
    assert m is not None
    assert m.eligibility == "needs_review"
    assert any("explicitly excludes early-career" in flag for flag in m.review_flags)
    assert m.match_score < 50


def test_aliases_do_not_match_partial_words():
    p = CandidateProfile(skills=[EvidenceItem(name="SQL", source_quote="SQL")])
    m = match_job(job("AI Engineer", "NoSQL platform"), p, "machine learning")
    assert m is not None
    assert "SQL" not in m.matched_skills


def test_pinecone_or_weaviate_counts_as_one_alternative_requirement():
    p = CandidateProfile(skills=[EvidenceItem(name="Python", source_quote="Python")])
    j = job("AI Engineer", "Python required. Experience with Vector Databases, Pinecone or Weaviate is required.")
    m = match_job(j, p, "machine learning")
    assert m is not None
    assert "Vector databases (Pinecone or Weaviate)" in m.missing_skills_to_verify
    assert "Pinecone" not in m.missing_skills_to_verify
    assert "Weaviate" not in m.missing_skills_to_verify


def test_pinecone_satisfies_or_weaviate_without_double_penalty():
    p = CandidateProfile(skills=[EvidenceItem(name="Pinecone", source_quote="Pinecone")])
    j = job("AI Engineer", "Pinecone or Weaviate required, vector databases experience required.")
    m = match_job(j, p, "machine learning")
    assert m is not None
    assert "Pinecone" in m.matched_skills
    assert "Weaviate" not in m.missing_skills_to_verify
    assert "Vector databases" not in m.missing_skills_to_verify

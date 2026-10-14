"""Regression tests for the seven real-world result types without external calls."""
from app.schemas.candidate import CandidateProfile, EvidenceItem, Project
from app.schemas.jobs import JobListing
from app.services.job_matching import core_description, match_job, rank_jobs, title_relevance


def profile():
    return CandidateProfile(skills=[EvidenceItem(name="Python", source_quote="Python"),
                                    EvidenceItem(name="RAG", source_quote="RAG"),
                                    EvidenceItem(name="PyTorch", source_quote="PyTorch")],
                            projects=[Project(name="Med-AGCNet", technologies=["PyTorch"], source_quote="Med-AGCNet"),
                                      Project(name="Adaptive Document Intelligence RAG", technologies=[], source_quote="Adaptive Document Intelligence RAG")])


def job(title, description="", location="Worldwide", id=None):
    return JobListing(id=id or title, source="remotive", title=title, company="Example",
                      url="https://example.com/job", remote=True, location=location,
                      description=description, published_at="2026-10-08T00:00:00")


def test_machine_learning_query_rejects_generic_tech_and_sales_titles():
    j = [job("Senior .NET Full-stack Developer", "AI and machine learning engineering opportunities"),
         job("Senior React Full-stack Developer", "we hire machine learning engineers"),
         job("Inside Sales Contractor", "analytics and machine learning software"),
         job("Senior AI Engineer", "Python RAG LangChain Pinecone"),
         job("Senior Data Scientist", "Python and machine learning")]
    result = rank_jobs(j, profile(), "machine learning")
    assert {m.job.title for m in result} == {"Senior AI Engineer", "Senior Data Scientist"}


def test_source_boilerplate_not_skill_evidence():
    j = job("Senior AI Engineer", "Python RAG. NOT YOUR TECH STACK? Databricks Kubernetes React AWS")
    result = match_job(j, profile(), "machine learning")
    assert result is not None
    assert set(result.matched_skills) >= {"Python", "RAG"}
    assert "Databricks" not in result.missing_skills_to_verify
    assert "Kubernetes" not in result.missing_skills_to_verify


def test_requirements_not_fabricated_from_profile():
    j = job("Senior AI Engineer", "3+ years of commercial experience. 2+ years LangChain required. RAG required")
    m = match_job(j, profile(), "machine learning")
    assert m
    assert "LangChain" in m.missing_skills_to_verify
    assert any("commercial experience" in x.lower() or "years of experience" in x.lower() for x in m.review_flags)
    assert m.eligibility == "needs_review"


def test_work_country_must_not_imply_authorization():
    j = job("Senior AI Engineer", "Python", "Americas, Europe, Israel")
    m = match_job(j, profile(), "machine learning", "Iran")
    assert m
    assert any("Iran" in x for x in m.review_flags)
    assert m.eligibility == "needs_review"


def test_score_is_bounded_and_not_probability():
    m = match_job(job("Machine Learning Engineer", "Python PyTorch RAG"), profile(), "machine learning")
    assert 0 <= m.match_score <= 100
    assert m.title_relevant
    assert "evidenced skill" in m.explanation


def test_generic_query_requires_title_relevance():
    assert title_relevance("Senior Back-end Engineer", "kubernetes")[0] is False
    assert title_relevance("Kubernetes Engineer", "kubernetes")[0] is True


def test_publication_malformed_doesnt_crash():
    j = job("AI Engineer", "Python").model_copy(update={"published_at":"garbage"})
    assert match_job(j, profile(), "machine learning") is not None


def test_only_20_results_returned_when_limit_20():
    jobs = [job("AI Engineer", "Python", id=str(i)) for i in range(30)]
    assert len(rank_jobs(jobs, profile(), "machine learning", limit=20)) == 20


def test_remotive_boilerplate_normalizer_keeps_core():
    assert core_description("LangChain is required. NOT YOUR STACK? AWS React") == "LangChain is required. "


def test_no_raw_resume_or_pii_in_explanation():
    p = profile()
    p.full_name = "TEST PRIVATE NAME"
    m = match_job(job("AI Engineer", "RAG Python"), p, "AI engineer")
    assert "TEST PRIVATE NAME" not in m.explanation

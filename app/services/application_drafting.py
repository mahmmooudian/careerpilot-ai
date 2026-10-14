"""Local, deterministic application drafts constrained to resume-profile evidence.

Never infer work authorization, years, achievements, education dates, contact details,
production credentials, or missing skills. No network, model, or persistence calls.
"""
from __future__ import annotations
import re
from app.schemas.application import ApplicationDraftRequest, ApplicationDraftResponse, SkillCheck

# Word/phrase boundaries prevent accidental matches such as 'rag' in 'storage'.
# The posting patterns are technology mentions, NOT mandatory requirement extraction.
TECHNOLOGIES = (
    ('Python', (r'\bpython\b',), (r'\bpython\b',)),
    ('RAG', (r'\brag\b',r'\bretrieval.augmented generation\b',), (r'\brag\b',r'\bretrieval.augmented generation\b',)),
    ('LLMs', (r'\bllms?\b',r'\blarge language models?\b',), (r'\bllms?\b',r'\blarge language models?\b',)),
    ('Agentic AI', (r'\bagentic\b',r'\bai agents?\b',r'\btool.calling\b',), (r'\bagentic\b',r'\bai agents?\b',r'\btool.calling\b',)),
    ('AWS', (r'\baws\b',r'\bamazon web services\b',r'\bbedrock\b',), (r'\baws\b',r'\bamazon web services\b',r'\bbedrock\b',)),
    ('GCP', (r'\bgcp\b',r'\bgoogle cloud\b',), (r'\bgcp\b',r'\bgoogle cloud\b',)),
    ('Azure', (r'\bazure\b',), (r'\bazure\b',)),
    ('PyTorch', (r'\bpytorch\b',), (r'\bpytorch\b',)),
    ('TensorFlow', (r'\btensorflow\b',), (r'\btensorflow\b',)),
    ('Scikit-learn', (r'\bscikit.learn\b',r'\bsklearn\b',), (r'\bscikit.learn\b',r'\bsklearn\b',)),
    ('Docker', (r'\bdocker\b',), (r'\bdocker\b',)),
    ('Kubernetes', (r'\bkubernetes\b',r'\bk8s\b',), (r'\bkubernetes\b',r'\bk8s\b',)),
    ('SQL', (r'\bsql\b',), (r'\bsql\b',)),
    ('MLOps', (r'\bmlops\b',r'\bml ops\b',), (r'\bmlops\b',r'\bml ops\b',)),
    ('CI/CD', (r'\bci\s*/\s*cd\b',r'\bcontinuous integration\b',), (r'\bci\s*/\s*cd\b',r'\bcontinuous integration\b',)),
    ('LangChain', (r'\blangchain\b',), (r'\blangchain\b',)),
    ('Vector databases', (r'\bvector databases?\b',r'\bpinecone\b',r'\bweaviate\b',), (r'\bvector databases?\b',r'\bpinecone\b',r'\bweaviate\b',)),
    ('FastAPI', (r'\bfastapi\b',), (r'\bfastapi\b',)),
    ('Pandas', (r'\bpandas\b',), (r'\bpandas\b',)),
    ('NumPy', (r'\bnumpy\b',), (r'\bnumpy\b',)),
    ('Power BI', (r'\bpower\s*bi\b',), (r'\bpower\s*bi\b',)),
    ('Computer Vision', (r'\bcomputer vision\b',r'\bopencv\b',), (r'\bcomputer vision\b',r'\bopencv\b',)),
    ('NLP', (r'\bnlp\b',r'\bnatural language processing\b',), (r'\bnlp\b',r'\bnatural language processing\b',)),
    ('Evaluation', (r'\bevaluation\b',r'\bevals?\b',), (r'\bmodel evaluation\b',r'\bevaluation\b',r'\bevals?\b',)),
)


def found(patterns, text):
    return any(re.search(p, text, flags=re.I) for p in patterns)


def normalized(value: str) -> str:
    return re.sub(r'\s+', ' ', value or '').strip()


def safe_inline(value: str | None) -> str:
    """Prevent injected line breaks in job title/name from altering draft structure."""
    return normalized(value or '')


def skill_checks(profile, description):
    # Only `skills[].name` supplies direct skill evidence. Project technology lists
    # are listed separately as project-specific facts, never implied professional mastery.
    skill_sources = [(s.name, s.source_quote) for s in profile.skills]
    matches = []
    not_evidenced = []
    for label, posting_patterns, evidence_patterns in TECHNOLOGIES:
        if not found(posting_patterns, description):
            continue
        supporting = next(((name, quote) for name, quote in skill_sources if found(evidence_patterns, name)), None)
        if supporting:
            matches.append(SkillCheck(skill=label, evidence=f'Resume skill: {supporting[0]}'))
        else:
            not_evidenced.append(label)
    return matches, not_evidenced


def project_relevance(profile, skills):
    matched = {m.skill for m in skills}
    scored = []
    for p in profile.projects:
        # Project title/technologies are facts supplied by resume extraction,
        # not proof of production depth or outcomes.
        combo = f'{p.name} ' + ' '.join(p.technologies)
        count = sum(found(evidence_patterns, combo) for lab, _, evidence_patterns in TECHNOLOGIES if lab in matched)
        scored.append((count, p))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [p for score, p in scored if score > 0][:3] or [p for _, p in scored[:2]]


def compose(request: ApplicationDraftRequest) -> ApplicationDraftResponse:
    profile, posting = request.candidate_profile, request.posting
    title, company = safe_inline(posting.title), safe_inline(posting.company)
    name = safe_inline(profile.full_name) or '[Your name]'
    matched, not_evidenced = skill_checks(profile, posting.description)
    projects = project_relevance(profile, matched)
    existing_skills = [safe_inline(s.name) for s in profile.skills]
    priority = [m.skill for m in matched]
    # Include exactly the explicitly present skills; do not fill an empty profile
    # with invented generic competencies or place skills in years-of-experience text.
    focused = priority + [s for s in existing_skills if s.casefold() not in {x.casefold() for x in priority}]
    focused = list(dict.fromkeys(focused))[:24]
    rows = [name]
    if profile.headline: rows.append(safe_inline(profile.headline))
    if profile.location: rows.append(f'Location: {safe_inline(profile.location)}')
    rows += ['', f'TARGET ROLE: {title} — {company}', '', 'SKILLS (from supplied resume profile)']
    rows.append(', '.join(focused) if focused else 'No validated skills supplied; review source resume.')
    if profile.experiences:
        rows += ['', 'EXPERIENCE (as recorded in resume profile)']
        for x in profile.experiences[:8]:
            line = safe_inline(x.job_title)
            if x.organization: line += f' | {safe_inline(x.organization)}'
            if x.start_date or x.end_date:
                line += f' | {safe_inline(x.start_date) or "Date not supplied"} – {safe_inline(x.end_date) or "Date not supplied"}'
            rows.append(line)
    if projects:
        rows += ['', 'SELECTED PROJECTS (resume-backed, no inferred achievements)']
        for p in projects:
            line = safe_inline(p.name)
            if p.technologies:
                line += ' — ' + ', '.join(safe_inline(x) for x in p.technologies[:10])
            rows.append(line)
    if profile.education:
        rows += ['', 'EDUCATION']
        for e in profile.education[:4]:
            line = safe_inline(e.degree)
            if e.institution: line += ' | ' + safe_inline(e.institution)
            rows.append(line)
    if profile.certifications:
        rows += ['', 'CERTIFICATIONS']
        rows.extend(safe_inline(c.name) for c in profile.certifications[:8])

    intro = f'I am writing to express my interest in the {title} position at {company}.'
    if matched:
        current = ', '.join(m.skill for m in matched[:5])
        claim = f'My resume lists experience with tools and methods relevant to the posting, including {current}.'
    elif profile.skills:
        claim = f'My background includes {", ".join(existing_skills[:4])}, and I would welcome the opportunity to discuss how those skills relate to this role.'
    else:
        claim = 'I would welcome an opportunity to discuss how my projects and background relate to this position.'
    proj_sent = ''
    if projects:
        names = ', '.join(safe_inline(p.name) for p in projects[:2])
        proj_sent = f'My portfolio includes {names}. I would be glad to explain my contributions and the engineering decisions behind these projects.'
    letter = '\n\n'.join([
        f'Dear {company} Hiring Team,',
        intro,
        claim,
        proj_sent or 'I would be happy to discuss the relevant work documented in my resume.',
        'I would appreciate the opportunity to discuss the position and your expectations. Thank you for considering my application.',
        f'Sincerely,\n{name}',
    ])
    year_mentions = sorted({int(m.group(1)) for m in re.finditer(
        r"\b(\d{1,2})\s*\+?\s*(?:years?|yrs?)\b", posting.description, flags=re.I
    ) if 0 < int(m.group(1)) <= 45})
    notes = [
        'Drafted locally from the supplied candidate profile and pasted job description; no new model or job-board call was made.',
        'Verify every claim against the original resume and the current job posting; the supplied profile is not independently authenticated.',
        'Technologies to verify are mentions in the posting, not necessarily mandatory requirements or confirmed skill gaps.',
        'Hiring-country eligibility, seniority, years of experience, and employer requirements were not verified.',
        'These drafts are for human editing and approval; no application was submitted or stored.',
    ]
    if year_mentions:
        notes.append('Posting mentions years of experience: ' + ', '.join(map(str, year_mentions)) + '; confirm whether these are mandatory requirements.')
    return ApplicationDraftResponse(job_title=title, company=company,
        matched_skills=matched, technologies_to_verify=not_evidenced,
        experience_year_mentions=year_mentions,
        resume_text='\n'.join(rows), cover_letter_text=letter,
        review_notes=notes)

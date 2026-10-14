# Design decisions and engineering trade-offs

This note explains why several aspects of the v1.0 project are intentionally conservative rather than missing by accident.

### 1. Deterministic ranking, not hiring probability

A title/skill-based, explainable ranker makes it possible to inspect relevance and flag missing information. It does not justify statistical claims about hiring decisions, visa eligibility or job suitability.

### 2. Explicit consent for external AI

Resume text is sensitive. Local parsing is the default; external profile extraction is available only after a user opt-in. AI output is evidence-backed but still requires human checking.

### 3. Job sources remain read-only

Providers receive search queries rather than CV content. The project does not use unauthorized LinkedIn scraping, employer automation or submission tools.

### 4. Local deterministic drafting

Creating cover-letter and resume text from a supplied profile without another LLM call minimizes external data flow and makes output more reproducible. It also means personalization has limits and manual editing is essential.

### 5. SQLite, not hosted multi-user infrastructure

A local database fits one user's saved jobs, private notes and manual search baselines. It avoids unnecessary cloud storage but does not offer encryption, account-based isolation or hosted backups.

### 6. Docker Compose is constrained to localhost

The container binds the host network loopback; container-internal network availability does not create authentication. Public deployment is deliberately unsupported pending a new security design.

### 7. Feature freeze at v1.0.0-local

UX refinements (including saved-job-to-draft field population), scheduled monitoring, additional authorized sources and hosted access are potential future increments. They are not part of the validated v1.0 contract.

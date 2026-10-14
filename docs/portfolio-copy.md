# CareerPilot AI — Portfolio and resume copy

## Portfolio project title

**CareerPilot AI | Explainable Job Intelligence & Human-in-the-Loop Application Assistant**

## Short description (for portfolio project cards)

Built a local-first AI-assisted career workspace that combines resume intelligence, public multi-source job discovery, explainable relevance matching, geographic grouping, saved application tracking and evidence-based application drafts. Developed with FastAPI, Python, SQLite and a privacy-conscious consent model.

## Extended portfolio case study

**Problem.** Job seekers often manage resumes, several public job boards, regional variants, qualification checks and application notes across disconnected tools. Pure keyword search gives limited evidence of why a listing is relevant, and simplistic scores can mislead applicants about hiring or work eligibility.

**Solution.** CareerPilot AI offers an integrated local dashboard. It parses PDF/DOCX resumes, optionally calls an external LLM with explicit user consent for evidence-oriented candidate profiling, queries public job feeds using role terms rather than private resume text, groups geographical variants, and provides explainable heuristic match scores. Users can filter by source and freshness, manually track saved searches and applications, and prepare editable application materials without automatic submission.

**Engineering.** The system uses a layered FastAPI backend with Pydantic contracts, modular services for parsing/discovery/matching/drafting, a browser-native UI, SQLite-backed tracking, and an operations CLI for integrity checks, consistent backups, in-memory restore checks and release readiness. Security boundaries intentionally restrict v1.0 to localhost; the architecture does not pretend to provide multi-user authentication.

**Validation.** The final tested local version passed 178 automated tests, the release readiness check and a Windows SQLite restore drill. Real provider availability and Docker behavior are environment dependent. The project is distributed as a single-user local release, not a public SaaS.

**Technologies.** Python · FastAPI · Pydantic · SQLite · HTTPX · PyMuPDF · python-docx · Vanilla JavaScript · pytest · Docker Compose

**Technical decisions.** Conservative matching instead of probability claims; source-only job API calls; explicit consent for AI resume processing; local deterministic application drafting; no auto-apply, scraping or background monitoring.

## Resume bullets (use 2–3; each is grounded in the current code)

- Engineered a local-first AI career assistant in **Python/FastAPI** integrating consent-gated resume intelligence, read-only public job discovery and explainable, candidate-aware ranking across regional job variants.
- Implemented deterministic relevance and application-drafting services with transparent skill verification, eligibility warnings and user-controlled job tracking in **SQLite**.
- Delivered a browser-based application workflow with **178 passing automated tests**, database integrity checks, recoverable backups and a documented localhost-only deployment architecture.

## LinkedIn / GitHub announcement draft

**CareerPilot AI v1.0.0-local is ready for a source release.**

I built CareerPilot AI as an engineering project to explore how resume understanding, job-feed integration, explainable ranking, geographic listing normalization and human-reviewed application writing fit together in one local-first system.

The FastAPI backend uses a consent-gated external AI provider for candidate profiles, while job discovery receives only search terms. Matching and drafting remain inspectable, and saved jobs/searches are tracked in a local SQLite database.

The final local verification passed 178 automated tests and an isolated-memory SQLite restore drill. This is deliberately a single-user localhost application—not a public employment service or an automatic job application tool.

Tech: Python, FastAPI, Pydantic, SQLite, HTTPX, JavaScript, pytest and optional Docker Compose.

[GitHub URL after publication]

#FastAPI #Python #AIEngineering #MachineLearning #SoftwareEngineering

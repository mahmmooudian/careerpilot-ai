# GitHub Release draft

**Tag:** `v1.0.0-local`  
**Title:** `CareerPilot AI v1.0.0 — Local-First Job Intelligence & Application Assistant`  
**Pre-release:** No, provided the local smoke test and final source review are complete.  
**Do not attach:** `.env`, database backups, private resumes, raw candidate profiles or private logs.

## What's in v1.0

CareerPilot AI brings together local PDF/DOCX parsing, opt-in LLM-assisted candidate profiles, explainable job matching, multi-source public job discovery, geographic grouping, advanced search filters, SQLite-backed opportunity management and editable application drafts.

Highlights:

- Evidence-aware candidate profile extraction with explicit consent for sending resume text to the configured AI provider.
- Remotive discovery and optional publicly accessible Greenhouse, Lever and Ashby feeds.
- Transparent skill/title relevance and review flags; no false claim of hiring probability or global work eligibility.
- Multiple geographic variants grouped without hiding their underlying listings.
- Advanced discovery filters, publication-date handling and manually checked saved searches.
- Local opportunity board with stages, notes, follow-up dates and activity history.
- Deterministic, editable resume and cover-letter text drafts (no automatic applications).
- Local health checks, SQLite snapshots, in-memory restore drills, security headers and Docker Compose configuration for loopback-only use.

## Verification

- 178 automated tests passed in the final local verification.
- Local release check passed with `public_deployment_ready: false`.
- Isolated-memory restore drill succeeded with a private Windows backup.
- Screenshots show development UI behavior; they are not performance benchmarks.
- Docker execution still requires validation on the target machine.

## Installation

Follow the README and `docs/setup-windows.md`. Python 3.10+ is required. For native execution, bind Uvicorn to `127.0.0.1`.

## Security and privacy

**This release is intended for one trusted user on localhost. It is not a hosted service.** No internet-facing authentication or authorization layer is provided. Do not expose port 8000 beyond the local machine.

Resume text is sent to an external LLM only on explicit user consent; public job boards receive search terms. No LinkedIn scraping, unattended monitoring or automatic application submission is implemented.

## Known limitations

- Employer feed availability and location restrictions vary.
- Heuristic match scores do not predict job offers.
- Application drafts require proofreading and human approval.
- Saved opportunities can require manually re-entered job descriptions when preparing drafts.
- A GitHub source release should not include private SQLite state.

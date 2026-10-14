<div align="center">

# CareerPilot AI

### Explainable job intelligence, from resume to application draft

**Local-first · Consent-gated AI · Human-in-the-loop**

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
![Version](https://img.shields.io/badge/release-v1.0.0--local-25675A)
![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi&logoColor=white)
![Tests](https://img.shields.io/badge/tests-178%20passed-357A59)
![Deployment](https://img.shields.io/badge/deployment-localhost%20only-D69F48)

A Python/FastAPI workspace that turns a candidate's resume into **evidence-backed, explainable job recommendations**, adds multi-source public vacancy discovery and local opportunity tracking, and helps prepare editable application materials—**without automatically applying to jobs**.

**[Architecture](docs/architecture.md) · [Windows setup](docs/setup-windows.md) · [Privacy & security](SECURITY.md) · [Release checklist](docs/release-checklist.md)**

</div>

---

## Product preview

> These screenshots are cropped from a local development run. Job counts are illustrative snapshots, **not** guaranteed live results or model-performance benchmarks. Please review images before publishing.

| Job discovery and candidate matching | Advanced job intelligence |
|---|---|
| ![CareerPilot job discovery overview](docs/screenshots/discovery-overview.png) | ![CareerPilot advanced job intelligence results](docs/screenshots/advanced-intelligence.png) |

![CareerPilot application preparation form](docs/screenshots/application-studio.png)

## Why CareerPilot AI?

Job discovery is not just a search problem. Applicants need to interpret varied job feeds, detect duplicates across countries, understand why a position appears relevant, verify eligibility requirements, and keep track of follow-ups.

CareerPilot AI combines these workflows while **separating what the system can verify from what the applicant must decide**. In particular, a technical match score is **not** a hiring probability, and a remote label does **not** establish work authorization.

## Features

| Capability | Implemented in v1.0 |
|---|---|
| Resume ingestion | PDF/DOCX text extraction using local Python libraries |
| AI-assisted candidate profile | Evidence-oriented extraction using a configured OpenAI-compatible provider, **only after explicit consent** |
| Job discovery | Read-only public feeds from Remotive, plus optional configured Greenhouse, Lever and Ashby employer boards |
| Matching and explanations | Deterministic title/skill relevance, missing-technologies-to-review lists and geographic review flags |
| Multi-region grouping | Deduplicates related postings while retaining distinct geographic variants |
| Advanced intelligence | Filters by seniority, source, text, remote flags, listed experience years and publication-age metadata |
| Saved job searches | SQLite-backed saved queries and **manual** comparisons of newly seen listing URLs |
| Opportunity management | Local saved jobs, stage updates, private notes, follow-ups and activity history |
| Application studio | Editable resume and cover-letter **drafts** prepared locally from supplied profile evidence and a job description |
| Maintenance tools | SQLite health checks, consistent backups, isolated-memory restore drills and local-release checks |
| Dashboard | Bundled HTML/CSS/JavaScript with same-origin FastAPI endpoints; no CDN or frontend build required |

### Design principles

- **Consent before external resume analysis.** Public job sources receive query parameters, not the candidate's resume. If AI profile extraction is requested and approved, resume text is sent to the configured AI provider.
- **Explainable rather than predictive.** Scores rank relevance for review and do not forecast offers, interviews or visa eligibility.
- **Evidence before claims.** Drafts distinguish directly evidenced skills from technologies needing verification; generated text requires human fact-checking.
- **Keep users in control.** No LinkedIn scraping, background alerts, automatic job submissions or email sending.
- **Private local state.** Saved opportunities, notes and searches live in a local SQLite database; raw resumes are not stored as a persistent application database feature.

## Architecture

![CareerPilot AI high-level architecture](docs/assets/architecture.svg)

**Request boundary:** a localhost-only FastAPI app mediates browser interaction. PDF/DOCX parsing and application drafting happen locally; candidate extraction can call a configured external AI service **with consent**. Public job feeds receive search terms. The local SQLite database stores user-curated tracking state, not entire resume files. See [architecture and trust boundaries](docs/architecture.md).

### Technology

`Python 3.10+` · `FastAPI` · `Pydantic v2` · `HTTPX` · `PyMuPDF` · `python-docx` · `SQLite` · `Vanilla JavaScript` · `HTML/CSS` · `pytest` · `Docker Compose (local-only)`

## Quick start — Windows / PowerShell

**Prerequisites:** Python 3.10+ and a modern browser; a configured AI provider is optional for browsing public jobs but needed for consent-gated resume analysis. For detailed steps, see [Windows setup](docs/setup-windows.md).

```powershell
# In the repository root:
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item .env.example .env
# Edit your PRIVATE .env locally to configure a provider; never commit it.
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000/app** for the dashboard or **http://127.0.0.1:8000/docs** for the interactive API reference. If you only need public job browsing, you can leave `AI_API_KEY` unset. **However, `release-check` evaluates full local-release configuration and may report `local_ready: false` until a real AI provider key is configured; this does not by itself prevent public-feed browsing.**

> Existing phased installations may have `.venv` **one directory above** the repository. In that case, use `..\.venv\Scripts\python.exe` instead of `.\.venv\Scripts\python.exe`. See the complete guide before moving files.

### Environment configuration

Create `.env` from `.env.example` and configure it **locally**:

| Variable | Meaning |
|---|---|
| `AI_API_KEY` | Secret API token for the configured external LLM provider; required only for AI profile extraction |
| `AI_BASE_URL` | OpenAI-compatible HTTPS endpoint (default example: Groq) |
| `AI_MODEL` | Provider-specific model identifier |
| `JOB_REMOTIVE_ENABLED` | Toggle Remotive public discovery |
| `JOB_GREENHOUSE_BOARDS` | Comma-separated public Greenhouse board slugs |
| `JOB_LEVER_SITES` | Comma-separated public Lever site slugs |
| `JOB_ASHBY_BOARDS` | Comma-separated public Ashby board slugs |

**No employer ATS account passwords or candidate application credentials are required.** Provider slugs are public hiring-board identifiers, not secrets.

## Main workflows

**Discover & match:** browse public postings by role, or—with consent—upload a resume to extract an AI-supported candidate profile, review evidence, and rank relevant jobs. Geographic and experience requirements are flagged for manual inspection.

**Advanced intelligence:** choose filtering criteria and compare grouped variants of job postings. Date-unknown postings are not labeled newly published. Create a saved search and manually choose *Check now* to compare posting URLs with a previous baseline; this does **not** schedule monitoring.

**Saved opportunities:** store a job's title, company, link and optional review score, then record your application stage, private notes, follow-up date and interview status. These records are user-entered; changing a stage does **not** contact the employer.

**Application studio:** supply the candidate profile and full original job description. The local deterministic drafting engine outputs an editable, evidence-oriented resume text and cover letter, plus technologies to verify. **No automatic application is sent.** A saved job may require reloading a profile and manually pasting the original description.

## API overview

| Method | Route | Purpose |
|---|---|---|
| `POST` | `/api/v1/resumes/parse` | Local document text extraction |
| `POST` | `/api/v1/resumes/analyze` | Consent-gated candidate extraction |
| `GET` | `/api/v1/jobs/search` | Public job discovery |
| `POST` | `/api/v1/jobs/recommend` | Candidate-aware job ranking |
| `GET` | `/api/v1/jobs/search/multi/grouped` | Grouped multi-role discovery |
| `POST` | `/api/v1/jobs/recommend/multi/grouped` | Grouped recommendations |
| `GET` | `/api/v1/jobs/intelligence/search` | Advanced filters and freshness classification |
| `GET / POST / PATCH / DELETE` | `/api/v1/opportunities` | Local saved opportunity tracking (item actions use `/{identifier}`) |
| `GET / POST / DELETE` | `/api/v1/job-watches` | Saved job search configurations |
| `POST` | `/api/v1/job-watches/{identifier}/check` | Manually update a search baseline |
| `POST` | `/api/v1/application/draft` | Local application drafts |
| `GET` | `/health` | Lightweight local liveness endpoint |

See **`/docs`** for actual Pydantic request schemas, optional fields and responses. Do not infer that route availability means public access is supported.

## Quality and verification

In the tested v1.0 local build, **178 pytest checks passed**, including API behavior, matching and grouping regressions, local origin restrictions, database persistence, release checks, and restore-drill scenarios. The Windows restore drill successfully verified a real private SQLite backup in isolated memory. External job feeds, AI provider availability and Docker startup vary by machine and network; they are not guaranteed by these unit tests.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m app.ops check
.\.venv\Scripts\python.exe -m app.ops release-check
```

For a private database backup (the destination directory must exist):

```powershell
.\.venv\Scripts\python.exe -m app.ops backup --destination "$env:USERPROFILE\Documents\CareerPilotBackups"
# Then run a restore-drill using the actual backup path.
```

**Warning:** snapshots can contain job notes and search preferences. Keep them private; never attach backups to GitHub releases.

### Docker — optional, local only

```bash
docker compose up --build -d
docker compose ps
```

The Compose configuration publishes `127.0.0.1:8000` on the **host only**, while the container listens on its internal bridge address. Docker uses an isolated named volume **separate** from the Windows database. The Docker build has not been validated on every target machine; verify it yourself before relying on it. Avoid `docker compose down -v` unless you intend to delete Docker's volume data.

## Security, privacy and limitations

> [!WARNING]
> **Local single-user application—not a public SaaS.** No multi-user login, public deployment authorization, hosted TLS termination, or complete internet-facing threat protection is provided. **Do not** publish port 8000 on the internet, attach public tunnels, or expose the service to a LAN without additional design and security work.

- No employment outcome guarantee, validated work authorization, verified application eligibility, or automated action on employer systems.
- LLM-generated profile evidence can be incomplete or wrong. Review original resumes and all application drafts before use.
- Job providers may change APIs, reduce availability, rate-limit, remove ads, or report incomplete publication dates.
- Candidate resumes are **not** uploaded to job providers; the configured LLM receives content only with explicit user permission.
- No direct LinkedIn integration, scraping, scheduled notifications, or auto-apply.
- Local SQLite storage and snapshots are **not** encrypted by this app; secure your computer and backups.
- Dependency versions are bounded but not hash-locked; maintainers should scan and update packages.

Details: [Security policy](SECURITY.md) · [Release checklist](docs/release-checklist.md) · [Design decisions](docs/design-decisions.md).

## Repository structure

```text
app/
  api/                # HTTP routing
  core/               # Configuration, local security and maintenance
  ops/                # Health, backup, restore and release CLI
  schemas/            # Pydantic contracts
  services/           # Resume, matching, discovery, drafts and stores
  web/                # Same-origin dashboard
 tests/               # Automated tests (178 passing in verified local build)
 docs/                # Architecture, setup, release and screenshots
 Dockerfile
 compose.yaml
 pyproject.toml
 .env.example
```

## Release scope and next steps

This repository represents the **v1.0.0 local feature freeze**. Potential follow-up versions may refine saved-job → draft context transfer, recruitment-source integrations, browser UX, deployment architecture and opt-in scheduled notifications. These are **not implemented or promised in v1.0**.

## License

A public license has **not yet been selected**. The repository owner must decide and add a suitable `LICENSE` file before granting reuse rights. Until then, public visibility by itself does not grant an open-source license.

---

<div align="center">
  <strong>CareerPilot AI</strong> — Review evidence. Understand relevance. Make your own decisions.
</div>

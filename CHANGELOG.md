# Changelog

## v1.0.0-local — Feature freeze

- Integrated PDF/DOCX parsing and explicit-consent AI-assisted candidate profiling.
- Added public job discovery (Remotive plus optional Greenhouse/Lever/Ashby boards), title relevance and explainable skill matching.
- Added grouped geographic listings and advanced search filtering, with unknown-date handling and manual saved-search checks.
- Added SQLite-based opportunity management, activity history and follow-ups.
- Added local evidence-backed application drafts for human editing; no automatic submissions.
- Added localhost security middleware, database health/backup, release checks and isolated-memory SQLite restore drills.
- Added Docker/Compose configuration for optional localhost-only use and full engineering documentation.
- Verified in current local development and user Windows runs: **178 passing tests**, healthy database and successful private-backup restore drill.
- Clarified limitations: no public hosting security, multi-user auth, LinkedIn scraping, scheduled notifications or automatic applications.

The project has been developed through phases 1–8. v1.0.0-local is the first consolidated source release; older phase-specific ZIP upgrade packages are intentionally excluded from the public repository.

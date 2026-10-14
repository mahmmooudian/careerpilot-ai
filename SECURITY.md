# Security and privacy policy — CareerPilot AI v1.0.0-local

CareerPilot AI is a **single-user, localhost-only project**. A successful local release check means that the configured local instance passed certain consistency checks; it **does not** mean the project is secure for public deployment.

## Supported release scope

- Run Uvicorn with `--host 127.0.0.1 --port 8000` for native operation.
- Docker Compose only binds the **host** port to `127.0.0.1`. Internal Docker bridge access is not authentication.
- No multi-tenant authorization, public authentication, password login, hosted TLS or service-level rate-limiting is provided.
- Do not use public tunnels, internet-facing proxies, LAN exposure or cloud ingress without a separate security architecture.

## Resume and job data flows

- PDF/DOCX parsing takes place locally.
- Candidate profile extraction can send resume-derived text to the user-configured external LLM provider **only after explicit opt-in**.
- Public job sources receive search terms, not the candidate's original resume.
- Local application drafting uses the supplied extracted profile and original job description; it does not make an additional LLM request.
- The app does not submit applications or scrape LinkedIn.
- External job descriptions and model responses are untrusted; inspect them before reusing claims.

## Local persistent state

SQLite stores saved opportunity metadata, status history, notes, follow-up details, saved search preferences, and known URLs for manual comparisons. Backups may contain private data. Raw resume documents and generated application drafts are not intentionally persisted in the application SQLite database. Other temporary browser/system artifacts may still exist outside that database.

Keep SQLite files and their backups on trusted private storage. The app does not provide at-rest encryption. Deleting a browser session or clearing its page does not erase saved SQLite records.

## Before a GitHub push or Release upload

1. **Never** commit `.env`, API tokens, resume files, raw candidate-profile JSON, SQLite databases, backups, or private logs.
2. Verify that `.gitignore` excludes `.env` and SQLite files, and check the actual index with `git ls-files`.
3. Examine screenshot text for names, browser profiles, email addresses, identifiable CV details and private notes.
4. Run the unit tests and local release check; inspect external service claims for accuracy.
5. Use the curated GitHub-source package rather than uploading the entire multi-phase development directory.
6. If a secret was ever committed, ignoring it now is insufficient: rotate it and scrub or rebuild Git history appropriately.

## Vulnerability reports

Contact the repository maintainer privately. Do not include live API keys, private CVs, full backup files or personal notes in public issues.

## Remaining risks

Internet-facing use requires a new security review covering authentication and authorization, reverse-proxy and CSRF assumptions, rate limits, streaming payload limits, dependency auditing, logging, secret management, hosted TLS, migrations and recovery procedures.

## Backup verification

```text
python -m app.ops check
python -m app.ops backup --destination PRIVATE_EXISTING_FOLDER
python -m app.ops restore-drill --backup PRIVATE_BACKUP.sqlite3
```

The current restore drill restores into **isolated in-memory SQLite** and checks integrity/expected tables and record counts. It discards the in-memory database after the test; it does not overwrite the live database. Successful simulation is not a substitute for a complete documented disaster-recovery procedure.

# GitHub publication checklist — v1.0.0-local

**Feature scope is frozen.** This publication documents the existing application; it does not extend features or assert that the app is secure on the public internet.

## Local verification

- [ ] Run `python -m pytest -q` (178 passed in the verified current build).
- [ ] Confirm `python -m app.ops check` reports database healthy and loopback mode.
- [ ] With a valid local AI key configured, confirm `python -m app.ops release-check` returns `local_ready: true` and `public_deployment_ready: false`; without a key the first flag can be false while public-feed browsing still works.
- [ ] Confirm a real private backup passes `restore-drill` (done in verified Windows run).
- [ ] Verify the four navigation sections and manual interactions in a browser; do not equate form visibility with a working generated draft.
- [ ] If claiming Docker works on the machine, perform a real `docker compose up --build -d` and test state persistence. Otherwise label Docker unverified.

## Privacy and public source

- [ ] Start from the **curated public source package**, not the historical phased development folder.
- [ ] Confirm `.env` does not exist in the publication folder or Git index.
- [ ] Inspect tracked files via `git ls-files`; there should be no private backups, original resumes, candidate JSON exports, raw logs, database files or historical absolute user paths.
- [ ] Review every screenshot for private names, addresses, browser profiles, notes and resume details.
- [ ] Check GitHub commit history too; `.gitignore` does not remove a previously committed secret.
- [ ] If keys were previously committed, revoke/rotate those keys immediately and rebuild the repository history if necessary.
- [ ] Select and add a `LICENSE` deliberately; public visibility alone is not open-source permission.

## Release communication

- [ ] Name repository `careerpilot-ai`; use `v1.0.0-local` for the first release tag.
- [ ] Set repository description and topics from [publication guide](publish-to-github-fa.md).
- [ ] Use [release notes](github-release-notes.md); make **local-only** limitation prominent.
- [ ] Do not publish `*.sqlite3`, `.env`, unredacted original resume documents or generated private candidate profiles as release attachments.
- [ ] Publish a sanitized UI preview; avoid unverifiable claims like "predicts your chance of being hired".

## Known limitations

- No public SaaS, automatic job applications, direct LinkedIn API/scraping or scheduled alerts.
- Eligibility, location and employer requirements must be manually verified.
- Draft resume/cover-letter content must be inspected by the applicant.
- A saved opportunity does not guarantee job application completion.
- Loading a saved job into Application Studio can still require manually pasting job description and reusing a profile.

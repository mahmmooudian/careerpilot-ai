# Windows setup — CareerPilot AI v1.0.0-local

This guide is for the **curated public source repository**, cloned into a new folder. It is not an instruction to delete or reset an existing private development installation.

## Prerequisites

- Windows 10/11, Python 3.10+ and PowerShell.
- Internet access to install dependencies; public job retrieval also needs network access.
- An external LLM API key only if you intend to request opt-in AI profile extraction. Job search itself does not need it.
- Optional: Docker Desktop, if separately testing the local container setup.

## Fresh installation

```powershell
git clone https://github.com/YOUR_ACCOUNT/careerpilot-ai.git
cd careerpilot-ai
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Open `.env` in a local editor and replace `YOUR_API_KEY_HERE` with your provider key **only if needed**. Never upload `.env` or paste a real key into issues or logs.

Run quality and readiness checks:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m app.ops check
.\.venv\Scripts\python.exe -m app.ops release-check
```

If you left `AI_API_KEY` unset, `release-check` can report `local_ready: false` because AI-assisted candidate extraction is not configured. Read-only public job search can still work. Do not put a real key in the public repository.

Start the dashboard:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Browse `http://127.0.0.1:8000/app` or `http://127.0.0.1:8000/docs`. Stop with Ctrl+C.

## Existing phased development installation

Some older installations store `.venv` in the **parent** directory. In that scenario run `..\.venv\Scripts\python.exe` (instead of `.\.venv\Scripts\python.exe`). Do **not** move or overwrite your existing `.env` and do **not** merge a public sanitized source archive onto your personal live database.

For documentation-only refreshes use the separately provided **Docs Overlay** in your existing project and keep all private files in place.

## Optional local Docker Compose

Stop native Uvicorn first so port 8000 is free:

```powershell
docker compose up --build -d
docker compose ps
docker compose logs --tail 30
```

Open the same localhost URL. Docker persists its own SQLite database in a separate Docker volume and does not automatically import native data. `docker compose down` stops containers while leaving volume data. `docker compose down -v` deletes the Compose volume; **avoid it unless you understand the data-loss impact**.

The Docker deployment has not been validated on every machine. See [architecture](architecture.md) and [security](../SECURITY.md) for limits.

## Safeguard your data

```powershell
$dir = "$env:USERPROFILE\Documents\CareerPilotBackups"
New-Item -Type Directory -Force -Path $dir
.\.venv\Scripts\python.exe -m app.ops backup --destination $dir
$backup = Get-ChildItem "$dir\careerpilot_backup_*.sqlite3" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
.\.venv\Scripts\python.exe -m app.ops restore-drill --backup "$($backup.FullName)"
```

Keep backups outside the Git repository. Only an authorized local user should be able to read them.

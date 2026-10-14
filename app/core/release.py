"""Offline release gate and non-destructive SQLite restore drill.

No remote calls, no secret values, no changes to the live database.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from contextlib import closing
from urllib.parse import urlsplit

from app.core.maintenance import integrity_check
from app.services.opportunity_store import default_db_path

REQUIRED_TABLES = frozenset({'opportunities', 'activities', 'job_watches', 'job_watch_seen'})


def _db_summary(path: Path) -> dict:
    state = integrity_check(path)
    if state['status'] != 'ok':
        raise ValueError('SQLite backup did not pass integrity check')
    try:
        with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=8) as db:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            missing = sorted(REQUIRED_TABLES - tables)
            if missing:
                raise ValueError('Backup lacks required application tables')
            if db.execute('PRAGMA foreign_key_check').fetchone() is not None:
                raise ValueError('Backup failed foreign key check')
            return {name: db.execute(f'SELECT COUNT(*) FROM {name}').fetchone()[0]
                    for name in sorted(REQUIRED_TABLES)}
    except sqlite3.Error as exc:
        raise ValueError('Backup could not be verified') from exc


def restore_drill(backup_file: Path) -> dict:
    """Test a private backup in isolated SQLite memory, never the live DB.

    An in-memory restore avoids Windows temporary-directory and SQLite file
    handle cleanup problems. Both database connections are explicitly closed.
    """
    backup_file = Path(backup_file).expanduser()
    if not backup_file.is_file():
        raise ValueError('Backup file does not exist')
    if backup_file.resolve() == default_db_path().resolve():
        raise ValueError('Use a backup file, not the active database')

    before = _db_summary(backup_file)
    try:
        source_uri = backup_file.resolve().as_uri() + '?mode=ro'
        with closing(sqlite3.connect(source_uri, uri=True, timeout=8)) as source:
            with closing(sqlite3.connect(':memory:', timeout=8)) as restored:
                source.backup(restored)
                # Inspect the actual restored database; never simply recheck the
                # original backup or infer a successful restore from no errors.
                check = restored.execute('PRAGMA quick_check').fetchone()
                if check is None or check[0] != 'ok':
                    raise ValueError('Restored database failed integrity check')
                tables = {
                    row[0] for row in restored.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                if not REQUIRED_TABLES.issubset(tables):
                    raise ValueError('Restored database lacks required application tables')
                if restored.execute('PRAGMA foreign_key_check').fetchone() is not None:
                    raise ValueError('Restored database failed foreign key check')
                after = {
                    name: restored.execute(f'SELECT COUNT(*) FROM {name}').fetchone()[0]
                    for name in sorted(REQUIRED_TABLES)
                }
    except sqlite3.Error as exc:
        raise ValueError('Could not restore and verify backup') from exc

    if before != after:
        raise ValueError('Restored record counts differ from the backup')
    return {
        'status': 'ok',
        'restored_to': 'isolated_memory_discarded',
        'live_database_unchanged': True,
        'record_counts': after,
    }


def local_release_check(project_root: Path | None = None, database: Path | None = None) -> dict:
    root = project_root or Path(__file__).resolve().parents[2]
    files = ['Dockerfile', 'compose.yaml', '.dockerignore', '.env.example',
             'README.md', 'SECURITY.md', 'CHANGELOG.md',
             'docs/architecture.md', 'docs/release-checklist.md']
    missing = [name for name in files if not (root / name).is_file()]
    db_path = database or default_db_path()
    db = integrity_check(db_path)
    # First run of a fresh install may not have initialized its local database.
    db_ready = db['status'] == 'ok' and db.get('opportunities_table') and db.get('saved_searches_table')
    provider = os.environ.get('AI_BASE_URL', 'https://api.groq.com/openai/v1')
    parsed = urlsplit(provider)
    provider_https = parsed.scheme == 'https' and bool(parsed.hostname)
    return {
        'release':'v1.0.0-local',
        'local_ready':not missing and bool(db_ready) and provider_https,
        'public_deployment_ready':False,
        'database_status':db['status'],
        'provider_https':provider_https,
        'ai_key_present':bool(os.getenv('AI_API_KEY','').strip()),
        'missing_release_files':missing,
        'manual_checks_required':['Docker build and run on target computer',
                                  'browser end-to-end smoke test',
                                  'backup restore drill on an actual private backup',
                                  'external job providers, availability and work eligibility'],
        'warning':'Single-user localhost release. NO PUBLIC INTERNET DEPLOYMENT OR AUTHENTICATION.'
    }

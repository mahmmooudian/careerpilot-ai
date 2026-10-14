"""Local SQLite health verification and consistent private backup.

Never backs up CVs: current DB holds saved job URLs, notes and search filters.
Run only from the user's local command line; no public admin endpoints.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.services.opportunity_store import default_db_path


def integrity_check(path: Path | None = None) -> dict:
    target = Path(path) if path is not None else default_db_path()
    if not target.exists():
        return {'status':'not_initialized', 'database_exists':False}
    if not target.is_file():
        return {'status':'invalid_path', 'database_exists':True}
    try:
        # Opening read-only must not create or modify an absent DB.
        with sqlite3.connect(target.resolve().as_uri() + '?mode=ro', uri=True, timeout=5) as db:
            result = db.execute('PRAGMA quick_check').fetchone()[0]
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        return {'status':'ok' if result == 'ok' else 'integrity_failed',
                'database_exists':True,
                'opportunities_table': 'opportunities' in tables,
                'saved_searches_table': 'job_watches' in tables}
    except (sqlite3.Error, OSError, ValueError):
        return {'status':'integrity_failed', 'database_exists':True}


def backup_database(destination_dir: Path, source: Path | None = None) -> Path:
    """Online backup from a consistent SQLite snapshot, never overwrite files.

    Target directory must already exist, preventing typo-driven disclosure to
    newly created public folders. The caller controls the destination.
    """
    original = Path(source) if source is not None else default_db_path()
    destination_dir = Path(destination_dir).expanduser()
    if not destination_dir.is_dir():
        raise ValueError('Backup directory must already exist')
    if not original.is_file() or integrity_check(original)['status'] != 'ok':
        raise ValueError('Local database is missing or failed integrity check')
    if destination_dir.resolve() == original.parent.resolve():
        raise ValueError('Use a separate private backup directory')

    timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    destination = destination_dir / f'careerpilot_backup_{timestamp}.sqlite3'
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, 'O_BINARY'):
        flags |= os.O_BINARY
    fd = os.open(destination, flags, 0o600)
    os.close(fd)
    try:
        with sqlite3.connect(original.resolve().as_uri() + '?mode=ro', uri=True, timeout=10) as live:
            with sqlite3.connect(destination, timeout=10) as snapshot:
                live.backup(snapshot)
        if integrity_check(destination)['status'] != 'ok':
            raise RuntimeError('Backup did not pass integrity check')
        if os.name != 'nt':
            destination.chmod(0o600)
        return destination
    except Exception:
        destination.unlink(missing_ok=True)
        raise

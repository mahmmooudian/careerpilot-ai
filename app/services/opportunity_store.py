from __future__ import annotations
"""Local, single-user SQLite store for curated opportunities and action history.

No CV, candidate profile, job description, provider keys, or job-board session data
is persisted.  Transactions are kept short; user input is always parameterized.
"""
import os
import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.schemas.opportunities import OpportunityCreate, OpportunityUpdate


class NotFound(Exception):
    pass


def default_db_path() -> Path:
    override = os.environ.get('CAREERPILOT_DATA_DIR')
    if override:
        folder = Path(override).expanduser()
    elif sys.platform == 'win32':
        folder = Path(os.environ.get('LOCALAPPDATA') or (Path.home() / 'AppData' / 'Local')) / 'CareerPilotAI'
    else:
        folder = Path.home() / '.careerpilot_ai'
    return folder / 'opportunities.sqlite3'


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class OpportunityStore:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path is not None else default_db_path()

    @contextmanager
    def connection(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if os.name != 'nt':
            self.path.parent.chmod(0o700)
        db = sqlite3.connect(str(self.path), timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA busy_timeout=10000')
        try:
            self._schema(db)
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
            if os.name != 'nt' and self.path.exists():
                self.path.chmod(0o600)

    @staticmethod
    def _schema(db):
        db.execute('''CREATE TABLE IF NOT EXISTS opportunities (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, company TEXT NOT NULL,
            url TEXT NOT NULL UNIQUE, source TEXT NOT NULL, source_job_id TEXT,
            location TEXT, technical_score INTEGER,
            stage TEXT NOT NULL DEFAULT 'saved', notes TEXT NOT NULL DEFAULT '',
            next_action_on TEXT, interview_at TEXT,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT, opportunity_id TEXT NOT NULL,
            kind TEXT NOT NULL, description TEXT NOT NULL, created_at TEXT NOT NULL,
            FOREIGN KEY (opportunity_id) REFERENCES opportunities(id) ON DELETE CASCADE
        )''')
        db.execute('CREATE INDEX IF NOT EXISTS idx_opportunities_stage ON opportunities(stage)')
        db.execute('CREATE INDEX IF NOT EXISTS idx_opportunities_next_action ON opportunities(next_action_on)')
        db.execute('CREATE INDEX IF NOT EXISTS idx_activities_opportunity ON activities(opportunity_id, id)')

    @staticmethod
    def _serialize(row):
        return dict(row) if row is not None else None

    def create(self, data: OpportunityCreate) -> tuple[dict, bool]:
        with self.connection() as db:
            existing = db.execute('SELECT * FROM opportunities WHERE url=?', (data.url,)).fetchone()
            if existing:
                return self._serialize(existing), False
            values = data.model_dump()
            values['id'] = str(uuid4())
            values['created_at'] = values['updated_at'] = now()
            columns = ', '.join(values)
            placeholders = ', '.join('?' for _ in values)
            try:
                db.execute(f'INSERT INTO opportunities ({columns}) VALUES ({placeholders})', tuple(values.values()))
            except sqlite3.IntegrityError:
                # A second request may have saved the same URL in the meantime.
                existing = db.execute('SELECT * FROM opportunities WHERE url=?', (data.url,)).fetchone()
                if existing:
                    return self._serialize(existing), False
                raise
            self._log(db, values['id'], 'saved', 'Saved opportunity for review')
            return self._serialize(db.execute('SELECT * FROM opportunities WHERE id=?', (values['id'],)).fetchone()), True

    def list(self, stage: str | None = None, q: str | None = None):
        with self.connection() as db:
            filters, args = [], []
            if stage:
                filters.append('stage=?'); args.append(stage)
            if q:
                escaped = q.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
                filters.append("(title LIKE ? ESCAPE '\\' OR company LIKE ? ESCAPE '\\' OR location LIKE ? ESCAPE '\\')")
                args.extend([f'%{escaped}%'] * 3)
            where = (' WHERE ' + ' AND '.join(filters)) if filters else ''
            sql = 'SELECT * FROM opportunities' + where + ' ORDER BY CASE WHEN next_action_on IS NULL THEN 1 ELSE 0 END, next_action_on, updated_at DESC LIMIT 500'
            return [self._serialize(row) for row in db.execute(sql, args).fetchall()]

    def get(self, identifier: str) -> dict:
        with self.connection() as db:
            row = db.execute('SELECT * FROM opportunities WHERE id=?', (identifier,)).fetchone()
            if not row: raise NotFound()
            return self._serialize(row)

    def patch(self, identifier: str, update: OpportunityUpdate) -> dict:
        changed = update.model_fields_set
        if not changed:
            return self.get(identifier)
        with self.connection() as db:
            row = db.execute('SELECT * FROM opportunities WHERE id=?', (identifier,)).fetchone()
            if not row: raise NotFound()
            values = update.model_dump(mode='json', exclude_unset=True)
            # No arbitrary column names: Pydantic extra=forbid + explicit allowlist.
            allowed = {'stage', 'notes', 'next_action_on', 'interview_at'}
            values = {k: v for k, v in values.items() if k in allowed}
            values['updated_at'] = now()
            sql = ', '.join(f'{k}=?' for k in values)
            db.execute(f'UPDATE opportunities SET {sql} WHERE id=?', (*values.values(), identifier))
            if 'stage' in values and values['stage'] != row['stage']:
                self._log(db, identifier, 'stage_changed', f"Stage: {row['stage']} → {values['stage']} (user recorded)")
            if 'notes' in values and values['notes'] != row['notes']:
                self._log(db, identifier, 'notes_updated', 'Notes updated')
            if 'next_action_on' in values and values['next_action_on'] != row['next_action_on']:
                self._log(db, identifier, 'follow_up_updated', 'Follow-up date updated')
            if 'interview_at' in values and values['interview_at'] != row['interview_at']:
                self._log(db, identifier, 'interview_updated', 'Interview time updated')
            return self._serialize(db.execute('SELECT * FROM opportunities WHERE id=?', (identifier,)).fetchone())

    def activities(self, identifier: str) -> list[dict]:
        with self.connection() as db:
            if not db.execute('SELECT 1 FROM opportunities WHERE id=?', (identifier,)).fetchone():
                raise NotFound()
            return [self._serialize(row) for row in db.execute(
                'SELECT id, created_at, kind, description FROM activities WHERE opportunity_id=? ORDER BY id DESC LIMIT 100', (identifier,)
            ).fetchall()]

    def delete(self, identifier: str) -> None:
        with self.connection() as db:
            cur = db.execute('DELETE FROM opportunities WHERE id=?', (identifier,))
            if not cur.rowcount: raise NotFound()

    @staticmethod
    def _log(db, identifier, kind, description):
        db.execute('INSERT INTO activities (opportunity_id, kind, description, created_at) VALUES (?,?,?,?)',
                   (identifier, kind, description, now()))

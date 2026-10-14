"""Local-only saved *search definitions* and manually checked public posting URLs.

Uses the existing local SQLite path, but never touches the opportunities table.
No CV, API key, provider response text or personal profile is persisted.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from uuid import uuid4

from app.services.opportunity_store import OpportunityStore
from app.services.job_intelligence import AdvancedFilters, AdvancedSearchResponse


class WatchNotFound(Exception):
    pass


class WatchLimitReached(Exception):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class WatchStore:
    def __init__(self, path=None):
        self.db = OpportunityStore(path=path)

    @staticmethod
    def ensure(db):
        db.execute('''CREATE TABLE IF NOT EXISTS job_watches (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, filters_json TEXT NOT NULL,
          created_at TEXT NOT NULL, last_checked_at TEXT
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS job_watch_seen (
          watch_id TEXT NOT NULL, url TEXT NOT NULL,
          first_seen_at TEXT NOT NULL,
          PRIMARY KEY (watch_id, url),
          FOREIGN KEY(watch_id) REFERENCES job_watches(id) ON DELETE CASCADE
        )''')

    @staticmethod
    def item(row):
        return {'id':row['id'], 'name':row['name'],
                'filters':AdvancedFilters.model_validate_json(row['filters_json']).model_dump(),
                'created_at':row['created_at'], 'last_checked_at':row['last_checked_at']}

    def create(self, name: str, filters: AdvancedFilters):
        with self.db.connection() as db:
            self.ensure(db)
            if db.execute('SELECT COUNT(*) FROM job_watches').fetchone()[0] >= 20:
                raise WatchLimitReached()
            identifier = str(uuid4())
            created = utc_now()
            db.execute('INSERT INTO job_watches(id,name,filters_json,created_at) VALUES(?,?,?,?)',
                       (identifier, name, filters.model_dump_json(), created))
            return self.item(db.execute('SELECT * FROM job_watches WHERE id=?', (identifier,)).fetchone())

    def get(self, identifier: str):
        with self.db.connection() as db:
            self.ensure(db)
            row = db.execute('SELECT * FROM job_watches WHERE id=?', (identifier,)).fetchone()
            if row is None: raise WatchNotFound()
            return self.item(row)

    def list(self):
        with self.db.connection() as db:
            self.ensure(db)
            return [self.item(r) for r in db.execute('SELECT * FROM job_watches ORDER BY created_at DESC, id DESC').fetchall()]

    def delete(self, identifier: str):
        with self.db.connection() as db:
            self.ensure(db)
            cursor = db.execute('DELETE FROM job_watches WHERE id=?', (identifier,))
            if not cursor.rowcount: raise WatchNotFound()

    def record_scan(self, identifier: str, response: AdvancedSearchResponse):
        # URL uniqueness is per geographic variant, not group. Scan only the displayed
        # result window; counts are NOT a census of all internet vacancies.
        records = [
            {'url': str(v.job.url), 'title':v.job.title, 'company':v.job.company,
             'location':v.job.location, 'source':v.job.source}
            for g in response.grouped_jobs for v in g.variants
        ]
        with self.db.connection() as db:
            self.ensure(db)
            row = db.execute('SELECT * FROM job_watches WHERE id=?', (identifier,)).fetchone()
            if row is None: raise WatchNotFound()
            prior = row['last_checked_at'] is not None
            # The first scan establishes a baseline, not a flood of "new" alerts.
            current = utc_now()
            new = []
            for record in records:
                existing = db.execute('SELECT 1 FROM job_watch_seen WHERE watch_id=? AND url=?',
                                      (identifier, record['url'])).fetchone()
                if not existing:
                    db.execute('INSERT INTO job_watch_seen(watch_id,url,first_seen_at) VALUES(?,?,?)',
                               (identifier, record['url'], current))
                    if prior: new.append(record)
            db.execute('UPDATE job_watches SET last_checked_at=? WHERE id=?', (current, identifier))
            return {'watch_id': identifier, 'first_scan':not prior, 'last_checked_at':current,
                    'scanned_variants':len(records), 'new_count':len(new), 'new_jobs':new,
                    'warnings': response.warnings + [
                        'Only currently displayed results were compared. Manual checks are not scheduled notifications.',
                    ]}

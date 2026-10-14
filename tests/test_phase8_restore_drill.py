"""Restore drills exercise real SQLite backup content without disk restoration."""
import sqlite3

import pytest

from app.core.maintenance import backup_database, integrity_check
from app.core.release import restore_drill
from app.services.opportunity_store import OpportunityStore
from app.services.job_watch_store import WatchStore
from app.schemas.opportunities import OpportunityCreate


def make_backup(tmp_path):
    live = tmp_path / 'local' / 'opportunities.sqlite3'
    store = OpportunityStore(live)
    _, ok = store.create(OpportunityCreate.model_validate({
        'title': 'AI Engineer', 'company': 'Demo Employer',
        'url': 'https://example.org/job/1', 'source': 'public_test',
        'location': 'Remote', 'technical_score': 87,
    }))
    assert ok
    with store.connection() as db:
        WatchStore.ensure(db)
        db.execute('''INSERT INTO job_watches
            (id, name, filters_json, created_at, last_checked_at)
            VALUES (?, ?, ?, ?, NULL)''',
            ('watch_1', 'AI roles', '{}', '2026-10-14T00:00:00Z'))
        db.execute('''INSERT INTO job_watch_seen
            (watch_id, url, first_seen_at) VALUES (?, ?, ?)''',
            ('watch_1', 'https://example.org/job/1', '2026-10-14T00:00:00Z'))
    backup_dir = tmp_path / 'private_backup'
    backup_dir.mkdir()
    backup = backup_database(backup_dir, live)
    return live, backup


def test_restore_drill_recovers_all_tables_and_does_not_modify_files(tmp_path):
    live, backup = make_backup(tmp_path)
    original_live = live.read_bytes()
    original_backup = backup.read_bytes()
    result = restore_drill(backup)
    assert result['status'] == 'ok'
    assert result['live_database_unchanged'] is True
    assert result['restored_to'] == 'isolated_memory_discarded'
    assert result['record_counts'] == {
        'activities': 1,
        'job_watch_seen': 1,
        'job_watches': 1,
        'opportunities': 1,
    }
    assert live.read_bytes() == original_live
    assert backup.read_bytes() == original_backup
    assert sorted(p.name for p in backup.parent.iterdir()) == [backup.name]
    assert integrity_check(live)['status'] == 'ok'


def test_restore_drill_against_real_backup_does_not_need_tempfile(monkeypatch, tmp_path):
    _, backup = make_backup(tmp_path)
    # Simulates unavailable/invalid Windows temporary directory paths.
    import tempfile
    def broken_temp_dir(*args, **kwargs):
        raise OSError(267, 'The directory name is invalid')
    monkeypatch.setattr(tempfile, 'TemporaryDirectory', broken_temp_dir)
    assert restore_drill(backup)['status'] == 'ok'


def test_restore_drill_rejects_missing_file(tmp_path):
    with pytest.raises(ValueError, match='does not exist'):
        restore_drill(tmp_path / 'absent.sqlite3')


def test_restore_drill_rejects_incomplete_schema(tmp_path):
    incomplete = tmp_path / 'incomplete.sqlite3'
    with sqlite3.connect(incomplete) as db:
        db.execute('CREATE TABLE opportunities (id TEXT)')
    with pytest.raises(ValueError, match='required application tables'):
        restore_drill(incomplete)


def test_restore_drill_rejects_corrupted_backup(tmp_path):
    invalid = tmp_path / 'corrupt.sqlite3'
    invalid.write_bytes(b'this is not a sqlite database')
    with pytest.raises(ValueError, match='integrity check|verified'):
        restore_drill(invalid)

"""Regression tests for Phase 7: local-only boundaries and database safety."""
import os
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.maintenance import integrity_check, backup_database
from app.ops.__main__ import run
from app.services.opportunity_store import OpportunityStore
from app.schemas.opportunities import OpportunityCreate


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_version_and_security_headers(client):
    response = client.get('/health')
    assert response.json()['version'] == '1.0.0'
    assert response.headers['Cache-Control'] == 'no-store'
    assert response.headers['X-Frame-Options'] == 'DENY'
    assert response.headers['X-Content-Type-Options'] == 'nosniff'
    assert response.headers['Referrer-Policy'] == 'no-referrer'
    assert 'camera=()' in response.headers['Permissions-Policy']


def test_dashboard_csp_still_does_not_allow_external_js(client):
    response = client.get('/app')
    assert response.status_code == 200
    csp = response.headers['Content-Security-Policy']
    assert "script-src 'self'" in csp
    assert 'frame-ancestors' in csp
    assert '8.0.0' in response.text


@pytest.mark.parametrize('hostname', [
    'evil.test', '128.0.0.1.attacker.example',
    '128.0.0.1@evil.test', 'evil.test@128.0.0.1',
    '[invalid', '128.0.0.1:badport',
])
def test_untrusted_host_rejected_from_all_routes(client, hostname):
    assert client.get('/app', headers={'Host':hostname}).status_code == 403
    assert client.get('/api/v1/jobs/search', headers={'Host':hostname}).status_code == 403


def test_remote_client_rejected_everywhere():
    with TestClient(app, client=('192.168.1.23', 5001)) as c:
        assert c.get('/app').status_code == 403
        assert c.get('/api/v1/jobs/search').status_code == 403
        assert c.get('/health').status_code == 403


@pytest.mark.parametrize('header', [
    {'Origin':'https://attacker.example'},
    {'Origin':'null'},
    {'Origin':'http://testserver.attacker.example'},
    {'Origin':'http://testserver/foreign'},
    {'Sec-Fetch-Site':'cross-site'},
    {'Sec-Fetch-Site':'same-site'},
])
def test_cross_site_writes_rejected_globally(client, header):
    assert client.post('/api/v1/resumes/analyze', headers=header).status_code == 403
    assert client.post('/api/v1/application/draft', headers=header).status_code == 403


def test_allowed_same_origin_keeps_existing_validation(client):
    response = client.post('/api/v1/resumes/analyze', headers={
        'Origin':'http://testserver', 'Sec-Fetch-Site':'same-origin',
    })
    assert response.status_code != 403  # May be 422 for missing file


def test_malformed_content_length_and_preflight_size(client):
    for length, code in [('invalid',400), ('-1',400), (str(11 * 1024 * 1024),413)]:
        resp = client.post('/api/v1/resumes/parse', content=b'abc', headers={'Content-Length':length})
        assert resp.status_code == code
        assert resp.headers['Cache-Control'] == 'no-store'


def test_api_response_disallows_cache(client):
    response = client.get('/api/v1/opportunities')
    assert response.status_code == 200
    assert response.headers['Cache-Control'] == 'no-store'
    assert 'Access-Control-Allow-Origin' not in response.headers


def test_missing_db_check_is_read_only(tmp_path):
    db = tmp_path / 'absent.db'
    assert integrity_check(db) == {'status':'not_initialized', 'database_exists':False}
    assert not db.exists()


def test_db_backup_preserves_data_and_passes_integrity(tmp_path):
    dbfile = tmp_path / 'data' / 'jobs.db'
    store = OpportunityStore(dbfile)
    job, created = store.create(OpportunityCreate.model_validate({
        'title':'Junior ML Engineer', 'company':'Example',
        'url':'https://example.com/jobs/one', 'source':'lever',
        'location':'Yerevan', 'technical_score':75,
    }))
    assert created
    backup_dir = tmp_path / 'private_backups'
    backup_dir.mkdir()
    dest = backup_database(backup_dir, dbfile)
    assert dest.parent == backup_dir
    assert dest.exists()
    assert integrity_check(dest)['status']=='ok'
    with sqlite3.connect(dest) as connection:
        assert connection.execute('SELECT title FROM opportunities WHERE id=?', (job['id'],)).fetchone()[0] == 'Junior ML Engineer'
    assert not list(dbfile.parent.glob('*backup*.sqlite3'))
    if os.name != 'nt':
        assert dest.stat().st_mode & 0o777 == 0o600


def test_backup_does_not_overwrite_or_create_destination_dir(tmp_path):
    store = OpportunityStore(tmp_path / 'source.sqlite3')
    with store.connection():
        pass
    with pytest.raises(ValueError):
        backup_database(tmp_path / 'nonexistent', store.path)
    with pytest.raises(ValueError):
        backup_database(tmp_path, store.path)


def test_cli_check_never_leaks_provider_key(monkeypatch, capsys, tmp_path):
    from app.core import maintenance
    monkeypatch.setenv('AI_API_KEY', 'PRIVATE_SECRET_TEST_TOKEN')
    monkeypatch.setenv('AI_BASE_URL', 'https://api.example.invalid/v1?token=secret_query')
    monkeypatch.setattr(maintenance, 'default_db_path', lambda: tmp_path / 'absent.sqlite3')
    assert run(['check']) == 0
    out = capsys.readouterr().out
    assert 'PRIVATE_SECRET_TEST_TOKEN' not in out
    assert 'secret_query' not in out
    assert 'multi_user_auth_enabled' in out
    assert not (tmp_path / 'absent.sqlite3').exists()


def test_untrusted_content_not_reflected(client):
    response = client.post('/api/v1/application/draft', headers={'Origin':'https://attack.example/my-token?secret=abc'})
    assert response.status_code == 403
    assert 'my-token' not in response.text
    assert 'secret=abc' not in response.text

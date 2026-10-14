"""Phase 3.8 — local dashboard availability and safety contract."""
from fastapi.testclient import TestClient
from app.main import app


def test_root_redirects_to_local_dashboard():
    with TestClient(app) as client:
        response = client.get('/', follow_redirects=False)
        assert response.status_code == 307
        assert response.headers['location'] == '/app'


def test_dashboard_serves_html_without_external_scripts_or_auto_consent():
    with TestClient(app) as client:
        response = client.get('/app')
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('text/html')
    assert "script-src 'self'" in response.headers['content-security-policy']
    assert response.headers['cache-control'] == 'no-store'
    html = response.text
    assert 'id="consent"' in html
    assert 'type="checkbox" id="consent" checked' not in html
    assert 'id="resume"' in html
    assert 'id="preview-btn"' in html
    assert 'id="saved-json"' in html
    assert 'https://' not in html  # no external service dependencies in page


def test_styles_and_scripts_served_locally():
    with TestClient(app) as client:
        css = client.get('/static/careerpilot.css')
        js = client.get('/static/careerpilot.js')
    assert css.status_code == 200
    assert 'text/css' in css.headers['content-type']
    assert '.job-card' in css.text
    assert js.status_code == 200
    assert 'javascript' in js.headers['content-type']
    assert '/api/v1/jobs/recommend/multi/grouped' in js.text
    assert '/api/v1/jobs/search/multi/grouped' in js.text


def test_no_automatic_application_or_browser_storage():
    with TestClient(app) as client:
        js = client.get('/static/careerpilot.js').text
    assert 'localStorage' not in js
    assert 'sessionStorage' not in js
    assert '/apply' not in js
    assert 'innerHTML' not in js
    assert "consent_to_external_processing', 'true'" in js


def test_existing_grouped_api_still_documented():
    with TestClient(app) as client:
        r = client.get('/openapi.json')
    assert r.status_code == 200
    p = r.json()['paths']
    assert '/api/v1/jobs/recommend/multi/grouped' in p
    assert '/api/v1/jobs/search/multi/grouped' in p
    assert '/app' not in p

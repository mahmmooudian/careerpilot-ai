"""Prevents stale discovery scripts hiding the save-to-board action."""
from fastapi.testclient import TestClient
from app.main import app


def test_dashboard_uses_revisioned_scripts_and_styles():
    with TestClient(app) as client:
        html = client.get('/app').text
        assert 'src="/static/careerpilot.js?v=8.0.0"' in html
        assert 'src="/static/opportunity-board.js?v=8.0.0"' in html
        assert 'href="/static/careerpilot.css?v=8.0.0"' in html
        assert html.index('careerpilot.js?v=8.0.0') < html.index('opportunity-board.js?v=8.0.0')
        for asset in ('careerpilot.js', 'opportunity-board.js', 'careerpilot.css'):
            response = client.get(f'/static/{asset}?v=8.0.0')
            assert response.status_code == 200


def test_save_action_is_wired_to_local_opportunities_api():
    with TestClient(app) as client:
        rendering = client.get('/static/careerpilot.js?v=8.0.0').text
        board = client.get('/static/opportunity-board.js?v=8.0.0').text
        assert "el('button', 'save-to-board'" in rendering
        assert 'window.CareerPilotBoard.save(job' in rendering
        assert "body.appendChild(saveAction)" in rendering
        assert "const API = '/api/v1/opportunities'" in board
        assert "method:'POST'" in board

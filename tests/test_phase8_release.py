from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
from app.core.release import local_release_check


def test_v1_health():
    response = TestClient(app).get('/health')
    assert response.status_code == 200
    assert response.json()['version'] == '1.0.0'


def test_release_report_not_public_ready():
    report = local_release_check()
    assert report['public_deployment_ready'] is False
    assert report['release'] == 'v1.0.0-local'


def test_docker_binds_loopback():
    compose = Path('compose.yaml').read_text(encoding='utf-8')
    assert '127.0.0.1:8000:8000' in compose


def test_secrets_not_bundled():
    """Protect local secrets from Git/Docker bundles without banning local .env."""
    assert Path('.env.example').is_file()
    git_rules = Path('.gitignore').read_text(encoding='utf-8').splitlines()
    docker_rules = Path('.dockerignore').read_text(encoding='utf-8').splitlines()
    assert '.env' in [line.strip() for line in git_rules]
    assert '.env' in [line.strip() for line in docker_rules]

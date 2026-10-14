import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services.opportunity_store import OpportunityStore
from app.api import opportunity_routes

@pytest.fixture
def client(tmp_path):
    app.dependency_overrides[opportunity_routes.store] = lambda: OpportunityStore(tmp_path / 'jobs.sqlite3')
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

PAYLOAD = {'title':'Junior AI Engineer','company':'Example Co','url':'https://example.org/jobs/123','source':'Lever','location':'Yerevan','technical_score':63}

def test_crud_and_history(client):
    response=client.post('/api/v1/opportunities',json=PAYLOAD)
    assert response.status_code==201
    obj=response.json(); ident=obj['id']; assert obj['stage']=='saved'
    assert client.post('/api/v1/opportunities',json=PAYLOAD).status_code==200
    assert client.get('/api/v1/opportunities').json()['count']==1
    update=client.patch(f'/api/v1/opportunities/{ident}',json={'stage':'interview','notes':'Contacted recruiter','next_action_on':'2026-10-20'})
    assert update.status_code==200 and update.json()['stage']=='interview'
    assert len(client.get(f'/api/v1/opportunities/{ident}/activity').json())>=3
    assert client.get('/api/v1/opportunities',params={'stage':'interview'}).json()['count']==1
    assert client.delete(f'/api/v1/opportunities/{ident}').status_code==204
    assert client.get(f'/api/v1/opportunities/{ident}').status_code==404

def test_input_validation_and_local_origin(client):
    assert client.post('/api/v1/opportunities',json={**PAYLOAD,'url':'http://localhost/private'}).status_code==422
    assert client.post('/api/v1/opportunities',json={**PAYLOAD,'technical_score':150}).status_code==422
    assert client.post('/api/v1/opportunities',json=PAYLOAD,headers={'Origin':'https://evil.example'}).status_code==403
    assert client.get('/api/v1/opportunities',headers={'Host':'evil.example'}).status_code==403

def test_no_external_submission(client):
    created=client.post('/api/v1/opportunities',json=PAYLOAD).json()
    response=client.patch(f"/api/v1/opportunities/{created['id']}",json={'stage':'applied'})
    assert response.status_code==200
    assert response.json()['stage']=='applied'
    assert 'user recorded' in client.get(f"/api/v1/opportunities/{created['id']}/activity").json()[0]['description']

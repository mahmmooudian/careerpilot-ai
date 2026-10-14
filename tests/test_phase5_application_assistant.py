"""Phase 5: grounded local drafts, zero external calls or persistence."""
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.schemas.application import ApplicationDraftRequest
from app.services.application_drafting import compose

PROFILE = {
    'full_name':'Example Candidate', 'headline':'ML Engineer | RAG', 'location':'Example City',
    'skills':[
        {'name':'Python','source_quote':'Python'},
        {'name':'Retrieval-Augmented Generation','source_quote':'Retrieval-Augmented Generation'},
        {'name':'LLMs','source_quote':'LLMs'},
        {'name':'PyTorch','source_quote':'PyTorch'},
    ],
    'experiences':[{'job_title':'AI Developer','organization':None,'start_date':None,'end_date':None,'source_quote':'AI Developer'}],
    'projects':[{'name':'Document Intelligence RAG','technologies':['Python','BM25'],'source_quote':'Document Intelligence RAG'}],
    'education':[{'degree':'BSc in Computer Science','institution':None,'source_quote':'BSc in Computer Science'}],
    'certifications':[],
}
POSTING = {
    'title':'Junior AI/ML Engineer', 'company':'Example Inc', 'location':'Yerevan',
    'description':'Candidates should have Python, RAG, large language models (LLMs), AWS and LangChain. Minimum 2+ years in relevant roles.'
}

@pytest.fixture
def client():
    with TestClient(app) as c: yield c


def test_local_draft_endpoint_and_matching(client):
    resp=client.post('/api/v1/application/draft', json={'candidate_profile':PROFILE,'posting':POSTING})
    assert resp.status_code == 200, resp.text
    value=resp.json()
    assert value['generation']=='local_evidence_bound_templates'
    assert {'Python','RAG','LLMs'} <= {x['skill'] for x in value['matched_skills']}
    assert {'AWS','LangChain'} <= set(value['technologies_to_verify'])
    assert 'Document Intelligence RAG' in value['resume_text']
    assert value['experience_year_mentions'] == [2]
    assert 'Example Candidate' in value['cover_letter_text']
    assert 'Example Inc' in value['cover_letter_text']
    assert '2 years' not in value['resume_text']
    assert '2 years' not in value['cover_letter_text']
    assert 'organization' not in value['cover_letter_text'].lower()
    assert 'Date not supplied' not in value['resume_text']
    assert resp.headers.get('cache-control') == 'no-store'


def test_no_unproven_provider_skills_in_drafts(client):
    r=client.post('/api/v1/application/draft',json={'candidate_profile':PROFILE,'posting':POSTING}).json()
    for doc in (r['resume_text'],r['cover_letter_text']):
        assert 'LangChain' not in doc
        assert 'AWS' not in doc
        assert 'production' not in doc.lower()
    assert all('not necessarily mandatory' in ' '.join(r['review_notes']) for _ in [0])


def test_no_evidence_is_not_fabricated(client):
    data={'candidate_profile':{'skills':[], 'experiences':[{'job_title':'Research Assistant','source_quote':'Research Assistant'}]}, 'posting':POSTING}
    out=client.post('/api/v1/application/draft',json=data)
    assert out.status_code==200
    assert out.json()['matched_skills']==[]
    assert out.json()['resume_text'].find('Research Assistant')>=0
    assert 'LLMs' not in out.json()['cover_letter_text']


def test_case_insensitive_phrase_but_not_substring(client):
    payload={'candidate_profile':PROFILE,'posting':{**POSTING,'description':'This job mentions storage and Python with strong evaluation practices.'}}
    response=client.post('/api/v1/application/draft',json=payload)
    labels={x['skill'] for x in response.json()['matched_skills']}
    assert 'Python' in labels
    assert 'RAG' not in labels


def test_rejection_of_empty_description_untrusted_schema_and_malformed_profile(client):
    body={'candidate_profile':PROFILE,'posting':POSTING}
    assert client.post('/api/v1/application/draft',json={**body,'posting':{**POSTING,'description':'short'}}).status_code==422
    assert client.post('/api/v1/application/draft',json={**body,'unexpected':'injected'}).status_code==422
    assert client.post('/api/v1/application/draft',json={**body,'candidate_profile':{'skills':[],'projects':[],'experiences':[]}}).status_code==422


def test_draft_is_same_origin_only(client):
    body={'candidate_profile':PROFILE,'posting':POSTING}
    assert client.post('/api/v1/application/draft',json=body, headers={'Origin':'https://attacker.example'}).status_code==403
    assert client.post('/api/v1/application/draft',json=body, headers={'Host':'attacker.example'}).status_code==403


def test_no_external_model_or_database_calls(monkeypatch,client,tmp_path):
    from app.services import candidate_extractor, opportunity_store
    def do_not_call(*args,**kwargs): raise AssertionError('Unexpected model or database access')
    monkeypatch.setattr(opportunity_store.OpportunityStore, 'connection', do_not_call)
    response=client.post('/api/v1/application/draft',json={'candidate_profile':PROFILE,'posting':POSTING})
    assert response.status_code==200


def test_dashboard_application_wiring_and_asset_cache_revision(client):
    html=client.get('/app').text
    assert 'id="application-studio"' in html
    assert 'src="/static/application-studio.js?v=8.0.0"' in html
    assert html.index('careerpilot.js?v=8.0.0') < html.index('application-studio.js?v=8.0.0')
    script=client.get('/static/application-studio.js?v=8.0.0').text
    assert '/api/v1/application/draft' in script
    assert 'innerHTML' not in script
    assert 'localStorage' not in script
    assert 'window.CareerPilotStudio' in script
    main=client.get('/static/careerpilot.js').text
    assert 'CareerPilotStudio.prepare' in main
    board=client.get('/static/opportunity-board.js').text
    assert 'Prepare application' in board


def test_no_accidental_contact_information_or_employer_inference():
    obj=ApplicationDraftRequest.model_validate({'candidate_profile':PROFILE,'posting':POSTING})
    draft=compose(obj)
    assert 'Example Candidate' in draft.resume_text
    assert 'AI Developer | ' not in draft.resume_text
    assert 'example@example.com' not in draft.resume_text
    assert 'www.' not in draft.resume_text


def test_project_fallback_does_not_invent_technologies(client):
    person={'projects':[{'name':'Classification Demo','source_quote':'Classification Demo','technologies':[]}], 'skills':[]}
    r=client.post('/api/v1/application/draft',json={'candidate_profile':person,'posting':POSTING})
    assert r.status_code==200
    assert 'Classification Demo' in r.json()['resume_text']
    assert 'AWS' not in r.json()['resume_text']

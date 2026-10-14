"""Regression tests for advanced freshness, grouping, local manual watch semantics."""
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.schemas.jobs import JobListing
from app.services.multi_job_discovery import MultiResult, RoleHit
from app.services.job_intelligence import (
    AdvancedFilters, advanced_search_result, apply_advanced_filters,
    posting_age, seniority_of,
)
from app.services.job_watch_store import WatchStore, WatchNotFound, WatchLimitReached

NOW = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)


def job(ident='1', title='Junior AI/ML Engineer', source='lever', location='Yerevan',
        published='2026-10-12T11:00:00Z', description=None):
    return JobListing(id=f'{source}:example:{ident}', source=source, title=title,
                      company='Provectus', location=location, remote=True,
                      published_at=published, description=description if description is not None else
                      'Python RAG developer role. This posting mentions 2+ years of production experience.',
                      url=f'https://jobs.example.org/openings/{ident}')


def hit(**kwargs):
    return RoleHit(job=job(**kwargs), matched_roles=('AI Engineer',), retrieval_score=40)


def found(hits):
    return MultiResult(roles=['AI Engineer'], hits=hits,
        checked=['lever:example'], warnings=[], jobs_considered=15,
        source_result_counts={'lever:example': len(hits)},
        source_fetched_counts={'lever:example':15})


def test_dates_missing_malformed_and_future_not_claimed_recent():
    assert posting_age(None, NOW) is None
    assert posting_age('N/A', NOW) is None
    assert posting_age('2030-01-01', NOW) is None
    assert posting_age('2026-10-13T12:00:00Z', NOW) == 1
    assert posting_age('2026-09-01T00:00:00', NOW) == 43


def test_freshness_filter_excludes_unknown_by_default():
    options=AdvancedFilters(roles='AI Engineer', max_age_days=7)
    hits=[hit(ident='fresh'),hit(ident='unknown',published=None),hit(ident='old',published='2026-08-01')]
    output, excluded, unknown = apply_advanced_filters(hits, options, NOW)
    assert [h.job.id for h in output] == ['lever:example:fresh']
    assert excluded == {'unknown_date':1, 'older_than_max_age':1}
    assert unknown == 1
    options.include_unknown_dates = True
    selected, _, unknown = apply_advanced_filters(hits, options, NOW)
    assert len(selected) == 2 and unknown == 1


def test_seniority_filter_is_explicit_not_senior_by_default():
    assert seniority_of('AI Engineer') == 'mid'
    assert seniority_of('Senior AI Engineer') == 'senior'
    assert seniority_of('Junior AI Engineer') == 'junior'
    options=AdvancedFilters(roles='AI Engineer', seniority='junior')
    hits=[hit(ident='a'),hit(ident='b',title='Senior AI Engineer')]
    selected, dropped, _=apply_advanced_filters(hits,options,NOW)
    assert len(selected)==1 and dropped['seniority']==1


def test_years_phrases_only_no_imputed_experience_or_eligibility():
    options=AdvancedFilters(roles='AI Engineer', max_years_mentioned=3)
    hits=[hit(ident='a', description='5+ years work with python'),
          hit(ident='b', description='Python and AI; experience not specified')]
    selected,counts,_=apply_advanced_filters(hits,options,NOW)
    assert [h.job.id for h in selected] == ['lever:example:b']
    assert counts['years_mentions']==1


def test_quality_keyword_and_source_filters():
    options=AdvancedFilters(roles='AI Engineer',source='lever',min_description_chars=12,
                            required_keywords='python,RAG',excluded_keywords='blockchain')
    hits=[hit(ident='a'),hit(ident='b',source='remotive'),
          hit(ident='c',description='short'),
          hit(ident='d',description='Python and blockchain RAG'),
          hit(ident='e',description='We use Python')]
    kept,stats,_=apply_advanced_filters(hits, options, NOW)
    assert [x.job.id for x in kept]==['lever:example:a']
    assert stats == {'source':1,'description_quality':1,'excluded_keywords':1,'required_keywords':1}


def test_filters_validate_constrained_queries():
    with pytest.raises(ValidationError): AdvancedFilters(roles='AI Engineer',max_age_days=-1)
    with pytest.raises(ValidationError): AdvancedFilters(roles='AI Engineer',excluded_keywords='x')
    with pytest.raises(ValidationError): AdvancedFilters(roles='AI Engineer',source='linkedin')
    with pytest.raises(ValidationError): AdvancedFilters(roles='AI Engineer',required_keywords='\x00malicious')


def test_grouped_advanced_search_preserves_variants_and_unknown_dates():
    hits=[hit(ident='a',location='Yerevan'),hit(ident='b',location='Ukraine',published=None)]
    result=advanced_search_result(found(hits),AdvancedFilters(roles='AI Engineer', limit=10),NOW)
    assert result.count==1 and result.filtered_variants==2
    assert result.grouped_jobs[0].variant_count==2
    assert {str(v.job.url) for v in result.grouped_jobs[0].variants} == {
        'https://jobs.example.org/openings/a','https://jobs.example.org/openings/b'}
    assert sorted(v.freshness for v in result.grouped_jobs[0].variants)==['recent','unknown']
    assert all(v.geographic_status == 'needs_review' for v in result.grouped_jobs[0].variants)
    assert result.unknown_date_variants==1


def test_watch_storage_first_scan_baseline_second_scan_new_urls(tmp_path):
    store=WatchStore(path=tmp_path/'careerpilot.sqlite3')
    filters=AdvancedFilters(roles='AI Engineer')
    watch=store.create('Junior AI search',filters)
    assert len(store.list())==1
    data=advanced_search_result(found([hit(ident='a')]),filters,NOW)
    first=store.record_scan(watch['id'],data)
    assert first['first_scan'] and first['new_count']==0 and first['scanned_variants']==1
    second=store.record_scan(watch['id'],data)
    assert second['new_count']==0 and not second['first_scan']
    updated=advanced_search_result(found([hit(ident='a'),hit(ident='b',location='Ukraine')]),filters,NOW)
    third=store.record_scan(watch['id'],updated)
    assert third['new_count']==1
    assert third['new_jobs'][0]['location']=='Ukraine'
    assert store.list()[0]['last_checked_at']
    store.delete(watch['id'])
    assert not store.list()
    with pytest.raises(WatchNotFound):store.get(watch['id'])


def test_watch_storage_no_cv_or_description_and_limit(tmp_path):
    store=WatchStore(path=tmp_path/'careerpilot.sqlite3')
    filters=AdvancedFilters(roles='AI Engineer',required_keywords='Python')
    for idx in range(20):store.create(f'Watch #{idx}',filters)
    with pytest.raises(WatchLimitReached):store.create('Too many',filters)
    raw=(tmp_path/'careerpilot.sqlite3').read_bytes()
    assert b'Python' in raw and b'CandidateProfile' not in raw
    assert b'production experience' not in raw


def test_intelligence_api_and_watch_routes_do_not_contact_network(monkeypatch, tmp_path):
    from app.api import intelligence_routes, job_watch_routes
    watch_store=WatchStore(path=tmp_path/'test.sqlite3')
    app.dependency_overrides[job_watch_routes.get_store]=lambda: watch_store
    calls=[]
    def fake_multi(roles,limit=20,remote_only=False,location_query=None,*,internal_pool=False):
        calls.append((roles,limit,internal_pool))
        return found([hit(ident='a')])
    monkeypatch.setattr(intelligence_routes.multi_routes._multi,'search_multi',fake_multi)
    try:
        with TestClient(app) as client:
            response=client.get('/api/v1/jobs/intelligence/search?roles=AI%20Engineer&limit=10&seniority=junior')
            assert response.status_code==200,response.text
            assert response.json()['count']==1
            assert calls and calls[0][1]==200 and calls[0][2]
            watch=client.post('/api/v1/job-watches',json={'name':'Junior search','filters':{'roles':'AI Engineer'}})
            assert watch.status_code==201,watch.text
            identifier=watch.json()['id']
            first=client.post(f'/api/v1/job-watches/{identifier}/check')
            assert first.status_code==200,first.text
            assert first.json()['first_scan'] and first.json()['new_count']==0
            listing=client.get('/api/v1/job-watches')
            assert listing.json()['watches'][0]['id']==identifier
            assert client.delete(f'/api/v1/job-watches/{identifier}').status_code==204
            assert client.post(f'/api/v1/job-watches/{identifier}/check').status_code==404
    finally:
        app.dependency_overrides.clear()


def test_untrusted_location_or_url_never_makes_eligible():
    options=AdvancedFilters(roles='AI Engineer',work_country='Armenia')
    data=advanced_search_result(found([hit(location='Armenia')]),options,NOW)
    flag=data.grouped_jobs[0].variants[0]
    assert flag.geographic_status=='needs_review'
    assert any('not proven' in f for f in flag.geographic_review_flags)


def test_advanced_ui_is_same_origin_and_exposes_manual_checks():
    with TestClient(app) as client:
        page=client.get('/app')
        assert page.status_code==200
        assert 'advanced-intelligence.js?v=8.0.0' in page.text
        assert 'href="#advanced-intelligence"' in page.text
        script=client.get('/static/advanced-intelligence.js?v=8.0.0')
        assert script.status_code==200
        assert 'Save this search' in page.text
        assert '/api/v1/job-watches' in script.text
        assert 'Check now' in script.text
        assert not any(x in script.text for x in ('localStorage', 'sessionStorage','autoApply'))

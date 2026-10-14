"""Local-only management API. Recording 'applied' never submits an application."""
from urllib.parse import urlsplit
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from app.core.security import is_local_peer
from app.schemas.opportunities import Activity, Opportunity, OpportunityCreate, OpportunityList, OpportunityUpdate, Stage
from app.services.opportunity_store import NotFound, OpportunityStore

router = APIRouter(prefix='/api/v1/opportunities', tags=['Opportunity Management'])


def local_request_only(request: Request):
    # This personal, unauthenticated workspace is deliberately not a hosted API.
    peer = request.client.host if request.client else None
    host = (request.url.hostname or '').lower()
    if not is_local_peer(peer, host):
        raise HTTPException(403, 'Opportunity storage is restricted to the local machine')
    origin = request.headers.get('origin')
    if origin:
        try:
            parsed = urlsplit(origin)
            if parsed.scheme != request.url.scheme or parsed.hostname != host or parsed.port != request.url.port:
                raise ValueError()
        except ValueError:
            raise HTTPException(403, 'Cross-origin changes are not allowed') from None


def store():
    return OpportunityStore()


def not_found(exc):
    raise HTTPException(404, 'Saved opportunity was not found') from exc


@router.post('', response_model=Opportunity, dependencies=[Depends(local_request_only)])
def save_opportunity(data: OpportunityCreate, response: Response, db: OpportunityStore = Depends(store)):
    saved, created = db.create(data)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    response.headers['Cache-Control'] = 'no-store'
    return saved


@router.get('', response_model=OpportunityList, dependencies=[Depends(local_request_only)])
def list_opportunities(stage: Stage | None = None,
                       q: str | None = Query(None, max_length=120),
                       db: OpportunityStore = Depends(store)):
    items = db.list(stage=stage.value if stage else None, q=q)
    return {'count': len(items), 'opportunities': items}


@router.get('/{identifier}', response_model=Opportunity, dependencies=[Depends(local_request_only)])
def get_opportunity(identifier: str, db: OpportunityStore = Depends(store)):
    try: return db.get(identifier)
    except NotFound as ex: not_found(ex)


@router.patch('/{identifier}', response_model=Opportunity, dependencies=[Depends(local_request_only)])
def change_opportunity(identifier: str, data: OpportunityUpdate, db: OpportunityStore = Depends(store)):
    try: return db.patch(identifier, data)
    except NotFound as ex: not_found(ex)


@router.get('/{identifier}/activity', response_model=list[Activity], dependencies=[Depends(local_request_only)])
def read_activity(identifier: str, db: OpportunityStore = Depends(store)):
    try: return db.activities(identifier)
    except NotFound as ex: not_found(ex)


@router.delete('/{identifier}', status_code=204, dependencies=[Depends(local_request_only)])
def remove_opportunity(identifier: str, db: OpportunityStore = Depends(store)):
    try: db.delete(identifier)
    except NotFound as ex: not_found(ex)
    return Response(status_code=204)

"""Local-only evidence-backed draft generation. No external submission or storage."""
from fastapi import APIRouter, Depends, Response
from app.api.opportunity_routes import local_request_only
from app.schemas.application import ApplicationDraftRequest, ApplicationDraftResponse
from app.services.application_drafting import compose

router = APIRouter(prefix='/api/v1/application', tags=['Application Assistant'])


@router.post('/draft', response_model=ApplicationDraftResponse, dependencies=[Depends(local_request_only)])
def draft_application(data: ApplicationDraftRequest, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    return compose(data)

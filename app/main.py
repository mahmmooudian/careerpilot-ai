"""CareerPilot AI application entry point."""
from pathlib import Path
from fastapi import FastAPI, Response
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from app.core.security import LocalSecurityMiddleware
from app.api.routes import router as resumes_router
from app.api.job_routes import router as jobs_router
from app.api.recommendation_routes import router as recommendations_router
from app.api.multi_routes import router as multi_router
from app.api.grouped_routes import router as grouped_router
from app.api.grouped_recommendation_routes import router as grouped_recommendation_router
from app.api.opportunity_routes import router as opportunity_router
from app.api.application_routes import router as application_router
from app.api.intelligence_routes import router as intelligence_router
from app.api.job_watch_routes import router as watch_router
app = FastAPI(
    title="CareerPilot AI",
    description="Resume parsing, evidence-based AI profiles, and read-only job discovery and candidate-aware rankings (v1.0 local release: explainable matching, opportunity tracking, release checks and recoverable local SQLite state).",
    version="1.0.0",
)
app.add_middleware(LocalSecurityMiddleware)
app.include_router(resumes_router)
app.include_router(jobs_router)
app.include_router(recommendations_router)
app.include_router(multi_router)
app.include_router(grouped_router)
app.include_router(grouped_recommendation_router)
app.include_router(opportunity_router)
app.include_router(application_router)
app.include_router(intelligence_router)
app.include_router(watch_router)

# Bundled, same-origin static assets; no external font/CDN dependency.
WEB = Path(__file__).resolve().parent / "web"
app.mount("/static", StaticFiles(directory=WEB), name="careerpilot-static")

@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/app", status_code=307)

@app.get("/app", include_in_schema=False)
def dashboard():
    response = FileResponse(WEB / "index.html", media_type="text/html")
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "connect-src 'self'; img-src 'self' data:; base-uri 'none'; "
        "object-src 'none'; frame-ancestors 'none'; form-action 'self'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response

@app.get("/health", tags=["Operations"])
def health() -> dict[str,str]:
    return {"status":"ok", "service":"careerpilot-ai", "version":"1.0.0"}

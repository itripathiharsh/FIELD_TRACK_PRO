from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.config import settings
from app.exceptions.handlers import register_exception_handlers
from app.jobs.scheduler import shutdown_scheduler, start_scheduler
from app.logging_config import setup_logging
from app.middleware import (
    CatchUnhandledExceptionsMiddleware,
    RequestLoggingAndContextMiddleware,
    SecurityHeadersMiddleware,
)

logger = setup_logging(settings.environment)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.app_name} [{settings.environment}]")
    # FT-021: the missed-visit scheduler is started here. Its docstring claimed
    # this wiring already existed; it did not, so overdue visits were never
    # transitioned to MISSED.
    start_scheduler()
    try:
        yield
    finally:
        shutdown_scheduler()
        logger.info(f"Shutting down {settings.app_name}")


def _docs_urls_for_environment(environment: str) -> tuple[str | None, str | None, str | None]:
    """
    P1-4: the interactive API docs expose the full route/schema surface and
    must not be reachable in production. Returning None for all three means
    FastAPI never registers those routes at all - a request to /docs in
    production gets a plain 404 (route not found), not merely a hidden UI
    link. Pulled out as its own function so the decision is directly
    unit-testable without constructing a whole app.
    """
    if environment == "production":
        return None, None, None
    return "/docs", "/redoc", "/openapi.json"


_docs_url, _redoc_url, _openapi_url = _docs_urls_for_environment(settings.environment)
app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    docs_url=_docs_url,
    redoc_url=_redoc_url,
    openapi_url=_openapi_url,
    lifespan=lifespan,
)

# Middleware order matters. Starlette applies `add_middleware` in reverse, so
# the LAST one registered is the OUTERMOST. Registering the catch-all first and
# CORS second puts CORS outside it, which means an error response produced by
# the catch-all still receives Access-Control-Allow-Origin (FT-046).
# SecurityHeadersMiddleware is registered last (outermost of all) so its
# headers land on every response, including CORS-decorated error responses.
app.add_middleware(RequestLoggingAndContextMiddleware)
app.add_middleware(CatchUnhandledExceptionsMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count", "X-Request-ID"],
)
app.add_middleware(SecurityHeadersMiddleware)

register_exception_handlers(app)

app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/health", tags=["health"])
async def root_health_check():
    """Root-level health probe for load balancers / Docker HEALTHCHECK."""
    return {"status": "UP"}


@app.get("/download/app", tags=["mobile-distribution"])
@app.get("/app-latest.apk", tags=["mobile-distribution"])
async def download_latest_apk():
    """Serves the latest assembled Android APK for direct mobile installation."""
    from pathlib import Path
    from fastapi import HTTPException
    from fastapi.responses import FileResponse

    apk_paths = [
        Path(r"f:\Field track pro v2 for test\FieldTrackPro-Latest-Debug.apk"),
        Path(r"f:\Field track pro v2 for test\field track pro\fieldtrackpro-android\app\build\outputs\apk\debug\app-debug.apk"),
    ]
    for p in apk_paths:
        if p.exists():
            return FileResponse(
                path=str(p),
                filename="FieldTrackPro-Latest-Debug.apk",
                media_type="application/vnd.android.package-archive",
            )
    raise HTTPException(status_code=404, detail="APK file not found")


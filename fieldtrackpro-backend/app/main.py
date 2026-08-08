from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.config import settings
from app.exceptions.handlers import register_exception_handlers
from app.jobs.scheduler import shutdown_scheduler, start_scheduler
from app.logging_config import setup_logging
from app.middleware import CatchUnhandledExceptionsMiddleware

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


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# Middleware order matters. Starlette applies `add_middleware` in reverse, so
# the LAST one registered is the OUTERMOST. Registering the catch-all first and
# CORS second puts CORS outside it, which means an error response produced by
# the catch-all still receives Access-Control-Allow-Origin (FT-046).
app.add_middleware(CatchUnhandledExceptionsMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/health", tags=["health"])
async def root_health_check():
    """Root-level health probe for load balancers / Docker HEALTHCHECK."""
    return {"status": "UP"}

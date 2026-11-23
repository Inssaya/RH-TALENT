import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .config import get_settings
from .db import get_engine
from .routers import admin, auth, candidate, jobs, public

settings = get_settings()
logging.basicConfig(level=logging.INFO, format='{"t":"%(asctime)s","lvl":"%(levelname)s","log":"%(name)s","msg":"%(message)s"}')
log = logging.getLogger("tm.api")

if settings.sentry_dsn:
    try:
        import sentry_sdk
        sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.env, traces_sample_rate=0.05)
    except ImportError:
        log.warning("SENTRY_DSN set but sentry-sdk is not installed")

app = FastAPI(title="TalentMatch API", version="1.0.0", root_path="",
              docs_url=None if settings.is_prod else "/api/docs", openapi_url=None if settings.is_prod else "/api/openapi.json")
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def security_and_timing(request: Request, call_next):
    started = time.monotonic()
    try:
        response = await call_next(request)
    except Exception:
        log.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse({"detail": "Internal error"}, status_code=500)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Cache-Control"] = response.headers.get("Cache-Control", "no-store")
    ms = int((time.monotonic() - started) * 1000)
    if ms > 1000:
        log.warning("slow request %s %s %sms", request.method, request.url.path, ms)
    return response


for r in (auth.router, jobs.router, public.router, candidate.router, admin.router):
    app.include_router(r, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/ready")
def ready():
    with get_engine().connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ready", "llm": bool(settings.mistral_api_key), "embeddings": settings.embeddings_provider}

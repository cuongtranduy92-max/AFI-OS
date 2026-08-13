from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from afi_os import __version__
from afi_os.api import api_router
from afi_os.config import get_settings
from afi_os.db import Base, engine
from afi_os.services.appraisal_jobs import recover_stale_appraisal_jobs

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    recover_stale_appraisal_jobs()
    yield


app = FastAPI(
    title="AFI-OS",
    version=__version__,
    description="Local-first affiliate operations platform",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url=None,
)
app.include_router(api_router)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self' http://127.0.0.1:8765 http://localhost:8765; "
        "frame-ancestors 'none'"
    )
    return response


@app.exception_handler(Exception)
async def unhandled_error(_request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal error", "type": type(exc).__name__},
    )


app.mount("/", StaticFiles(directory=settings.web_root, html=True), name="web")

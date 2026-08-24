"""
FastAPI app entrypoint: wires together the patients CRUD API, the Vapi
webhook, the appointments/call-logs bonus endpoints, CORS, a catch-all error
handler (so an unhandled exception still returns the {"data","error"}
envelope instead of FastAPI's default plaintext 500), and index creation on
startup.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import appointments, call_logs, patients, vapi_tools
from app.api.schemas import fail
from app.core.config import get_settings
from app.core.logging import logger
from app.db.mongo import ensure_indexes, get_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_indexes()
    logger.info("startup complete, indexes ensured")
    yield


app = FastAPI(title="CareCloud Patient Registration API", version="1.0.0", lifespan=lifespan)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(patients.router)
app.include_router(vapi_tools.router)
app.include_router(appointments.router)
app.include_router(call_logs.router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content=fail("INTERNAL_ERROR", "Something went wrong"))


@app.get("/health")
async def health(response: Response):
    # A health check that doesn't touch the database would happily report
    # "ok" while every real endpoint 500s on a dead Mongo connection - most
    # dangerous right after a Render cold start, exactly when you'd want
    # this to catch it.
    try:
        await get_db().command("ping")
        return {"status": "ok", "database": "connected"}
    except Exception:
        logger.exception("health check: database ping failed")
        response.status_code = 503
        return {"status": "degraded", "database": "unreachable"}

import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from database import init_db
from scheduler import init_scheduler
from routers import flights, searches, settings, crawler, airlines, tracks, automate


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    init_scheduler()
    yield


app = FastAPI(
    title="FlyCal API",
    version="1.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

_cors_origins = os.environ.get("CORS_ORIGINS", "").strip()
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins.split(","),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(flights.router)
app.include_router(searches.router)
app.include_router(settings.router)
app.include_router(crawler.router)
app.include_router(airlines.router)
app.include_router(tracks.router)
app.include_router(automate.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/logs")
def get_logs():
    from database import SessionLocal, CrawlerLog
    db = SessionLocal()
    try:
        logs = (
            db.query(CrawlerLog)
            .order_by(CrawlerLog.started_at.desc())
            .limit(50)
            .all()
        )
        return [
            {
                "id": log.id,
                "search_id": log.search_id,
                "triggered_by": log.triggered_by,
                "status": log.status,
                "error_msg": log.error_msg,
                "started_at": log.started_at.isoformat() if log.started_at else None,
                "ended_at": log.ended_at.isoformat() if log.ended_at else None,
            }
            for log in logs
        ]
    finally:
        db.close()


_data_dir = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data"))
_logo_dir = os.path.join(_data_dir, "logos")
os.makedirs(_logo_dir, exist_ok=True)
app.mount("/api/airlines/logos", StaticFiles(directory=_logo_dir), name="logos")

_frontend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend")
if os.path.isdir(_frontend_dir):
    app.mount("/", StaticFiles(directory=_frontend_dir, html=True), name="frontend")

import asyncio
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import CrawlerLog, Search, Setting, get_db

logger = logging.getLogger("flycal.routers.crawler")

router = APIRouter(prefix="/api/crawler", tags=["crawler"])


def _get_setting(db: Session, key: str, default: str = "") -> str:
    row = db.query(Setting).filter(Setting.key == key).first()
    return row.value if row else default


@router.get("/status")
def crawler_status(db: Session = Depends(get_db)):
    enabled = _get_setting(db, "crawler_enabled", "false") == "true"
    last_log = db.query(CrawlerLog).order_by(CrawlerLog.started_at.desc()).first()
    from scheduler import get_next_run_time
    next_run = get_next_run_time()
    return {
        "enabled": enabled,
        "last_run": {
            "started_at": last_log.started_at.isoformat() if last_log and last_log.started_at else None,
            "ended_at": last_log.ended_at.isoformat() if last_log and last_log.ended_at else None,
            "status": last_log.status if last_log else None,
            "error_msg": last_log.error_msg if last_log else None,
        } if last_log else None,
        "next_run": next_run,
    }


@router.post("/toggle")
def toggle_crawler(db: Session = Depends(get_db)):
    current = _get_setting(db, "crawler_enabled", "false")
    new_val = "false" if current == "true" else "true"
    existing = db.query(Setting).filter(Setting.key == "crawler_enabled").first()
    if existing:
        existing.value = new_val
    else:
        db.add(Setting(key="crawler_enabled", value=new_val))
    db.commit()

    from scheduler import update_scheduler_state
    update_scheduler_state(new_val == "true")

    return {"enabled": new_val == "true"}


@router.post("/run")
async def manual_run(db: Session = Depends(get_db)):
    last_search = db.query(Search).filter(Search.is_last == True).first()
    if not last_search:
        raise HTTPException(status_code=400, detail="No search to run. Create a search first.")

    from routers.flights import _run_scraping
    asyncio.ensure_future(_run_scraping(last_search.id))
    return {"status": "crawler_started", "search_id": last_search.id}


@router.get("/logs", tags=["logs"])
def get_logs(db: Session = Depends(get_db)):
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

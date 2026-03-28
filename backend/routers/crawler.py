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
    crawler_time = _get_setting(db, "crawler_time", "07:00")
    last_log = db.query(CrawlerLog).order_by(CrawlerLog.started_at.desc()).first()
    from scheduler import get_next_run_times
    next_run = get_next_run_times()

    # Crawler target search info
    crawler_search_id = _get_setting(db, "crawler_search_id", "")
    crawler_started_at = _get_setting(db, "crawler_started_at", "")
    target_search = None
    if crawler_search_id:
        try:
            s = db.query(Search).filter(Search.id == int(crawler_search_id)).first()
            if s:
                import json
                try:
                    airlines_list = json.loads(s.airlines) if s.airlines else []
                except (json.JSONDecodeError, TypeError):
                    airlines_list = []
                target_search = {
                    "id": s.id,
                    "origin_city": s.origin_city,
                    "destination_city": s.destination_city,
                    "date_from": s.date_from.isoformat() if s.date_from else "",
                    "date_to": s.date_to.isoformat() if s.date_to else "",
                    "airlines": airlines_list,
                }
        except (ValueError, TypeError):
            pass

    return {
        "enabled": enabled,
        "crawler_time": crawler_time,
        "last_run": {
            "started_at": (last_log.started_at.isoformat() + "Z") if last_log and last_log.started_at else None,
            "ended_at": (last_log.ended_at.isoformat() + "Z") if last_log and last_log.ended_at else None,
            "status": last_log.status if last_log else None,
            "error_msg": last_log.error_msg if last_log else None,
        } if last_log else None,
        "next_run": next_run,
        "crawler_search_id": crawler_search_id,
        "crawler_started_at": crawler_started_at,
        "target_search": target_search,
    }


def _set_setting(db: Session, key: str, value: str):
    existing = db.query(Setting).filter(Setting.key == key).first()
    if existing:
        existing.value = value
    else:
        db.add(Setting(key=key, value=value))


@router.post("/toggle")
def toggle_crawler(db: Session = Depends(get_db)):
    current = _get_setting(db, "crawler_enabled", "false")
    new_val = "false" if current == "true" else "true"
    _set_setting(db, "crawler_enabled", new_val)

    # When enabling, record which search and when
    if new_val == "true":
        last_search = db.query(Search).filter(Search.is_last == True).first()
        if last_search:
            _set_setting(db, "crawler_search_id", str(last_search.id))
            _set_setting(db, "crawler_started_at", datetime.utcnow().isoformat())
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


@router.post("/update-schedule")
def update_schedule(data: dict, db: Session = Depends(get_db)):
    """Update crawler schedule time. Expects {time: '07:00'}"""
    time_val = data.get("time", "07:00")
    _set_setting(db, "crawler_time", time_val)
    db.commit()

    from scheduler import update_schedule_time
    update_schedule_time(time_val)

    return {"ok": True, "time": time_val}


@router.get("/logs", tags=["logs"])
def get_logs(db: Session = Depends(get_db)):
    logs = (
        db.query(CrawlerLog)
        .order_by(CrawlerLog.started_at.desc())
        .limit(100)
        .all()
    )
    return [
        {
            "id": log.id,
            "search_id": log.search_id,
            "triggered_by": log.triggered_by,
            "status": log.status,
            "error_msg": log.error_msg,
            "started_at": (log.started_at.isoformat() + "Z") if log.started_at else None,
            "ended_at": (log.ended_at.isoformat() + "Z") if log.ended_at else None,
        }
        for log in logs
    ]

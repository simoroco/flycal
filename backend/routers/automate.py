import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from database import (
    ScheduledCrawler, Search, CrawlerLog, Setting, get_db,
    log_activity,
)
from scheduler import sync_scheduler_jobs, update_scheduler_state, get_next_run_times, ALLOWED_TIMES

logger = logging.getLogger("flycal.routers.automate")

router = APIRouter(prefix="/api/automate", tags=["automate"])


class CrawlerCreateRequest(BaseModel):
    search_id: int
    schedule_time: str = "04:00"


class CrawlerUpdateRequest(BaseModel):
    schedule_time: Optional[str] = None
    enabled: Optional[bool] = None


def _crawler_to_dict(c: ScheduledCrawler, db: Session):
    search = db.query(Search).filter(Search.id == c.search_id).first()
    airlines = json.loads(search.airlines) if search and search.airlines else []
    return {
        "id": c.id,
        "search_id": c.search_id,
        "schedule_time": c.schedule_time,
        "enabled": c.enabled,
        "created_at": c.created_at.isoformat() + "Z" if c.created_at else "",
        "search": {
            "id": search.id,
            "origin_city": search.origin_city,
            "destination_city": search.destination_city,
            "date_from": search.date_from.isoformat() if search.date_from else "",
            "date_to": search.date_to.isoformat() if search.date_to else "",
            "trip_type": search.trip_type,
            "airlines": airlines,
        } if search else None,
    }


@router.get("/crawlers")
def list_crawlers(db: Session = Depends(get_db)):
    crawlers = db.query(ScheduledCrawler).order_by(ScheduledCrawler.created_at.desc()).all()
    return [_crawler_to_dict(c, db) for c in crawlers]


@router.post("/crawlers")
def create_crawler(req: CrawlerCreateRequest, db: Session = Depends(get_db)):
    if req.schedule_time not in ALLOWED_TIMES:
        raise HTTPException(status_code=400, detail=f"Invalid schedule_time. Allowed: {ALLOWED_TIMES}")

    search = db.query(Search).filter(Search.id == req.search_id).first()
    if not search:
        raise HTTPException(status_code=404, detail="Search not found")

    # Check if crawler already exists for this search
    existing = db.query(ScheduledCrawler).filter(ScheduledCrawler.search_id == req.search_id).first()
    if existing:
        raise HTTPException(status_code=409, detail="Crawler already exists for this search")

    crawler = ScheduledCrawler(
        search_id=req.search_id,
        schedule_time=req.schedule_time,
        enabled=True,
    )
    db.add(crawler)
    db.commit()
    db.refresh(crawler)
    sync_scheduler_jobs()
    log_activity(db, "crawler", "created", f"{search.origin_city}→{search.destination_city} at {req.schedule_time}")
    return _crawler_to_dict(crawler, db)


@router.put("/crawlers/{crawler_id}")
def update_crawler(crawler_id: int, req: CrawlerUpdateRequest, db: Session = Depends(get_db)):
    crawler = db.query(ScheduledCrawler).filter(ScheduledCrawler.id == crawler_id).first()
    if not crawler:
        raise HTTPException(status_code=404, detail="Crawler not found")

    if req.schedule_time is not None:
        if req.schedule_time not in ALLOWED_TIMES:
            raise HTTPException(status_code=400, detail=f"Invalid schedule_time. Allowed: {ALLOWED_TIMES}")
        crawler.schedule_time = req.schedule_time

    if req.enabled is not None:
        crawler.enabled = req.enabled

    db.commit()
    db.refresh(crawler)
    sync_scheduler_jobs()
    search = db.query(Search).filter(Search.id == crawler.search_id).first()
    route = f"{search.origin_city}→{search.destination_city}" if search else f"crawler #{crawler_id}"
    changes = []
    if req.schedule_time is not None:
        changes.append(f"schedule → {req.schedule_time}")
    if req.enabled is not None:
        changes.append("enabled" if req.enabled else "disabled")
    log_activity(db, "crawler", "updated", f"{route} {', '.join(changes)}")
    return _crawler_to_dict(crawler, db)


@router.delete("/crawlers/{crawler_id}")
def delete_crawler(crawler_id: int, db: Session = Depends(get_db)):
    crawler = db.query(ScheduledCrawler).filter(ScheduledCrawler.id == crawler_id).first()
    if not crawler:
        raise HTTPException(status_code=404, detail="Crawler not found")
    search = db.query(Search).filter(Search.id == crawler.search_id).first()
    route = f"{search.origin_city}→{search.destination_city}" if search else f"crawler #{crawler_id}"
    schedule = crawler.schedule_time
    db.delete(crawler)
    db.commit()
    sync_scheduler_jobs()
    log_activity(db, "crawler", "deleted", f"{route} ({schedule})")
    return {"ok": True}


@router.post("/crawlers/{crawler_id}/run")
async def run_crawler(crawler_id: int, db: Session = Depends(get_db)):
    import asyncio
    crawler = db.query(ScheduledCrawler).filter(ScheduledCrawler.id == crawler_id).first()
    if not crawler:
        raise HTTPException(status_code=404, detail="Crawler not found")

    source_search = db.query(Search).filter(Search.id == crawler.search_id).first()
    if not source_search:
        raise HTTPException(status_code=404, detail="Source search not found")

    # Create new search — set is_last so Scan page picks it up
    db.query(Search).filter(Search.is_last == True).update({"is_last": False})
    new_search = Search(
        origin_city=source_search.origin_city,
        destination_city=source_search.destination_city,
        date_from=source_search.date_from,
        date_to=source_search.date_to,
        trip_type=source_search.trip_type,
        airlines=source_search.airlines,
        is_last=True,
        created_at=datetime.utcnow(),
    )
    db.add(new_search)
    db.commit()
    db.refresh(new_search)

    from routers.flights import _run_scraping
    asyncio.ensure_future(_run_scraping(new_search.id, triggered_by="auto"))

    return {"search_id": new_search.id, "status": "started"}


@router.post("/toggle")
def toggle_global_crawler(db: Session = Depends(get_db)):
    setting = db.query(Setting).filter(Setting.key == "crawler_enabled").first()
    if not setting:
        setting = Setting(key="crawler_enabled", value="false")
        db.add(setting)

    new_val = "false" if setting.value == "true" else "true"
    setting.value = new_val

    if new_val == "true":
        started = db.query(Setting).filter(Setting.key == "crawler_started_at").first()
        if started:
            started.value = datetime.utcnow().isoformat()

    db.commit()
    update_scheduler_state(new_val == "true")
    log_activity(db, "system", "enabled" if new_val == "true" else "disabled", f"Global automation {'enabled' if new_val == 'true' else 'disabled'}")

    return {"enabled": new_val == "true"}


@router.get("/status")
def get_automate_status(db: Session = Depends(get_db)):
    setting = db.query(Setting).filter(Setting.key == "crawler_enabled").first()
    enabled = setting and setting.value == "true"

    crawler_count = db.query(ScheduledCrawler).count()
    enabled_count = db.query(ScheduledCrawler).filter(ScheduledCrawler.enabled == True).count()
    next_runs = get_next_run_times()

    # Last run from CrawlerLog
    last_log = db.query(CrawlerLog).order_by(CrawlerLog.started_at.desc()).first()
    last_run = None
    if last_log:
        last_run = {
            "started_at": last_log.started_at.isoformat() + "Z" if last_log.started_at else None,
            "ended_at": last_log.ended_at.isoformat() + "Z" if last_log.ended_at else None,
            "status": last_log.status,
            "error_msg": last_log.error_msg,
        }

    return {
        "enabled": enabled,
        "crawler_count": crawler_count,
        "enabled_count": enabled_count,
        "next_runs": next_runs,
        "last_run": last_run,
    }


@router.get("/logs")
def get_automate_logs(db: Session = Depends(get_db)):
    from database import ActivityLog

    # Fetch CrawlerLog entries
    crawler_logs = (
        db.query(CrawlerLog)
        .order_by(CrawlerLog.started_at.desc())
        .limit(200)
        .all()
    )

    # Fetch ActivityLog entries
    activity_logs = (
        db.query(ActivityLog)
        .order_by(ActivityLog.created_at.desc())
        .limit(200)
        .all()
    )

    # Merge into unified format
    merged = []
    for log in crawler_logs:
        err = f" — {log.error_msg}" if log.error_msg else ""
        merged.append({
            "type": "scan",
            "action": log.status,
            "message": f"{log.triggered_by}{err}",
            "timestamp": log.started_at.isoformat() + "Z" if log.started_at else None,
        })

    for log in activity_logs:
        merged.append({
            "type": log.category,
            "action": log.action,
            "message": log.message,
            "timestamp": log.created_at.isoformat() + "Z" if log.created_at else None,
        })

    # Sort by timestamp descending
    merged.sort(key=lambda x: x["timestamp"] or "", reverse=True)
    return merged[:200]


@router.delete("/logs")
def clear_automate_logs(db: Session = Depends(get_db)):
    from database import ActivityLog
    activity_count = db.query(ActivityLog).delete()
    crawler_count = db.query(CrawlerLog).delete()
    db.commit()
    return {"ok": True, "deleted": activity_count + crawler_count}

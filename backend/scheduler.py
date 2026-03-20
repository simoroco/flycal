import asyncio
import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

logger = logging.getLogger("flycal.scheduler")

_scheduler: AsyncIOScheduler = None
JOB_ID_1 = "flycal_crawler_1"
JOB_ID_2 = "flycal_crawler_2"
TZ = pytz.timezone("Europe/Paris")


async def _scheduled_crawl():
    from database import SessionLocal, Search, Setting
    db = SessionLocal()
    try:
        enabled_setting = db.query(Setting).filter(Setting.key == "crawler_enabled").first()
        if not enabled_setting or enabled_setting.value != "true":
            logger.info("Scheduler triggered but crawler is disabled, skipping.")
            return

        last_search = db.query(Search).filter(Search.is_last == True).first()
        if not last_search:
            logger.info("Scheduler triggered but no last search found, skipping.")
            return

        # Create a new Search entry so each auto-crawl appears in history
        db.query(Search).filter(Search.is_last == True).update({"is_last": False})
        new_search = Search(
            origin_city=last_search.origin_city,
            destination_city=last_search.destination_city,
            date_from=last_search.date_from,
            date_to=last_search.date_to,
            trip_type=last_search.trip_type,
            airlines=last_search.airlines,
            is_last=True,
            created_at=datetime.utcnow(),
        )
        db.add(new_search)
        db.commit()
        db.refresh(new_search)
        search_id = new_search.id
    finally:
        db.close()

    logger.info(f"Scheduler running crawl for search {search_id} (auto)")
    from routers.flights import _run_scraping
    await _run_scraping(search_id, triggered_by="auto")


def _parse_times() -> list:
    """Parse crawler_times from DB into list of (hour, minute) tuples."""
    try:
        from database import SessionLocal, Setting
        db = SessionLocal()
        try:
            row = db.query(Setting).filter(Setting.key == "crawler_times").first()
            times_str = row.value if row and row.value else "07:00"
        finally:
            db.close()
    except Exception:
        times_str = "07:00"

    parts = [t.strip() for t in times_str.split(",") if t.strip()]
    result = []
    for part in parts:
        try:
            h, m = part.split(":")
            result.append((int(h), int(m)))
        except (ValueError, IndexError):
            result.append((7, 0))
    return result


def _apply_jobs(times: list):
    """Apply job configuration: create/update/remove jobs based on times list."""
    global _scheduler
    if not _scheduler:
        return

    # Job 1 — always present if times has at least 1 entry
    if len(times) >= 1:
        h, m = times[0]
        _scheduler.add_job(
            _scheduled_crawl,
            CronTrigger(hour=h, minute=m, timezone=TZ),
            id=JOB_ID_1,
            replace_existing=True,
            misfire_grace_time=3600,
        )
        logger.info(f"Job #1 set to {h:02d}:{m:02d}")
    else:
        if _scheduler.get_job(JOB_ID_1):
            _scheduler.remove_job(JOB_ID_1)

    # Job 2 — only if times has 2 entries
    if len(times) >= 2:
        h, m = times[1]
        _scheduler.add_job(
            _scheduled_crawl,
            CronTrigger(hour=h, minute=m, timezone=TZ),
            id=JOB_ID_2,
            replace_existing=True,
            misfire_grace_time=3600,
        )
        logger.info(f"Job #2 set to {h:02d}:{m:02d}")
    else:
        if _scheduler.get_job(JOB_ID_2):
            _scheduler.remove_job(JOB_ID_2)


def init_scheduler():
    global _scheduler
    _scheduler = AsyncIOScheduler(timezone=TZ)

    times = _parse_times()
    _apply_jobs(times)

    _scheduler.start()
    times_desc = ", ".join(f"{h:02d}:{m:02d}" for h, m in times)
    logger.info(f"APScheduler started with schedule: {times_desc} Europe/Paris")


def get_next_run_time() -> str:
    global _scheduler
    if not _scheduler:
        return None
    # Return the earliest next run across both jobs
    next_times = []
    for jid in (JOB_ID_1, JOB_ID_2):
        job = _scheduler.get_job(jid)
        if job and job.next_run_time:
            next_times.append(job.next_run_time)
    if next_times:
        return min(next_times).isoformat()
    return None


def update_scheduler_state(enabled: bool):
    global _scheduler
    if not _scheduler:
        return
    if enabled:
        times = _parse_times()
        _apply_jobs(times)
        times_desc = ", ".join(f"{h:02d}:{m:02d}" for h, m in times)
        logger.info(f"Scheduler jobs enabled ({times_desc})")
    else:
        for jid in (JOB_ID_1, JOB_ID_2):
            if _scheduler.get_job(jid):
                _scheduler.remove_job(jid)
        logger.info("Scheduler jobs removed (disabled)")
    logger.info(f"Scheduler state updated: enabled={enabled}")


def update_schedule_times(times_str: str):
    """Update the scheduler with new times (called from API)."""
    global _scheduler
    if not _scheduler:
        return

    parts = [t.strip() for t in times_str.split(",") if t.strip()]
    times = []
    for part in parts:
        try:
            h, m = part.split(":")
            times.append((int(h), int(m)))
        except (ValueError, IndexError):
            times.append((7, 0))

    _apply_jobs(times)
    times_desc = ", ".join(f"{h:02d}:{m:02d}" for h, m in times)
    logger.info(f"Scheduler times updated to: {times_desc}")

import asyncio
import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

logger = logging.getLogger("flycal.scheduler")

_scheduler: AsyncIOScheduler = None
JOB_ID = "flycal_crawler"
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


def _get_crawler_time() -> str:
    """Read crawler_time from database, default '07:00'."""
    try:
        from database import SessionLocal, Setting
        db = SessionLocal()
        try:
            row = db.query(Setting).filter(Setting.key == "crawler_time").first()
            return row.value if row and row.value else "07:00"
        finally:
            db.close()
    except Exception:
        return "07:00"


def _build_trigger(time_str: str = None):
    """Build CronTrigger from a single time string like '07:00'."""
    if not time_str:
        time_str = _get_crawler_time()
    try:
        h, m = time_str.strip().split(":")
        return CronTrigger(hour=int(h), minute=int(m), timezone=TZ)
    except (ValueError, IndexError):
        return CronTrigger(hour=7, minute=0, timezone=TZ)


def init_scheduler():
    global _scheduler
    _scheduler = AsyncIOScheduler(timezone=TZ)

    time_str = _get_crawler_time()
    _scheduler.add_job(
        _scheduled_crawl,
        _build_trigger(time_str),
        id=JOB_ID,
        replace_existing=True,
        misfire_grace_time=3600,
    )

    _scheduler.start()
    logger.info(f"APScheduler started with daily schedule: {time_str} Europe/Paris")


def get_next_run_time() -> str:
    global _scheduler
    if not _scheduler:
        return None
    job = _scheduler.get_job(JOB_ID)
    if job and job.next_run_time:
        return job.next_run_time.isoformat()
    return None


def update_scheduler_state(enabled: bool):
    global _scheduler
    if not _scheduler:
        return
    if enabled:
        time_str = _get_crawler_time()
        _scheduler.add_job(
            _scheduled_crawl,
            _build_trigger(time_str),
            id=JOB_ID,
            replace_existing=True,
            misfire_grace_time=3600,
        )
        logger.info(f"Scheduler job enabled ({time_str})")
    else:
        if _scheduler.get_job(JOB_ID):
            _scheduler.remove_job(JOB_ID)
        logger.info("Scheduler job removed (disabled)")
    logger.info(f"Scheduler state updated: enabled={enabled}")


def update_schedule_time(time_str: str):
    """Update the scheduler with a new time (called from API)."""
    global _scheduler
    if not _scheduler:
        return
    _scheduler.add_job(
        _scheduled_crawl,
        _build_trigger(time_str),
        id=JOB_ID,
        replace_existing=True,
        misfire_grace_time=3600,
    )
    logger.info(f"Scheduler time updated to: {time_str}")

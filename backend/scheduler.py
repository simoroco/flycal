import asyncio
import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
import pytz

logger = logging.getLogger("flycal.scheduler")

_scheduler: AsyncIOScheduler = None
JOB_ID = "flycal_crawler"
TZ = pytz.timezone("Europe/Paris")


def _get_crawler_interval() -> int:
    """Read crawler_interval from settings, default 60 minutes."""
    try:
        from database import SessionLocal, Setting
        db = SessionLocal()
        try:
            row = db.query(Setting).filter(Setting.key == "crawler_interval").first()
            return int(row.value) if row and row.value else 60
        finally:
            db.close()
    except Exception:
        return 60


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

        search_id = last_search.id
    finally:
        db.close()

    logger.info(f"Scheduler running crawl for search {search_id}")
    from routers.flights import _run_scraping
    await _run_scraping(search_id)


def _build_trigger(interval_minutes: int = None):
    if interval_minutes is None:
        interval_minutes = _get_crawler_interval()
    return IntervalTrigger(minutes=max(1, interval_minutes), timezone=TZ)


def init_scheduler():
    global _scheduler
    _scheduler = AsyncIOScheduler(timezone=TZ)

    interval = _get_crawler_interval()
    _scheduler.add_job(
        _scheduled_crawl,
        _build_trigger(interval),
        id=JOB_ID,
        replace_existing=True,
        misfire_grace_time=3600,
    )

    _scheduler.start()
    logger.info(f"APScheduler started with interval of {interval} minutes")


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
    job = _scheduler.get_job(JOB_ID)
    if enabled:
        interval = _get_crawler_interval()
        _scheduler.add_job(
            _scheduled_crawl,
            _build_trigger(interval),
            id=JOB_ID,
            replace_existing=True,
            misfire_grace_time=3600,
        )
        logger.info(f"Scheduler job enabled with interval {interval} min")
    elif not enabled and job:
        _scheduler.remove_job(JOB_ID)
        logger.info("Scheduler job removed (disabled)")
    logger.info(f"Scheduler state updated: enabled={enabled}")

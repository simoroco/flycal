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

        search_id = last_search.id
    finally:
        db.close()

    logger.info(f"Scheduler running crawl for search {search_id}")
    from routers.flights import _run_scraping
    await _run_scraping(search_id)


def init_scheduler():
    global _scheduler
    _scheduler = AsyncIOScheduler(timezone=TZ)

    _scheduler.add_job(
        _scheduled_crawl,
        CronTrigger(hour="7,20", minute=0, timezone=TZ),
        id=JOB_ID,
        replace_existing=True,
        misfire_grace_time=3600,
    )

    _scheduler.start()
    logger.info("APScheduler started with jobs at 07:00 and 20:00 Europe/Paris")


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
    if enabled and not job:
        _scheduler.add_job(
            _scheduled_crawl,
            CronTrigger(hour="7,20", minute=0, timezone=TZ),
            id=JOB_ID,
            replace_existing=True,
            misfire_grace_time=3600,
        )
        logger.info("Scheduler job re-enabled")
    elif not enabled and job:
        pass
    logger.info(f"Scheduler state updated: enabled={enabled}")

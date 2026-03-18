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


def _get_crawler_times() -> str:
    """Read crawler_times from database, default '07:00,22:00'."""
    try:
        from database import SessionLocal, Setting
        db = SessionLocal()
        try:
            row = db.query(Setting).filter(Setting.key == "crawler_times").first()
            return row.value if row and row.value else "07:00,22:00"
        finally:
            db.close()
    except Exception:
        return "07:00,22:00"


def _build_trigger(times_str: str = None):
    """Build CronTrigger from times string like '07:00,22:00' or '07:00'."""
    if not times_str:
        times_str = _get_crawler_times()

    parts = [t.strip() for t in times_str.split(",") if t.strip()]
    hours = []
    minutes = []
    for part in parts:
        try:
            h, m = part.split(":")
            hours.append(int(h))
            minutes.append(int(m))
        except (ValueError, IndexError):
            hours.append(7)
            minutes.append(0)

    if not hours:
        return CronTrigger(hour="7,22", minute=0, timezone=TZ)

    # If all minutes are the same, use simple cron
    if len(set(minutes)) == 1:
        hour_str = ",".join(str(h) for h in hours)
        return CronTrigger(hour=hour_str, minute=minutes[0], timezone=TZ)
    else:
        # Multiple different minutes - use first time's minute and all hours
        # (APScheduler cron doesn't support per-hour minutes, so approximate)
        hour_str = ",".join(str(h) for h in hours)
        return CronTrigger(hour=hour_str, minute=minutes[0], timezone=TZ)


def init_scheduler():
    global _scheduler
    _scheduler = AsyncIOScheduler(timezone=TZ)

    times_str = _get_crawler_times()
    _scheduler.add_job(
        _scheduled_crawl,
        _build_trigger(times_str),
        id=JOB_ID,
        replace_existing=True,
        misfire_grace_time=3600,
    )

    _scheduler.start()
    logger.info(f"APScheduler started with schedule: {times_str} Europe/Paris")


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
        times_str = _get_crawler_times()
        _scheduler.add_job(
            _scheduled_crawl,
            _build_trigger(times_str),
            id=JOB_ID,
            replace_existing=True,
            misfire_grace_time=3600,
        )
        logger.info(f"Scheduler job enabled ({times_str})")
    elif not enabled and job:
        _scheduler.remove_job(JOB_ID)
        logger.info("Scheduler job removed (disabled)")
    logger.info(f"Scheduler state updated: enabled={enabled}")


def update_schedule_times(times_str: str):
    """Update the scheduler with new times (called from API)."""
    global _scheduler
    if not _scheduler:
        return
    job = _scheduler.get_job(JOB_ID)
    if job:
        _scheduler.add_job(
            _scheduled_crawl,
            _build_trigger(times_str),
            id=JOB_ID,
            replace_existing=True,
            misfire_grace_time=3600,
        )
        logger.info(f"Scheduler times updated to: {times_str}")

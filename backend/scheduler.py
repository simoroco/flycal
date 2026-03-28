import asyncio
import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger("flycal.scheduler")

scheduler = AsyncIOScheduler(timezone="Europe/Paris")
ALLOWED_TIMES = ["04:00", "07:00", "14:00", "18:00", "23:00"]


async def _scheduled_crawl_slot(time_slot: str):
    """Run all enabled crawlers for this time slot, sequentially."""
    from database import SessionLocal, Setting, Search, ScheduledCrawler, CrawlerLog
    import json

    db = SessionLocal()
    try:
        # Check global enable
        enabled_setting = db.query(Setting).filter(Setting.key == "crawler_enabled").first()
        if not enabled_setting or enabled_setting.value != "true":
            logger.info(f"Global crawler disabled, skipping slot {time_slot}")
            from database import log_activity
            log_activity(db, "system", "skipped", f"Slot {time_slot} skipped — global disabled")
            return

        crawlers = (
            db.query(ScheduledCrawler)
            .filter(ScheduledCrawler.schedule_time == time_slot, ScheduledCrawler.enabled == True)
            .all()
        )

        if not crawlers:
            logger.info(f"No enabled crawlers for slot {time_slot}")
            return

        logger.info(f"Running {len(crawlers)} crawler(s) for slot {time_slot}")
        from database import log_activity
        log_activity(db, "system", "started", f"Slot {time_slot} — {len(crawlers)} crawler(s)")

        for crawler in crawlers:
            source_search = db.query(Search).filter(Search.id == crawler.search_id).first()
            if not source_search:
                logger.warning(f"Crawler {crawler.id}: source search {crawler.search_id} not found, skipping")
                continue

            try:
                # Parse airlines
                airlines_list = json.loads(source_search.airlines) if source_search.airlines else []

                # Create new search with same parameters
                new_search = Search(
                    origin_city=source_search.origin_city,
                    destination_city=source_search.destination_city,
                    date_from=source_search.date_from,
                    date_to=source_search.date_to,
                    trip_type=source_search.trip_type,
                    airlines=source_search.airlines,
                    is_last=False,
                )
                db.add(new_search)
                db.commit()
                db.refresh(new_search)

                logger.info(f"Crawler {crawler.id}: created search #{new_search.id} for {source_search.origin_city}->{source_search.destination_city}")

                # Run scraping
                from routers.flights import _run_scraping
                await _run_scraping(new_search.id, triggered_by="auto")

            except Exception as e:
                logger.error(f"Crawler {crawler.id} failed: {e}")
                from database import log_activity
                log_activity(db, "crawler", "error", f"Crawler #{crawler.id} failed: {str(e)[:200]}")

    finally:
        db.close()


def sync_scheduler_jobs():
    """Sync APScheduler jobs with database crawlers."""
    from database import SessionLocal, Setting, ScheduledCrawler

    db = SessionLocal()
    try:
        # Check global enable
        enabled_setting = db.query(Setting).filter(Setting.key == "crawler_enabled").first()
        globally_enabled = enabled_setting and enabled_setting.value == "true"

        if not globally_enabled:
            # Remove all crawler jobs
            for job in scheduler.get_jobs():
                if job.id.startswith("flycal_crawler_"):
                    scheduler.remove_job(job.id)
            logger.info("Global crawler disabled, removed all jobs")
            return

        # Get active time slots
        active_slots = set()
        crawlers = db.query(ScheduledCrawler).filter(ScheduledCrawler.enabled == True).all()
        for c in crawlers:
            active_slots.add(c.schedule_time)

        # Current job IDs
        current_jobs = {job.id for job in scheduler.get_jobs() if job.id.startswith("flycal_crawler_")}

        # Add missing jobs
        for slot in active_slots:
            job_id = f"flycal_crawler_{slot}"
            if job_id not in current_jobs:
                hour, minute = slot.split(":")
                scheduler.add_job(
                    _scheduled_crawl_slot,
                    trigger=CronTrigger(hour=int(hour), minute=int(minute)),
                    id=job_id,
                    args=[slot],
                    misfire_grace_time=3600,
                    replace_existing=True,
                )
                logger.info(f"Added scheduler job for slot {slot}")

        # Remove jobs for slots with no enabled crawlers
        for job_id in current_jobs:
            slot = job_id.replace("flycal_crawler_", "")
            if slot not in active_slots:
                scheduler.remove_job(job_id)
                logger.info(f"Removed scheduler job for slot {slot}")

    finally:
        db.close()


def update_scheduler_state(enabled: bool):
    """Toggle global scheduler state."""
    if not enabled:
        for job in scheduler.get_jobs():
            if job.id.startswith("flycal_crawler_"):
                scheduler.remove_job(job.id)
        logger.info("Global crawler OFF — all jobs removed")
    else:
        sync_scheduler_jobs()
        logger.info("Global crawler ON — jobs synced")


def get_next_run_times():
    """Get next run time for each active slot."""
    result = {}
    for job in scheduler.get_jobs():
        if job.id.startswith("flycal_crawler_"):
            slot = job.id.replace("flycal_crawler_", "")
            next_run = job.next_run_time
            if next_run:
                result[slot] = next_run.isoformat()
    return result


def init_scheduler():
    scheduler.start()
    sync_scheduler_jobs()
    logger.info("Scheduler initialized")

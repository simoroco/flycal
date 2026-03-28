import json
import asyncio
import logging
from datetime import datetime, date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session, joinedload

from database import (
    Airline,
    Flight,
    PriceHistory,
    PriceTracker,
    Search,
    CrawlerLog,
    get_db,
)

logger = logging.getLogger("flycal.routers.flights")

router = APIRouter(prefix="/api/flights", tags=["flights"])

# Global abort flag for cancelling in-progress searches (thread-safe)
import threading
_abort_lock = threading.Lock()
_abort_search_ids: set = set()
_running_search_id: int = None  # Track which search is currently running


class SearchRequest(BaseModel):
    origin_city: str
    destination_city: str
    date_from: str
    date_to: str
    trip_type: str = "oneway"
    airlines: List[str] = []


class FlightOut(BaseModel):
    id: int
    search_id: int
    airline_id: int
    airline_name: str
    airline_fees_fixed: float
    airline_fees_percent: float
    airline_logo_url: Optional[str] = None
    direction: str
    flight_date: str
    departure_time: str
    arrival_time: str
    origin_airport: str
    destination_airport: str
    price: float
    currency: str
    scraped_at: str


class SearchOut(BaseModel):
    id: int
    origin_city: str
    destination_city: str
    date_from: str
    date_to: str
    trip_type: str
    airlines: list
    created_at: str
    is_last: bool
    flights: List[FlightOut]


def _flight_to_dict(f: Flight, db=None) -> dict:
    result = {
        "id": f.id,
        "search_id": f.search_id,
        "airline_id": f.airline_id,
        "airline_name": f.airline.name if f.airline else "",
        "airline_fees_fixed": f.airline.fees_fixed if f.airline else 0,
        "airline_fees_percent": f.airline.fees_percent if f.airline else 0,
        "airline_logo_url": f.airline.logo_url if f.airline else None,
        "direction": f.direction,
        "flight_date": f.flight_date.isoformat() if f.flight_date else "",
        "departure_time": str(f.departure_time) if f.departure_time else "",
        "arrival_time": str(f.arrival_time) if f.arrival_time else "",
        "origin_airport": f.origin_airport,
        "destination_airport": f.destination_airport,
        "price": f.price,
        "currency": f.currency,
        "scraped_at": f.scraped_at.isoformat() if f.scraped_at else "",
        "oldest_price": None,
        "oldest_price_date": None,
    }
    # Look up oldest known price from PriceTracker (persists across searches)
    if db:
        oldest = (
            db.query(PriceTracker)
            .filter(
                PriceTracker.airline_id == f.airline_id,
                PriceTracker.direction == f.direction,
                PriceTracker.flight_date == f.flight_date,
                PriceTracker.departure_time == f.departure_time,
                PriceTracker.origin_airport == f.origin_airport,
                PriceTracker.destination_airport == f.destination_airport,
            )
            .order_by(PriceTracker.recorded_at.asc())
            .first()
        )
        if oldest and oldest.price != f.price:
            result["oldest_price"] = oldest.price
            result["oldest_price_date"] = oldest.recorded_at.strftime("%Y-%m-%d") if oldest.recorded_at else None
    return result


def _search_to_dict(s: Search, db=None) -> dict:
    airlines_list = []
    try:
        airlines_list = json.loads(s.airlines)
    except (json.JSONDecodeError, TypeError):
        airlines_list = []
    return {
        "id": s.id,
        "origin_city": s.origin_city,
        "destination_city": s.destination_city,
        "date_from": s.date_from.isoformat() if s.date_from else "",
        "date_to": s.date_to.isoformat() if s.date_to else "",
        "trip_type": s.trip_type,
        "airlines": airlines_list,
        "created_at": (s.created_at.isoformat() + "Z") if s.created_at else "",
        "is_last": s.is_last,
        "flights": [_flight_to_dict(f, db=db) for f in s.flights],
    }


@router.get("/running")
def get_running_search(db: Session = Depends(get_db)):
    """Return info about the currently running search (if any)."""
    with _abort_lock:
        rid = _running_search_id
    if not rid:
        return {"running": False, "search_id": None, "search": None}
    search = db.query(Search).filter(Search.id == rid).first()
    if not search:
        return {"running": True, "search_id": rid, "search": None}
    airlines_list = []
    try:
        airlines_list = json.loads(search.airlines)
    except (json.JSONDecodeError, TypeError):
        pass
    return {
        "running": True,
        "search_id": rid,
        "search": {
            "id": search.id,
            "origin_city": search.origin_city,
            "destination_city": search.destination_city,
            "date_from": search.date_from.isoformat() if search.date_from else "",
            "date_to": search.date_to.isoformat() if search.date_to else "",
            "airlines": airlines_list,
        },
    }


@router.get("/last")
def get_last_search(db: Session = Depends(get_db)):
    search = (
        db.query(Search)
        .filter(Search.is_last == True)
        .options(joinedload(Search.flights).joinedload(Flight.airline))
        .first()
    )
    if not search:
        return {"search": None, "flights": []}
    return _search_to_dict(search, db=db)


async def _run_scraping(search_id: int, triggered_by: str = "manual"):
    global _running_search_id
    from database import SessionLocal, Flight, PriceHistory, PriceTracker, Airline, Search, CrawlerLog
    from scraper.ryanair import RyanairScraper
    from scraper.transavia import TransaviaScraper
    from scraper.airfrance import AirFranceScraper
    from scraper.airarabia import AirArabiaScraper
    from scraper.royalairmaroc import RoyalAirMarocScraper
    from scraper.amadeus_scraper import amadeus_search, is_amadeus_configured
    from scraper.google_flights import google_flights_search, google_flights_bulk_search

    with _abort_lock:
        _running_search_id = search_id

    db = SessionLocal()
    log_entry = None
    try:
        search = db.query(Search).filter(Search.id == search_id).first()
        if not search:
            logger.warning(f"Search {search_id} not found, aborting scrape")
            # Create log entry for audit trail even when search is missing
            orphan_log = CrawlerLog(
                search_id=search_id,
                triggered_by=triggered_by,
                status="error",
                error_msg=f"Search {search_id} not found",
                started_at=datetime.utcnow(),
                ended_at=datetime.utcnow(),
            )
            try:
                db.add(orphan_log)
                db.commit()
            except Exception:
                db.rollback()
            return

        log_entry = CrawlerLog(
            search_id=search_id,
            triggered_by=triggered_by,
            status="running",
            started_at=datetime.utcnow(),
        )
        db.add(log_entry)
        db.commit()

        requested_airlines = []
        try:
            requested_airlines = json.loads(search.airlines)
        except (json.JSONDecodeError, TypeError):
            pass

        airline_records = db.query(Airline).filter(Airline.enabled == True).all()
        if requested_airlines:
            airline_records = [a for a in airline_records if a.name in requested_airlines]

        airline_map = {a.name: a for a in airline_records}

        scraper_classes = {
            "Ryanair": RyanairScraper,
            "Transavia": TransaviaScraper,
            "Air France": AirFranceScraper,
            "Air Arabia": AirArabiaScraper,
            "Royal Air Maroc": RoyalAirMarocScraper,
        }

        use_amadeus = is_amadeus_configured()

        all_results = []
        failed_airlines = []

        SCRAPER_TIMEOUT = 300  # 5 min max per individual scraper

        # Phase 1: Try direct scrapers
        for airline_name, scraper_cls in scraper_classes.items():
            if search_id in _abort_search_ids:
                logger.info(f"Search {search_id} cancelled by user")
                raise Exception("Search cancelled by user")
            if airline_name not in airline_map:
                continue
            try:
                scraper = scraper_cls()
                results = await asyncio.wait_for(
                    scraper.search(
                        origin_city=search.origin_city,
                        destination_city=search.destination_city,
                        date_from=search.date_from,
                        date_to=search.date_to,
                        trip_type=search.trip_type,
                    ),
                    timeout=SCRAPER_TIMEOUT,
                )
                real_flights = [r for r in results if not getattr(r, "route_not_served", False)]
                if real_flights:
                    all_results.extend((airline_name, r) for r in results)
                elif airline_name != "Ryanair":
                    failed_airlines.append(airline_name)
                    logger.info(f"Direct scraper for {airline_name} found no flights, queued for Google Flights")
                else:
                    all_results.extend((airline_name, r) for r in results)
            except asyncio.TimeoutError:
                logger.error(f"Scraper {airline_name} timed out after {SCRAPER_TIMEOUT}s")
                if airline_name != "Ryanair":
                    failed_airlines.append(airline_name)
            except Exception as e:
                logger.error(f"Scraper {airline_name} failed: {e}")
                if airline_name != "Ryanair":
                    failed_airlines.append(airline_name)

        # Airlines without direct scrapers go straight to Google Flights
        for airline_name in airline_map:
            if airline_name not in scraper_classes and airline_name not in failed_airlines:
                failed_airlines.append(airline_name)
                logger.info(f"No direct scraper for {airline_name}, queued for Google Flights")

        # Check abort before Phase 2
        if search_id in _abort_search_ids:
            logger.info(f"Search {search_id} cancelled by user")
            raise Exception("Search cancelled by user")

        # Phase 2: Single bulk Google Flights search for all failed airlines
        if failed_airlines:
            logger.info(f"Running Google Flights bulk search for: {', '.join(failed_airlines)}")
            try:
                gf_results = await google_flights_bulk_search(
                    airline_names=failed_airlines,
                    origin_city=search.origin_city,
                    destination_city=search.destination_city,
                    date_from=search.date_from,
                    date_to=search.date_to,
                    trip_type=search.trip_type,
                )
                still_failed = []
                for airline_name, flights in gf_results.items():
                    real = [f for f in flights if not getattr(f, "route_not_served", False)]
                    if real:
                        all_results.extend((airline_name, f) for f in flights)
                    else:
                        still_failed.append(airline_name)
                        all_results.extend((airline_name, f) for f in flights)
            except Exception as e:
                logger.warning(f"Google Flights bulk search failed: {e}")
                still_failed = failed_airlines

            # Check abort before Phase 3
            if search_id in _abort_search_ids:
                logger.info(f"Search {search_id} cancelled by user")
                raise Exception("Search cancelled by user")

            # Phase 3: Amadeus fallback for airlines still without results
            if still_failed and use_amadeus:
                for airline_name in still_failed:
                    if search_id in _abort_search_ids:
                        logger.info(f"Search {search_id} cancelled by user")
                        raise Exception("Search cancelled by user")
                    try:
                        amadeus_results = await amadeus_search(
                            airline_name=airline_name,
                            origin_city=search.origin_city,
                            destination_city=search.destination_city,
                            date_from=search.date_from,
                            date_to=search.date_to,
                            trip_type=search.trip_type,
                        )
                        amadeus_real = [r for r in amadeus_results if not getattr(r, "route_not_served", False)]
                        if amadeus_real:
                            # Replace only route_not_served entries, keep real flights from earlier phases
                            all_results = [(n, r) for n, r in all_results
                                           if not (n == airline_name and getattr(r, "route_not_served", False))]
                            all_results.extend((airline_name, r) for r in amadeus_real)
                            logger.info(f"Amadeus found {len(amadeus_real)} flights for {airline_name}")
                    except Exception as am_err:
                        logger.warning(f"Amadeus fallback failed for {airline_name}: {am_err}")

        # Delete existing flights for this search (PriceHistory cascades via relationship)
        existing_flights = db.query(Flight).filter(Flight.search_id == search_id).all()
        for ef in existing_flights:
            db.delete(ef)
        db.flush()

        # Deduplicate flights and filter out route_not_served (only track which airlines had none)
        seen = set()
        deduped_results = []
        airlines_with_real_flights = set()
        for airline_name, result in all_results:
            if getattr(result, "route_not_served", False):
                continue  # Skip route_not_served entries, track via set below
            key = (airline_name, result.direction, str(result.flight_date),
                   result.departure_time, result.arrival_time,
                   result.origin_airport, result.destination_airport)
            if key not in seen:
                seen.add(key)
                deduped_results.append((airline_name, result))
                airlines_with_real_flights.add(airline_name)

        # Determine which requested airlines had no real results
        route_not_served_airlines = set(airline_map.keys()) - airlines_with_real_flights

        now = datetime.utcnow()
        for airline_name, result in deduped_results:
            airline = airline_map.get(airline_name)
            if not airline:
                continue
            flight = Flight(
                search_id=search_id,
                airline_id=airline.id,
                direction=result.direction,
                flight_date=result.flight_date,
                departure_time=result.departure_time,
                arrival_time=result.arrival_time,
                origin_airport=result.origin_airport,
                destination_airport=result.destination_airport,
                price=result.price,
                currency=result.currency,
                scraped_at=now,
            )
            db.add(flight)
            db.flush()

            ph = PriceHistory(
                flight_id=flight.id,
                price=result.price,
                recorded_at=now,
            )
            db.add(ph)

            # Record in persistent PriceTracker (cross-search)
            db.add(PriceTracker(
                airline_id=airline.id,
                direction=result.direction,
                flight_date=result.flight_date,
                departure_time=result.departure_time,
                origin_airport=result.origin_airport,
                destination_airport=result.destination_airport,
                price=result.price,
                recorded_at=now,
            ))

        if route_not_served_airlines:
            logger.info(f"Route not served by: {', '.join(route_not_served_airlines)}")

        db.commit()

        if log_entry:
            log_entry.status = "success"
            log_entry.ended_at = datetime.utcnow()
            if route_not_served_airlines:
                log_entry.error_msg = "route_not_served:" + ",".join(sorted(route_not_served_airlines))
            db.commit()

        post_errors = []
        try:
            from alert_engine import check_alerts
            check_alerts(db)
        except Exception as e:
            logger.error(f"Alert checking failed: {e}")
            post_errors.append(f"alerts:{e}")

        try:
            from email_service import send_crawl_recap
            send_crawl_recap(search_id)
        except Exception as e:
            logger.error(f"Email recap failed: {e}")
            post_errors.append(f"email:{e}")

        # Append post-scrape errors to log entry so they're visible in UI
        if post_errors and log_entry:
            existing = log_entry.error_msg or ""
            suffix = " | post:" + "; ".join(post_errors)
            log_entry.error_msg = (existing + suffix)[:500]
            db.commit()

    except Exception as e:
        logger.error(f"Scraping failed for search {search_id}: {e}")
        if log_entry:
            if "cancelled by user" in str(e).lower():
                log_entry.status = "cancelled"
            else:
                log_entry.status = "error"
            log_entry.error_msg = str(e)[:500]
            log_entry.ended_at = datetime.utcnow()
            db.commit()

        # Restore is_last to the most recent search that has results
        try:
            flight_count = db.query(Flight).filter(Flight.search_id == search_id).count()
            if flight_count == 0:
                db.query(Search).filter(Search.id == search_id).update({"is_last": False})
                prev = (
                    db.query(Search)
                    .filter(Search.id != search_id, Search.flights.any())
                    .order_by(Search.id.desc())
                    .first()
                )
                if prev:
                    prev.is_last = True
                    logger.info(f"Restored is_last to search #{prev.id} after failed/cancelled search #{search_id}")
                db.commit()
        except Exception as restore_err:
            logger.error(f"Failed to restore is_last: {restore_err}")
            db.rollback()

    finally:
        with _abort_lock:
            _abort_search_ids.discard(search_id)
            if _running_search_id == search_id:
                _running_search_id = None
        db.close()


@router.get("/price-history/{flight_id}")
def get_price_history(flight_id: int, db: Session = Depends(get_db)):
    """Get price history for a specific flight."""
    records = (
        db.query(PriceHistory)
        .filter(PriceHistory.flight_id == flight_id)
        .order_by(PriceHistory.recorded_at.asc())
        .all()
    )
    return [
        {
            "price": r.price,
            "recorded_at": r.recorded_at.isoformat() if r.recorded_at else "",
        }
        for r in records
    ]


@router.post("/cancel")
async def cancel_search(search_id: Optional[int] = None, db: Session = Depends(get_db)):
    """Cancel a specific or the current running search."""
    target_id = search_id
    if not target_id:
        # Fall back to currently running search
        with _abort_lock:
            target_id = _running_search_id
    if not target_id:
        # Final fallback: last search
        last_search = db.query(Search).filter(Search.is_last == True).first()
        if last_search:
            target_id = last_search.id
    if target_id:
        with _abort_lock:
            _abort_search_ids.add(target_id)
        return {"status": "cancelled", "search_id": target_id}
    return {"status": "no_search_running"}


@router.post("/search")
async def create_search(data: SearchRequest, db: Session = Depends(get_db)):
    if not data.origin_city or not data.origin_city.strip():
        raise HTTPException(status_code=400, detail="Origin city is required.")
    if not data.destination_city or not data.destination_city.strip():
        raise HTTPException(status_code=400, detail="Destination city is required.")
    if data.origin_city.strip().upper() == data.destination_city.strip().upper():
        raise HTTPException(status_code=400, detail="Origin and destination cities must be different.")

    # Atomic is_last flag swap — prevents race with scheduler
    db.execute(text("BEGIN IMMEDIATE"))
    try:
        db.query(Search).filter(Search.is_last == True).update({"is_last": False})
        search = Search(
            origin_city=data.origin_city.strip(),
            destination_city=data.destination_city.strip(),
            date_from=date.fromisoformat(data.date_from),
            date_to=date.fromisoformat(data.date_to),
            trip_type=data.trip_type,
            airlines=json.dumps(data.airlines),
            is_last=True,
            created_at=datetime.utcnow(),
        )
        db.add(search)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(search)

    asyncio.ensure_future(_run_scraping(search.id))
    return {"search_id": search.id, "status": "scraping_started"}

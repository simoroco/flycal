import json
import asyncio
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from database import Search, Flight, CrawlerLog, get_db

logger = logging.getLogger("flycal.routers.searches")

router = APIRouter(prefix="/api/searches", tags=["searches"])


def _flight_to_dict(f):
    return {
        "id": f.id,
        "search_id": f.search_id,
        "airline_id": f.airline_id,
        "airline_name": f.airline.name if f.airline else "",
        "airline_fees_fixed": f.airline.fees_fixed if f.airline else 0,
        "airline_fees_percent": f.airline.fees_percent if f.airline else 0,
        "direction": f.direction,
        "flight_date": f.flight_date.isoformat() if f.flight_date else "",
        "departure_time": str(f.departure_time) if f.departure_time else "",
        "arrival_time": str(f.arrival_time) if f.arrival_time else "",
        "origin_airport": f.origin_airport,
        "destination_airport": f.destination_airport,
        "price": f.price,
        "currency": f.currency,
        "scraped_at": f.scraped_at.isoformat() if f.scraped_at else "",
    }


def _search_to_dict(s):
    airlines_list = []
    try:
        airlines_list = json.loads(s.airlines)
    except (json.JSONDecodeError, TypeError):
        airlines_list = []

    last_log = None
    if s.crawler_logs:
        sorted_logs = sorted(s.crawler_logs, key=lambda l: l.started_at or datetime.min, reverse=True)
        if sorted_logs:
            last_log = sorted_logs[0]

    return {
        "id": s.id,
        "origin_city": s.origin_city,
        "destination_city": s.destination_city,
        "date_from": s.date_from.isoformat() if s.date_from else "",
        "date_to": s.date_to.isoformat() if s.date_to else "",
        "trip_type": s.trip_type,
        "airlines": airlines_list,
        "created_at": s.created_at.isoformat() if s.created_at else "",
        "is_last": s.is_last,
        "status": last_log.status if last_log else "unknown",
        "flight_count": len(s.flights),
        "flights": [_flight_to_dict(f) for f in s.flights],
    }


@router.get("")
def list_searches(db: Session = Depends(get_db)):
    searches = (
        db.query(Search)
        .options(
            joinedload(Search.flights).joinedload(Flight.airline),
            joinedload(Search.crawler_logs),
        )
        .order_by(Search.created_at.desc())
        .all()
    )
    return [_search_to_dict(s) for s in searches]


@router.post("/{search_id}/rerun")
async def rerun_search(search_id: int, db: Session = Depends(get_db)):
    search = db.query(Search).filter(Search.id == search_id).first()
    if not search:
        raise HTTPException(status_code=404, detail="Search not found")

    db.query(Search).filter(Search.is_last == True).update({"is_last": False})

    new_search = Search(
        origin_city=search.origin_city,
        destination_city=search.destination_city,
        date_from=search.date_from,
        date_to=search.date_to,
        trip_type=search.trip_type,
        airlines=search.airlines,
        is_last=True,
        created_at=datetime.utcnow(),
    )
    db.add(new_search)
    db.commit()
    db.refresh(new_search)

    from routers.flights import _run_scraping
    asyncio.ensure_future(_run_scraping(new_search.id))
    return {"search_id": new_search.id, "status": "scraping_started"}

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Optional

from database import (
    TrackedFlight, PriceAlert, AlertHistory, PriceTracker, Airline, get_db,
)

logger = logging.getLogger("flycal.routers.tracks")

router = APIRouter(prefix="/api/tracks", tags=["tracks"])


# ── Pydantic models ──

class TrackRequest(BaseModel):
    airline_id: int
    direction: str
    flight_date: str
    departure_time: str
    origin_airport: str
    destination_airport: str


class AlertRequest(BaseModel):
    alert_type: str  # "threshold", "variation", "trend_start"
    operator: Optional[str] = None
    value: Optional[float] = None
    value_is_percent: bool = False
    logic_group: int = 0
    cooldown: str = "every_scan"
    enabled: bool = True


class AlertUpdateRequest(BaseModel):
    alert_type: Optional[str] = None
    operator: Optional[str] = None
    value: Optional[float] = None
    value_is_percent: Optional[bool] = None
    logic_group: Optional[int] = None
    cooldown: Optional[str] = None
    enabled: Optional[bool] = None


# ── Helpers ──

def _track_to_dict(track: TrackedFlight, db: Session):
    airline = db.query(Airline).filter(Airline.id == track.airline_id).first()

    # Get latest price from PriceTracker
    latest = (
        db.query(PriceTracker)
        .filter(
            PriceTracker.airline_id == track.airline_id,
            PriceTracker.direction == track.direction,
            PriceTracker.flight_date == track.flight_date,
            PriceTracker.departure_time == track.departure_time,
            PriceTracker.origin_airport == track.origin_airport,
            PriceTracker.destination_airport == track.destination_airport,
        )
        .order_by(PriceTracker.recorded_at.desc())
        .first()
    )

    # Get oldest price
    oldest = (
        db.query(PriceTracker)
        .filter(
            PriceTracker.airline_id == track.airline_id,
            PriceTracker.direction == track.direction,
            PriceTracker.flight_date == track.flight_date,
            PriceTracker.departure_time == track.departure_time,
            PriceTracker.origin_airport == track.origin_airport,
            PriceTracker.destination_airport == track.destination_airport,
        )
        .order_by(PriceTracker.recorded_at.asc())
        .first()
    )

    # Count price data points
    price_count = (
        db.query(PriceTracker)
        .filter(
            PriceTracker.airline_id == track.airline_id,
            PriceTracker.direction == track.direction,
            PriceTracker.flight_date == track.flight_date,
            PriceTracker.departure_time == track.departure_time,
            PriceTracker.origin_airport == track.origin_airport,
            PriceTracker.destination_airport == track.destination_airport,
        )
        .count()
    )

    return {
        "id": track.id,
        "airline_id": track.airline_id,
        "airline_name": airline.name if airline else "",
        "airline_logo_url": airline.logo_url if airline else None,
        "airline_fees_fixed": airline.fees_fixed if airline else 0,
        "airline_fees_percent": airline.fees_percent if airline else 0,
        "direction": track.direction,
        "flight_date": track.flight_date.isoformat() if track.flight_date else "",
        "departure_time": track.departure_time,
        "origin_airport": track.origin_airport,
        "destination_airport": track.destination_airport,
        "tracked_at": track.tracked_at.isoformat() + "Z" if track.tracked_at else "",
        "current_price": latest.price if latest else None,
        "oldest_price": oldest.price if oldest else None,
        "oldest_price_date": oldest.recorded_at.isoformat() if oldest and oldest.recorded_at else None,
        "price_data_points": price_count,
        "alerts": [_alert_to_dict(a) for a in track.alerts],
    }


def _alert_to_dict(a: PriceAlert):
    return {
        "id": a.id,
        "tracked_flight_id": a.pinned_flight_id,
        "alert_type": a.alert_type,
        "operator": a.operator,
        "value": a.value,
        "value_is_percent": a.value_is_percent,
        "logic_group": a.logic_group,
        "cooldown": a.cooldown,
        "enabled": a.enabled,
        "created_at": a.created_at.isoformat() + "Z" if a.created_at else "",
    }


# ── Endpoints ──

@router.get("")
def list_tracks(db: Session = Depends(get_db)):
    tracks = (
        db.query(TrackedFlight)
        .order_by(TrackedFlight.flight_date.asc())
        .all()
    )
    return [_track_to_dict(t, db) for t in tracks]


@router.post("")
def create_track(req: TrackRequest, db: Session = Depends(get_db)):
    from datetime import date as date_type
    flight_date = date_type.fromisoformat(req.flight_date)

    existing = (
        db.query(TrackedFlight)
        .filter(
            TrackedFlight.airline_id == req.airline_id,
            TrackedFlight.direction == req.direction,
            TrackedFlight.flight_date == flight_date,
            TrackedFlight.departure_time == req.departure_time,
            TrackedFlight.origin_airport == req.origin_airport,
            TrackedFlight.destination_airport == req.destination_airport,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Flight already tracked")

    track = TrackedFlight(
        airline_id=req.airline_id,
        direction=req.direction,
        flight_date=flight_date,
        departure_time=req.departure_time,
        origin_airport=req.origin_airport,
        destination_airport=req.destination_airport,
    )
    db.add(track)
    db.commit()
    db.refresh(track)

    # Auto-alert: create a default 5% variation alert
    auto_alert = PriceAlert(
        pinned_flight_id=track.id,  # physical column name
        alert_type="variation",
        value=5.0,
        value_is_percent=True,
        logic_group=0,
        cooldown="every_scan",
        enabled=True,
    )
    db.add(auto_alert)
    db.commit()
    db.refresh(track)

    return _track_to_dict(track, db)


@router.delete("/{track_id}")
def delete_track(track_id: int, db: Session = Depends(get_db)):
    track = db.query(TrackedFlight).filter(TrackedFlight.id == track_id).first()
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")
    db.delete(track)
    db.commit()
    return {"ok": True}


@router.get("/{track_id}/price-history")
def get_track_price_history(track_id: int, db: Session = Depends(get_db)):
    track = db.query(TrackedFlight).filter(TrackedFlight.id == track_id).first()
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")

    entries = (
        db.query(PriceTracker)
        .filter(
            PriceTracker.airline_id == track.airline_id,
            PriceTracker.direction == track.direction,
            PriceTracker.flight_date == track.flight_date,
            PriceTracker.departure_time == track.departure_time,
            PriceTracker.origin_airport == track.origin_airport,
            PriceTracker.destination_airport == track.destination_airport,
        )
        .order_by(PriceTracker.recorded_at.asc())
        .all()
    )

    return [
        {
            "price": e.price,
            "recorded_at": e.recorded_at.isoformat() + "Z" if e.recorded_at else "",
        }
        for e in entries
    ]


@router.post("/check-batch")
def check_tracks_batch(flights: List[TrackRequest], db: Session = Depends(get_db)):
    """Check which flights are tracked. Returns a dict keyed by composite key."""
    from datetime import date as date_type

    all_tracks = db.query(TrackedFlight).all()
    track_map = {}
    for t in all_tracks:
        key = f"{t.airline_id}|{t.direction}|{t.flight_date.isoformat()}|{t.departure_time}|{t.origin_airport}|{t.destination_airport}"
        track_map[key] = t.id

    result = {}
    for f in flights:
        key = f"{f.airline_id}|{f.direction}|{f.flight_date}|{f.departure_time}|{f.origin_airport}|{f.destination_airport}"
        if key in track_map:
            result[key] = {"tracked": True, "track_id": track_map[key]}
        else:
            result[key] = {"tracked": False, "track_id": None}

    return result


# ── Alert endpoints ──

@router.post("/{track_id}/alerts")
def create_alert(track_id: int, req: AlertRequest, db: Session = Depends(get_db)):
    track = db.query(TrackedFlight).filter(TrackedFlight.id == track_id).first()
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")

    alert = PriceAlert(
        pinned_flight_id=track_id,
        alert_type=req.alert_type,
        operator=req.operator,
        value=req.value,
        value_is_percent=req.value_is_percent,
        logic_group=req.logic_group,
        cooldown=req.cooldown,
        enabled=req.enabled,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return _alert_to_dict(alert)


@router.put("/{track_id}/alerts/{alert_id}")
def update_alert(track_id: int, alert_id: int, req: AlertUpdateRequest, db: Session = Depends(get_db)):
    alert = (
        db.query(PriceAlert)
        .filter(PriceAlert.id == alert_id, PriceAlert.pinned_flight_id == track_id)
        .first()
    )
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    for field, val in req.dict(exclude_unset=True).items():
        setattr(alert, field, val)

    db.commit()
    db.refresh(alert)
    return _alert_to_dict(alert)


@router.delete("/{track_id}/alerts/{alert_id}")
def delete_alert(track_id: int, alert_id: int, db: Session = Depends(get_db)):
    alert = (
        db.query(PriceAlert)
        .filter(PriceAlert.id == alert_id, PriceAlert.pinned_flight_id == track_id)
        .first()
    )
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    db.delete(alert)
    db.commit()
    return {"ok": True}

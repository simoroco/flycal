import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Optional

from database import (
    PinnedFlight, PriceAlert, AlertHistory, PriceTracker, Airline, get_db,
)

logger = logging.getLogger("flycal.routers.pins")

router = APIRouter(prefix="/api/pins", tags=["pins"])


# ── Pydantic models ──

class PinRequest(BaseModel):
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

def _pin_to_dict(pin: PinnedFlight, db: Session):
    airline = db.query(Airline).filter(Airline.id == pin.airline_id).first()

    # Get latest price from PriceTracker
    latest = (
        db.query(PriceTracker)
        .filter(
            PriceTracker.airline_id == pin.airline_id,
            PriceTracker.direction == pin.direction,
            PriceTracker.flight_date == pin.flight_date,
            PriceTracker.departure_time == pin.departure_time,
            PriceTracker.origin_airport == pin.origin_airport,
            PriceTracker.destination_airport == pin.destination_airport,
        )
        .order_by(PriceTracker.recorded_at.desc())
        .first()
    )

    # Get oldest price
    oldest = (
        db.query(PriceTracker)
        .filter(
            PriceTracker.airline_id == pin.airline_id,
            PriceTracker.direction == pin.direction,
            PriceTracker.flight_date == pin.flight_date,
            PriceTracker.departure_time == pin.departure_time,
            PriceTracker.origin_airport == pin.origin_airport,
            PriceTracker.destination_airport == pin.destination_airport,
        )
        .order_by(PriceTracker.recorded_at.asc())
        .first()
    )

    # Count price data points
    price_count = (
        db.query(PriceTracker)
        .filter(
            PriceTracker.airline_id == pin.airline_id,
            PriceTracker.direction == pin.direction,
            PriceTracker.flight_date == pin.flight_date,
            PriceTracker.departure_time == pin.departure_time,
            PriceTracker.origin_airport == pin.origin_airport,
            PriceTracker.destination_airport == pin.destination_airport,
        )
        .count()
    )

    return {
        "id": pin.id,
        "airline_id": pin.airline_id,
        "airline_name": airline.name if airline else "",
        "airline_logo_url": airline.logo_url if airline else None,
        "airline_fees_fixed": airline.fees_fixed if airline else 0,
        "airline_fees_percent": airline.fees_percent if airline else 0,
        "direction": pin.direction,
        "flight_date": pin.flight_date.isoformat() if pin.flight_date else "",
        "departure_time": pin.departure_time,
        "origin_airport": pin.origin_airport,
        "destination_airport": pin.destination_airport,
        "pinned_at": pin.pinned_at.isoformat() + "Z" if pin.pinned_at else "",
        "current_price": latest.price if latest else None,
        "oldest_price": oldest.price if oldest else None,
        "oldest_price_date": oldest.recorded_at.isoformat() if oldest and oldest.recorded_at else None,
        "price_data_points": price_count,
        "alerts": [_alert_to_dict(a) for a in pin.alerts],
    }


def _alert_to_dict(a: PriceAlert):
    return {
        "id": a.id,
        "pinned_flight_id": a.pinned_flight_id,
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
def list_pins(db: Session = Depends(get_db)):
    pins = (
        db.query(PinnedFlight)
        .order_by(PinnedFlight.flight_date.asc())
        .all()
    )
    return [_pin_to_dict(p, db) for p in pins]


@router.post("")
def create_pin(req: PinRequest, db: Session = Depends(get_db)):
    from datetime import date as date_type
    flight_date = date_type.fromisoformat(req.flight_date)

    existing = (
        db.query(PinnedFlight)
        .filter(
            PinnedFlight.airline_id == req.airline_id,
            PinnedFlight.direction == req.direction,
            PinnedFlight.flight_date == flight_date,
            PinnedFlight.departure_time == req.departure_time,
            PinnedFlight.origin_airport == req.origin_airport,
            PinnedFlight.destination_airport == req.destination_airport,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Flight already pinned")

    pin = PinnedFlight(
        airline_id=req.airline_id,
        direction=req.direction,
        flight_date=flight_date,
        departure_time=req.departure_time,
        origin_airport=req.origin_airport,
        destination_airport=req.destination_airport,
    )
    db.add(pin)
    db.commit()
    db.refresh(pin)
    return _pin_to_dict(pin, db)


@router.delete("/{pin_id}")
def delete_pin(pin_id: int, db: Session = Depends(get_db)):
    pin = db.query(PinnedFlight).filter(PinnedFlight.id == pin_id).first()
    if not pin:
        raise HTTPException(status_code=404, detail="Pin not found")
    db.delete(pin)
    db.commit()
    return {"ok": True}


@router.get("/{pin_id}/price-history")
def get_pin_price_history(pin_id: int, db: Session = Depends(get_db)):
    pin = db.query(PinnedFlight).filter(PinnedFlight.id == pin_id).first()
    if not pin:
        raise HTTPException(status_code=404, detail="Pin not found")

    entries = (
        db.query(PriceTracker)
        .filter(
            PriceTracker.airline_id == pin.airline_id,
            PriceTracker.direction == pin.direction,
            PriceTracker.flight_date == pin.flight_date,
            PriceTracker.departure_time == pin.departure_time,
            PriceTracker.origin_airport == pin.origin_airport,
            PriceTracker.destination_airport == pin.destination_airport,
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
def check_pins_batch(flights: List[PinRequest], db: Session = Depends(get_db)):
    """Check which flights are pinned. Returns a dict keyed by composite key."""
    from datetime import date as date_type

    all_pins = db.query(PinnedFlight).all()
    pin_map = {}
    for p in all_pins:
        key = f"{p.airline_id}|{p.direction}|{p.flight_date.isoformat()}|{p.departure_time}|{p.origin_airport}|{p.destination_airport}"
        pin_map[key] = p.id

    result = {}
    for f in flights:
        key = f"{f.airline_id}|{f.direction}|{f.flight_date}|{f.departure_time}|{f.origin_airport}|{f.destination_airport}"
        if key in pin_map:
            result[key] = {"pinned": True, "pin_id": pin_map[key]}
        else:
            result[key] = {"pinned": False, "pin_id": None}

    return result


# ── Alert endpoints ──

@router.post("/{pin_id}/alerts")
def create_alert(pin_id: int, req: AlertRequest, db: Session = Depends(get_db)):
    pin = db.query(PinnedFlight).filter(PinnedFlight.id == pin_id).first()
    if not pin:
        raise HTTPException(status_code=404, detail="Pin not found")

    alert = PriceAlert(
        pinned_flight_id=pin_id,
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


@router.put("/{pin_id}/alerts/{alert_id}")
def update_alert(pin_id: int, alert_id: int, req: AlertUpdateRequest, db: Session = Depends(get_db)):
    alert = (
        db.query(PriceAlert)
        .filter(PriceAlert.id == alert_id, PriceAlert.pinned_flight_id == pin_id)
        .first()
    )
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    for field, val in req.dict(exclude_unset=True).items():
        setattr(alert, field, val)

    db.commit()
    db.refresh(alert)
    return _alert_to_dict(alert)


@router.delete("/{pin_id}/alerts/{alert_id}")
def delete_alert(pin_id: int, alert_id: int, db: Session = Depends(get_db)):
    alert = (
        db.query(PriceAlert)
        .filter(PriceAlert.id == alert_id, PriceAlert.pinned_flight_id == pin_id)
        .first()
    )
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    db.delete(alert)
    db.commit()
    return {"ok": True}

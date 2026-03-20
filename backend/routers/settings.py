import csv
import io
import json
import smtplib
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Dict, Any
from sqlalchemy.orm import Session

from database import Setting, Search, Flight, Airline, CrawlerLog, PriceTracker, get_db

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsUpdate(BaseModel):
    settings: Dict[str, Any]


_NUMERIC_SETTINGS = {"ideal_price", "smtp_port", "crawler_interval"}


def _get_all_settings(db: Session) -> dict:
    rows = db.query(Setting).all()
    result = {}
    for row in rows:
        key = row.key
        val = row.value
        if key == "time_slots":
            try:
                val = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                val = []
        elif val in ("true", "false"):
            val = val == "true"
        elif key in _NUMERIC_SETTINGS:
            try:
                val = int(val) if val and "." not in val else float(val)
            except (ValueError, TypeError):
                pass
        result[key] = val
    return result


@router.get("")
def get_settings(db: Session = Depends(get_db)):
    return _get_all_settings(db)


@router.put("")
def update_settings(data: SettingsUpdate, db: Session = Depends(get_db)):
    for key, value in data.settings.items():
        if isinstance(value, bool):
            str_value = "true" if value else "false"
        elif isinstance(value, (list, dict)):
            str_value = json.dumps(value)
        else:
            str_value = str(value)
        existing = db.query(Setting).filter(Setting.key == key).first()
        if existing:
            existing.value = str_value
        else:
            db.add(Setting(key=key, value=str_value))
    db.commit()
    return _get_all_settings(db)


@router.post("/smtp-test")
def test_smtp(db: Session = Depends(get_db)):
    settings = _get_all_settings(db)
    host = settings.get("smtp_host", "")
    port = int(settings.get("smtp_port", 587))
    user = settings.get("smtp_user", "")
    password = settings.get("smtp_password", "")

    if not host or not user:
        raise HTTPException(status_code=400, detail="SMTP host and user are required")

    try:
        with smtplib.SMTP(host, port, timeout=10) as server:
            server.starttls()
            server.login(user, password)
        return {"ok": True, "message": "SMTP connection successful"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"SMTP connection failed: {str(e)}")


@router.get("/export")
def export_data(db: Session = Depends(get_db)):
    """Export all settings, searches, flights, airlines, crawler logs and price tracker to CSV."""
    output = io.StringIO()

    # --- Settings ---
    output.write("[SETTINGS]\n")
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["key", "value"])
    for row in db.query(Setting).all():
        writer.writerow([row.key, row.value or ""])

    # --- Airlines ---
    output.write("\n[AIRLINES]\n")
    writer.writerow(["id", "name", "fees_fixed", "fees_percent", "enabled", "logo_url"])
    for a in db.query(Airline).all():
        writer.writerow([a.id, a.name, a.fees_fixed, a.fees_percent, a.enabled, a.logo_url or ""])

    # --- Searches ---
    output.write("\n[SEARCHES]\n")
    writer.writerow(["id", "origin_city", "destination_city", "date_from", "date_to", "trip_type", "airlines", "created_at", "is_last"])
    for s in db.query(Search).order_by(Search.id).all():
        writer.writerow([
            s.id, s.origin_city, s.destination_city,
            s.date_from.isoformat() if s.date_from else "",
            s.date_to.isoformat() if s.date_to else "",
            s.trip_type, s.airlines,
            s.created_at.isoformat() if s.created_at else "",
            s.is_last,
        ])

    # --- Flights ---
    output.write("\n[FLIGHTS]\n")
    writer.writerow(["id", "search_id", "airline_id", "direction", "flight_date", "departure_time", "arrival_time", "origin_airport", "destination_airport", "price", "currency", "scraped_at"])
    for f in db.query(Flight).order_by(Flight.id).all():
        writer.writerow([
            f.id, f.search_id, f.airline_id, f.direction,
            f.flight_date.isoformat() if f.flight_date else "",
            f.departure_time, f.arrival_time,
            f.origin_airport, f.destination_airport,
            f.price, f.currency,
            f.scraped_at.isoformat() if f.scraped_at else "",
        ])

    # --- Price Tracker ---
    output.write("\n[PRICE_TRACKER]\n")
    writer.writerow(["id", "airline_id", "direction", "flight_date", "departure_time", "origin_airport", "destination_airport", "price", "recorded_at"])
    for pt in db.query(PriceTracker).order_by(PriceTracker.id).all():
        writer.writerow([
            pt.id, pt.airline_id, pt.direction,
            pt.flight_date.isoformat() if pt.flight_date else "",
            pt.departure_time, pt.origin_airport, pt.destination_airport,
            pt.price,
            pt.recorded_at.isoformat() if pt.recorded_at else "",
        ])

    # --- Crawler Logs ---
    output.write("\n[CRAWLER_LOGS]\n")
    writer.writerow(["id", "search_id", "triggered_by", "status", "error_msg", "started_at", "ended_at"])
    for log in db.query(CrawlerLog).order_by(CrawlerLog.id).all():
        writer.writerow([
            log.id, log.search_id, log.triggered_by, log.status,
            log.error_msg or "",
            log.started_at.isoformat() if log.started_at else "",
            log.ended_at.isoformat() if log.ended_at else "",
        ])

    output.seek(0)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=flycal_export_{timestamp}.csv"},
    )


@router.post("/import")
async def import_data(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Import settings, searches, flights, airlines, crawler logs from CSV."""
    content = (await file.read()).decode("utf-8")
    lines = content.splitlines()

    current_section = None
    section_rows = {}

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            current_section = stripped[1:-1]
            section_rows[current_section] = []
            continue
        if current_section and stripped:
            section_rows.setdefault(current_section, []).append(stripped)

    imported = {}

    # --- Settings ---
    if "SETTINGS" in section_rows:
        rows = list(csv.reader(section_rows["SETTINGS"], delimiter=";"))
        if rows and rows[0] == ["key", "value"]:
            rows = rows[1:]
        count = 0
        for row in rows:
            if len(row) >= 2:
                existing = db.query(Setting).filter(Setting.key == row[0]).first()
                if existing:
                    existing.value = row[1]
                else:
                    db.add(Setting(key=row[0], value=row[1]))
                count += 1
        db.commit()
        imported["settings"] = count

    # --- Airlines ---
    if "AIRLINES" in section_rows:
        rows = list(csv.reader(section_rows["AIRLINES"], delimiter=";"))
        if rows and rows[0][0] == "id":
            rows = rows[1:]
        count = 0
        for row in rows:
            if len(row) >= 5:
                existing = db.query(Airline).filter(Airline.name == row[1]).first()
                if existing:
                    existing.fees_fixed = float(row[2]) if row[2] else 0
                    existing.fees_percent = float(row[3]) if row[3] else 0
                    existing.enabled = row[4] == "True"
                    if len(row) >= 6:
                        existing.logo_url = row[5] or None
                else:
                    db.add(Airline(
                        name=row[1],
                        fees_fixed=float(row[2]) if row[2] else 0,
                        fees_percent=float(row[3]) if row[3] else 0,
                        enabled=row[4] == "True",
                        logo_url=row[5] if len(row) >= 6 and row[5] else None,
                    ))
                count += 1
        db.commit()
        imported["airlines"] = count

    return {"ok": True, "imported": imported}

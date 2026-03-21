import csv
import io
import json
from datetime import datetime, date as date_type
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Dict, Any
from sqlalchemy.orm import Session

from database import Setting, Search, Flight, Airline, CrawlerLog, PriceTracker, PriceHistory, get_db

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
    from email_service import send_test_email

    try:
        send_test_email()
        return {"ok": True, "message": "Test email sent successfully! Check your inbox."}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"SMTP test failed: {str(e)}")


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

    # --- Price History ---
    output.write("\n[PRICE_HISTORY]\n")
    writer.writerow(["id", "flight_id", "price", "recorded_at"])
    for ph in db.query(PriceHistory).order_by(PriceHistory.id).all():
        writer.writerow([
            ph.id, ph.flight_id, ph.price,
            ph.recorded_at.isoformat() if ph.recorded_at else "",
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

    # --- Searches ---
    if "SEARCHES" in section_rows:
        rows = list(csv.reader(section_rows["SEARCHES"], delimiter=";"))
        if rows and rows[0][0] == "id":
            rows = rows[1:]
        count = 0
        for row in rows:
            if len(row) >= 9:
                search_id = int(row[0])
                existing = db.query(Search).filter(Search.id == search_id).first()
                if not existing:
                    s = Search(
                        id=search_id,
                        origin_city=row[1],
                        destination_city=row[2],
                        date_from=date_type.fromisoformat(row[3]) if row[3] else None,
                        date_to=date_type.fromisoformat(row[4]) if row[4] else None,
                        trip_type=row[5],
                        airlines=row[6],
                        created_at=datetime.fromisoformat(row[7]) if row[7] else None,
                        is_last=row[8] == "True",
                    )
                    db.add(s)
                    count += 1
        db.commit()
        imported["searches"] = count

    # --- Flights ---
    if "FLIGHTS" in section_rows:
        rows = list(csv.reader(section_rows["FLIGHTS"], delimiter=";"))
        if rows and rows[0][0] == "id":
            rows = rows[1:]
        count = 0
        for row in rows:
            if len(row) >= 12:
                flight_id = int(row[0])
                existing = db.query(Flight).filter(Flight.id == flight_id).first()
                if not existing:
                    f = Flight(
                        id=flight_id,
                        search_id=int(row[1]),
                        airline_id=int(row[2]),
                        direction=row[3],
                        flight_date=date_type.fromisoformat(row[4]) if row[4] else None,
                        departure_time=row[5],
                        arrival_time=row[6],
                        origin_airport=row[7],
                        destination_airport=row[8],
                        price=float(row[9]),
                        currency=row[10],
                        scraped_at=datetime.fromisoformat(row[11]) if row[11] else None,
                    )
                    db.add(f)
                    count += 1
        db.commit()
        imported["flights"] = count

    # --- Price History ---
    if "PRICE_HISTORY" in section_rows:
        rows = list(csv.reader(section_rows["PRICE_HISTORY"], delimiter=";"))
        if rows and rows[0][0] == "id":
            rows = rows[1:]
        count = 0
        for row in rows:
            if len(row) >= 4:
                ph_id = int(row[0])
                existing = db.query(PriceHistory).filter(PriceHistory.id == ph_id).first()
                if not existing:
                    ph = PriceHistory(
                        id=ph_id,
                        flight_id=int(row[1]),
                        price=float(row[2]),
                        recorded_at=datetime.fromisoformat(row[3]) if row[3] else None,
                    )
                    db.add(ph)
                    count += 1
        db.commit()
        imported["price_history"] = count

    # --- Price Tracker ---
    if "PRICE_TRACKER" in section_rows:
        rows = list(csv.reader(section_rows["PRICE_TRACKER"], delimiter=";"))
        if rows and rows[0][0] == "id":
            rows = rows[1:]
        count = 0
        for row in rows:
            if len(row) >= 9:
                pt_id = int(row[0])
                existing = db.query(PriceTracker).filter(PriceTracker.id == pt_id).first()
                if not existing:
                    pt = PriceTracker(
                        id=pt_id,
                        airline_id=int(row[1]),
                        direction=row[2],
                        flight_date=date_type.fromisoformat(row[3]) if row[3] else None,
                        departure_time=row[4],
                        origin_airport=row[5],
                        destination_airport=row[6],
                        price=float(row[7]),
                        recorded_at=datetime.fromisoformat(row[8]) if row[8] else None,
                    )
                    db.add(pt)
                    count += 1
        db.commit()
        imported["price_tracker"] = count

    # --- Crawler Logs ---
    if "CRAWLER_LOGS" in section_rows:
        rows = list(csv.reader(section_rows["CRAWLER_LOGS"], delimiter=";"))
        if rows and rows[0][0] == "id":
            rows = rows[1:]
        count = 0
        for row in rows:
            if len(row) >= 7:
                log_id = int(row[0])
                existing = db.query(CrawlerLog).filter(CrawlerLog.id == log_id).first()
                if not existing:
                    log = CrawlerLog(
                        id=log_id,
                        search_id=int(row[1]) if row[1] else None,
                        triggered_by=row[2],
                        status=row[3],
                        error_msg=row[4] or None,
                        started_at=datetime.fromisoformat(row[5]) if row[5] else None,
                        ended_at=datetime.fromisoformat(row[6]) if row[6] else None,
                    )
                    db.add(log)
                    count += 1
        db.commit()
        imported["crawler_logs"] = count

    return {"ok": True, "imported": imported}


@router.post("/reset")
def reset_database(db: Session = Depends(get_db)):
    """Delete all data and reset all settings to defaults. Keep airlines."""
    import json as _json
    # Delete all transactional data
    db.query(PriceHistory).delete()
    db.query(Flight).delete()
    db.query(CrawlerLog).delete()
    db.query(PriceTracker).delete()
    db.query(Search).delete()

    # Reset all settings to defaults
    default_settings = {
        "smtp_host": "",
        "smtp_port": "587",
        "smtp_user": "",
        "smtp_password": "",
        "smtp_to": "",
        "smtp_send_enabled": "false",
        "crawler_enabled": "false",
        "crawler_interval": "60",
        "crawler_search_id": "",
        "crawler_started_at": "",
        "crawler_time": "07:00",
        "server_hostname": "192.168.1.50",
        "ideal_price": "40",
        "time_slots": _json.dumps([
            {"label": "Comfortable", "start": "10:00", "end": "18:00", "color": "green"},
            {"label": "Acceptable", "start": "06:00", "end": "10:00", "color": "orange"},
            {"label": "Difficult", "start": "00:00", "end": "06:00", "color": "red"},
            {"label": "Late", "start": "18:00", "end": "00:00", "color": "orange"},
        ]),
    }
    for key, value in default_settings.items():
        existing = db.query(Setting).filter(Setting.key == key).first()
        if existing:
            existing.value = value
        else:
            db.add(Setting(key=key, value=value))
    # Delete any settings not in defaults
    db.query(Setting).filter(~Setting.key.in_(default_settings.keys())).delete(synchronize_session=False)

    db.commit()
    return {"ok": True, "message": "Database reset complete. All settings restored to defaults. Airlines preserved."}

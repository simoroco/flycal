import json
import smtplib
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Dict, Any
from sqlalchemy.orm import Session

from database import Setting, get_db

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsUpdate(BaseModel):
    settings: Dict[str, Any]


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

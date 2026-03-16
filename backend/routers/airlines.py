import os
import shutil
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session

from database import Airline, get_db

_data_dir = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "data"))
LOGO_DIR = os.path.join(_data_dir, "logos")
os.makedirs(LOGO_DIR, exist_ok=True)

router = APIRouter(prefix="/api/airlines", tags=["airlines"])


class AirlineCreate(BaseModel):
    name: str
    fees_fixed: float = 0.0
    fees_percent: float = 0.0
    enabled: bool = True
    logo_url: Optional[str] = None


class AirlineUpdate(BaseModel):
    name: Optional[str] = None
    fees_fixed: Optional[float] = None
    fees_percent: Optional[float] = None
    enabled: Optional[bool] = None
    logo_url: Optional[str] = None


class AirlineOut(BaseModel):
    id: int
    name: str
    fees_fixed: float
    fees_percent: float
    enabled: bool
    logo_url: Optional[str] = None

    class Config:
        from_attributes = True


@router.get("", response_model=list[AirlineOut])
def list_airlines(db: Session = Depends(get_db)):
    return db.query(Airline).all()


@router.post("", response_model=AirlineOut)
def create_airline(data: AirlineCreate, db: Session = Depends(get_db)):
    existing = db.query(Airline).filter(Airline.name == data.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Airline already exists")
    airline = Airline(**data.model_dump())
    db.add(airline)
    db.commit()
    db.refresh(airline)
    return airline


@router.put("/{airline_id}", response_model=AirlineOut)
def update_airline(airline_id: int, data: AirlineUpdate, db: Session = Depends(get_db)):
    airline = db.query(Airline).filter(Airline.id == airline_id).first()
    if not airline:
        raise HTTPException(status_code=404, detail="Airline not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(airline, field, value)
    db.commit()
    db.refresh(airline)
    return airline


@router.delete("/{airline_id}")
def delete_airline(airline_id: int, db: Session = Depends(get_db)):
    airline = db.query(Airline).filter(Airline.id == airline_id).first()
    if not airline:
        raise HTTPException(status_code=404, detail="Airline not found")
    db.delete(airline)
    db.commit()
    return {"ok": True}


@router.post("/{airline_id}/logo", response_model=AirlineOut)
async def upload_logo(airline_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    airline = db.query(Airline).filter(Airline.id == airline_id).first()
    if not airline:
        raise HTTPException(status_code=404, detail="Airline not found")
    ext = os.path.splitext(file.filename or "logo.png")[1] or ".png"
    filename = f"{airline_id}_{uuid.uuid4().hex[:8]}{ext}"
    filepath = os.path.join(LOGO_DIR, filename)
    with open(filepath, "wb") as f:
        shutil.copyfileobj(file.file, f)
    airline.logo_url = f"/api/airlines/logos/{filename}"
    db.commit()
    db.refresh(airline)
    return airline

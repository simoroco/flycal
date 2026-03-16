import json
import os
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Date,
    Float,
    ForeignKey,
    Integer,
    Text,
    create_engine,
    event,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

_data_dir = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data"))
DB_PATH = os.environ.get("DB_PATH", os.path.join(_data_dir, "db.sqlite"))
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})

@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Search(Base):
    __tablename__ = "searches"
    id = Column(Integer, primary_key=True, autoincrement=True)
    origin_city = Column(Text, nullable=False)
    destination_city = Column(Text, nullable=False)
    date_from = Column(Date, nullable=False)
    date_to = Column(Date, nullable=False)
    trip_type = Column(Text, nullable=False, default="oneway")
    airlines = Column(Text, nullable=False, default="[]")
    created_at = Column(DateTime, default=datetime.utcnow)
    is_last = Column(Boolean, default=False)
    flights = relationship("Flight", back_populates="search", cascade="all, delete-orphan")
    crawler_logs = relationship("CrawlerLog", back_populates="search", cascade="all, delete-orphan")


class Airline(Base):
    __tablename__ = "airlines"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False, unique=True)
    fees_fixed = Column(Float, default=0.0)
    fees_percent = Column(Float, default=0.0)
    enabled = Column(Boolean, default=True)
    logo_url = Column(Text, nullable=True, default=None)
    flights = relationship("Flight", back_populates="airline")


class Flight(Base):
    __tablename__ = "flights"
    id = Column(Integer, primary_key=True, autoincrement=True)
    search_id = Column(Integer, ForeignKey("searches.id"), nullable=False)
    airline_id = Column(Integer, ForeignKey("airlines.id"), nullable=False)
    direction = Column(Text, nullable=False)
    flight_date = Column(Date, nullable=False)
    departure_time = Column(Text, nullable=False)
    arrival_time = Column(Text, nullable=False)
    origin_airport = Column(Text, nullable=False)
    destination_airport = Column(Text, nullable=False)
    price = Column(Float, nullable=False)
    currency = Column(Text, default="EUR")
    scraped_at = Column(DateTime, default=datetime.utcnow)
    search = relationship("Search", back_populates="flights")
    airline = relationship("Airline", back_populates="flights")
    price_history = relationship("PriceHistory", back_populates="flight", cascade="all, delete-orphan")


class PriceHistory(Base):
    __tablename__ = "price_history"
    id = Column(Integer, primary_key=True, autoincrement=True)
    flight_id = Column(Integer, ForeignKey("flights.id"), nullable=False)
    price = Column(Float, nullable=False)
    recorded_at = Column(DateTime, default=datetime.utcnow)
    flight = relationship("Flight", back_populates="price_history")


class Setting(Base):
    __tablename__ = "settings"
    key = Column(Text, primary_key=True)
    value = Column(Text)


class CrawlerLog(Base):
    __tablename__ = "crawler_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    search_id = Column(Integer, ForeignKey("searches.id"), nullable=True)
    triggered_by = Column(Text, nullable=False, default="manual")
    status = Column(Text, nullable=False, default="running")
    error_msg = Column(Text, nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    search = relationship("Search", back_populates="crawler_logs")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _migrate_db():
    """Add missing columns to existing tables."""
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Add logo_url to airlines if missing
    cursor.execute("PRAGMA table_info(airlines)")
    cols = {row[1] for row in cursor.fetchall()}
    if "logo_url" not in cols:
        cursor.execute("ALTER TABLE airlines ADD COLUMN logo_url TEXT")
        # Set default logos for known airlines
        defaults = {
            "Transavia": "https://images.kiwi.com/airlines/64/HV.png",
            "Ryanair": "https://images.kiwi.com/airlines/64/FR.png",
            "Air France": "https://images.kiwi.com/airlines/64/AF.png",
            "Air Arabia": "https://images.kiwi.com/airlines/64/3O.png",
            "Royal Air Maroc": "https://images.kiwi.com/airlines/64/AT.png",
        }
        for name, url in defaults.items():
            cursor.execute("UPDATE airlines SET logo_url = ? WHERE name = ?", (url, name))
        conn.commit()
    conn.close()


def init_db():
    Base.metadata.create_all(bind=engine)
    _migrate_db()
    db = SessionLocal()
    try:
        if db.query(Airline).count() == 0:
            default_airlines = [
                Airline(name="Transavia", fees_fixed=0.0, fees_percent=0.0, enabled=True,
                        logo_url="https://images.kiwi.com/airlines/64/HV.png"),
                Airline(name="Ryanair", fees_fixed=0.0, fees_percent=0.0, enabled=True,
                        logo_url="https://images.kiwi.com/airlines/64/FR.png"),
                Airline(name="Air France", fees_fixed=0.0, fees_percent=0.0, enabled=True,
                        logo_url="https://images.kiwi.com/airlines/64/AF.png"),
                Airline(name="Air Arabia", fees_fixed=0.0, fees_percent=0.0, enabled=True,
                        logo_url="https://images.kiwi.com/airlines/64/3O.png"),
                Airline(name="Royal Air Maroc", fees_fixed=0.0, fees_percent=0.0, enabled=True,
                        logo_url="https://images.kiwi.com/airlines/64/AT.png"),
            ]
            db.add_all(default_airlines)
            db.commit()
        else:
            existing_names = {a.name for a in db.query(Airline).all()}
            if "Royal Air Maroc" not in existing_names:
                db.add(Airline(name="Royal Air Maroc", fees_fixed=0.0, fees_percent=0.0, enabled=True))
                db.commit()

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
            "crawler_times": "07:00,22:00",
            "ideal_price": "100",
            "time_slots": json.dumps([
                {"label": "Comfortable", "start": "10:00", "end": "18:00", "color": "green"},
                {"label": "Acceptable", "start": "06:00", "end": "10:00", "color": "orange"},
                {"label": "Difficult", "start": "00:00", "end": "06:00", "color": "red"},
                {"label": "Late", "start": "18:00", "end": "00:00", "color": "orange"},
            ]),
        }
        for key, value in default_settings.items():
            existing = db.query(Setting).filter(Setting.key == key).first()
            if not existing:
                db.add(Setting(key=key, value=value))
        db.commit()
    finally:
        db.close()

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


class PriceTracker(Base):
    """Persistent price tracking across searches. Keyed by flight identity (not search-specific)."""
    __tablename__ = "price_tracker"
    id = Column(Integer, primary_key=True, autoincrement=True)
    airline_id = Column(Integer, ForeignKey("airlines.id"), nullable=False)
    direction = Column(Text, nullable=False)
    flight_date = Column(Date, nullable=False)
    departure_time = Column(Text, nullable=False)
    origin_airport = Column(Text, nullable=False)
    destination_airport = Column(Text, nullable=False)
    price = Column(Float, nullable=False)
    recorded_at = Column(DateTime, default=datetime.utcnow)


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
            "American Airlines": "https://images.kiwi.com/airlines/64/AA.png",
            "Emirates": "https://images.kiwi.com/airlines/64/EK.png",
            "Qatar Airways": "https://images.kiwi.com/airlines/64/QR.png",
            "Lufthansa": "https://images.kiwi.com/airlines/64/LH.png",
            "Singapore Airlines": "https://images.kiwi.com/airlines/64/SQ.png",
            "British Airways": "https://images.kiwi.com/airlines/64/BA.png",
            "Air China": "https://images.kiwi.com/airlines/64/CA.png",
            "Turkish Airlines": "https://images.kiwi.com/airlines/64/TK.png",
            "EasyJet": "https://images.kiwi.com/airlines/64/U2.png",
            "Vueling": "https://images.kiwi.com/airlines/64/VY.png",
            "Finnair": "https://images.kiwi.com/airlines/64/AY.png",
            "Air Caraibes": "https://images.kiwi.com/airlines/64/TX.png",
            "TAP Air Portugal": "https://images.kiwi.com/airlines/64/TP.png",
            "Iberia": "https://images.kiwi.com/airlines/64/IB.png",
            "Corsair": "https://images.kiwi.com/airlines/64/SS.png",
            "ITA Airways": "https://images.kiwi.com/airlines/64/AZ.png",
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
                Airline(name="Air France", fees_fixed=0.0, fees_percent=0.0, enabled=False,
                        logo_url="https://images.kiwi.com/airlines/64/AF.png"),
                Airline(name="Air Arabia", fees_fixed=0.0, fees_percent=0.0, enabled=True,
                        logo_url="https://images.kiwi.com/airlines/64/3O.png"),
                Airline(name="Royal Air Maroc", fees_fixed=0.0, fees_percent=0.0, enabled=False,
                        logo_url="https://images.kiwi.com/airlines/64/AT.png"),
                Airline(name="American Airlines", fees_fixed=0.0, fees_percent=0.0, enabled=False,
                        logo_url="https://images.kiwi.com/airlines/64/AA.png"),
                Airline(name="Emirates", fees_fixed=0.0, fees_percent=0.0, enabled=False,
                        logo_url="https://images.kiwi.com/airlines/64/EK.png"),
                Airline(name="Qatar Airways", fees_fixed=0.0, fees_percent=0.0, enabled=False,
                        logo_url="https://images.kiwi.com/airlines/64/QR.png"),
                Airline(name="Lufthansa", fees_fixed=0.0, fees_percent=0.0, enabled=False,
                        logo_url="https://images.kiwi.com/airlines/64/LH.png"),
                Airline(name="Singapore Airlines", fees_fixed=0.0, fees_percent=0.0, enabled=False,
                        logo_url="https://images.kiwi.com/airlines/64/SQ.png"),
                Airline(name="British Airways", fees_fixed=0.0, fees_percent=0.0, enabled=False,
                        logo_url="https://images.kiwi.com/airlines/64/BA.png"),
                Airline(name="Air China", fees_fixed=0.0, fees_percent=0.0, enabled=False,
                        logo_url="https://images.kiwi.com/airlines/64/CA.png"),
                Airline(name="Turkish Airlines", fees_fixed=0.0, fees_percent=0.0, enabled=False,
                        logo_url="https://images.kiwi.com/airlines/64/TK.png"),
                Airline(name="EasyJet", fees_fixed=0.0, fees_percent=0.0, enabled=False,
                        logo_url="https://images.kiwi.com/airlines/64/U2.png"),
                Airline(name="Vueling", fees_fixed=0.0, fees_percent=0.0, enabled=False,
                        logo_url="https://images.kiwi.com/airlines/64/VY.png"),
                Airline(name="Finnair", fees_fixed=0.0, fees_percent=0.0, enabled=False,
                        logo_url="https://images.kiwi.com/airlines/64/AY.png"),
                Airline(name="Air Caraibes", fees_fixed=0.0, fees_percent=0.0, enabled=False,
                        logo_url="https://images.kiwi.com/airlines/64/TX.png"),
                Airline(name="TAP Air Portugal", fees_fixed=0.0, fees_percent=0.0, enabled=False,
                        logo_url="https://images.kiwi.com/airlines/64/TP.png"),
                Airline(name="Iberia", fees_fixed=0.0, fees_percent=0.0, enabled=False,
                        logo_url="https://images.kiwi.com/airlines/64/IB.png"),
                Airline(name="Corsair", fees_fixed=0.0, fees_percent=0.0, enabled=False,
                        logo_url="https://images.kiwi.com/airlines/64/SS.png"),
                Airline(name="ITA Airways", fees_fixed=0.0, fees_percent=0.0, enabled=False,
                        logo_url="https://images.kiwi.com/airlines/64/AZ.png"),
            ]
            db.add_all(default_airlines)
            db.commit()
        else:
            existing_names = {a.name for a in db.query(Airline).all()}
            new_airlines = {
                "Royal Air Maroc": ("AT", False),
                "American Airlines": ("AA", False),
                "Emirates": ("EK", False),
                "Qatar Airways": ("QR", False),
                "Lufthansa": ("LH", False),
                "Singapore Airlines": ("SQ", False),
                "British Airways": ("BA", False),
                "Air China": ("CA", False),
                "Turkish Airlines": ("TK", False),
                "EasyJet": ("U2", False),
                "Vueling": ("VY", False),
                "Finnair": ("AY", False),
                "Air Caraibes": ("TX", False),
                "TAP Air Portugal": ("TP", False),
                "Iberia": ("IB", False),
                "Corsair": ("SS", False),
                "ITA Airways": ("AZ", False),
            }
            for name, (iata, enabled) in new_airlines.items():
                if name not in existing_names:
                    db.add(Airline(
                        name=name, fees_fixed=0.0, fees_percent=0.0, enabled=enabled,
                        logo_url=f"https://images.kiwi.com/airlines/64/{iata}.png",
                    ))
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
            "crawler_time": "07:00",
            "server_hostname": "192.168.1.50",
            "ideal_price": "40",
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

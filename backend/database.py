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
    cursor.execute("PRAGMA journal_size_limit=67108864")  # 64MB max WAL size
    cursor.execute("PRAGMA cache_size=-64000")  # 64MB cache
    cursor.execute("PRAGMA synchronous=NORMAL")  # Faster writes, still safe with WAL
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
    crawler_id = Column(Integer, nullable=True)  # Don't use FK to avoid migration complexity
    search = relationship("Search", back_populates="crawler_logs")


class ScheduledCrawler(Base):
    __tablename__ = "scheduled_crawlers"
    id = Column(Integer, primary_key=True, autoincrement=True)
    search_id = Column(Integer, ForeignKey("searches.id"), nullable=False)
    schedule_time = Column(Text, nullable=False)  # "04:00","07:00","14:00","18:00","23:00"
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    search = relationship("Search")


class TrackedFlight(Base):
    __tablename__ = "tracked_flights"
    __table_args__ = (
        # Same identity key as PriceTracker
        # Prevents duplicate tracks for the same flight
        {"sqlite_autoincrement": True},
    )
    id = Column("pinned_flight_id", Integer, primary_key=True, autoincrement=True)
    airline_id = Column(Integer, ForeignKey("airlines.id"), nullable=False)
    direction = Column(Text, nullable=False)
    flight_date = Column(Date, nullable=False)
    departure_time = Column(Text, nullable=False)
    origin_airport = Column(Text, nullable=False)
    destination_airport = Column(Text, nullable=False)
    tracked_at = Column("pinned_at", DateTime, default=datetime.utcnow)
    airline = relationship("Airline")
    alerts = relationship("PriceAlert", back_populates="tracked_flight", cascade="all, delete-orphan")


class PriceAlert(Base):
    __tablename__ = "track_alerts"
    id = Column(Integer, primary_key=True, autoincrement=True)
    pinned_flight_id = Column(Integer, ForeignKey("tracked_flights.pinned_flight_id"), nullable=False)
    alert_type = Column(Text, nullable=False)  # "threshold", "variation", "trend_start"
    operator = Column(Text, nullable=True)      # "lt"/"gt" for threshold; "increase"/"decrease" for trend
    value = Column(Float, nullable=True)        # absolute price or percentage
    value_is_percent = Column(Boolean, default=False)
    logic_group = Column(Integer, default=0)    # AND intra-group, OR inter-groups
    cooldown = Column(Text, default="every_scan")  # once_only, every_scan, once_per_day, once_per_week
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    tracked_flight = relationship("TrackedFlight", back_populates="alerts")
    history = relationship("AlertHistory", back_populates="alert", cascade="all, delete-orphan")


class AlertHistory(Base):
    __tablename__ = "track_alert_history"
    id = Column(Integer, primary_key=True, autoincrement=True)
    price_alert_id = Column(Integer, ForeignKey("track_alerts.id"), nullable=False)
    triggered_at = Column(DateTime, default=datetime.utcnow)
    price_at_trigger = Column(Float, nullable=False)
    message = Column(Text, nullable=True)
    alert = relationship("PriceAlert", back_populates="history")


class ActivityLog(Base):
    __tablename__ = "activity_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    category = Column(Text, nullable=False)   # "track", "alert", "crawler", "email", "system"
    action = Column(Text, nullable=False)      # "created", "deleted", "enabled", "disabled", "sent", "triggered", "error"
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


def log_activity(db, category: str, action: str, message: str):
    db.add(ActivityLog(category=category, action=action, message=message))
    db.commit()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _migrate_db():
    """Add missing columns to existing tables and rename tables."""
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Migrate pinned_flights -> tracked_flights (copy data if both exist, drop old)
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pinned_flights'")
    old_pf = cursor.fetchone()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tracked_flights'")
    new_tf = cursor.fetchone()
    if old_pf and new_tf:
        # Both exist (create_all made new, old still has data) — copy data and drop old
        cursor.execute("INSERT OR IGNORE INTO tracked_flights SELECT * FROM pinned_flights")
        cursor.execute("DROP TABLE pinned_flights")
        conn.commit()
    elif old_pf and not new_tf:
        cursor.execute("ALTER TABLE pinned_flights RENAME TO tracked_flights")
        conn.commit()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='price_alerts'")
    old_pa = cursor.fetchone()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='track_alerts'")
    new_ta = cursor.fetchone()
    if old_pa and new_ta:
        cursor.execute("INSERT OR IGNORE INTO track_alerts SELECT * FROM price_alerts")
        cursor.execute("DROP TABLE price_alerts")
        conn.commit()
    elif old_pa and not new_ta:
        cursor.execute("ALTER TABLE price_alerts RENAME TO track_alerts")
        conn.commit()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='alert_history'")
    old_ah = cursor.fetchone()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='track_alert_history'")
    new_tah = cursor.fetchone()
    if old_ah and new_tah:
        cursor.execute("INSERT OR IGNORE INTO track_alert_history SELECT * FROM alert_history")
        cursor.execute("DROP TABLE alert_history")
        conn.commit()
    elif old_ah and not new_tah:
        cursor.execute("ALTER TABLE alert_history RENAME TO track_alert_history")
        conn.commit()

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

    # Add crawler_id to crawler_logs if missing
    cursor.execute("PRAGMA table_info(crawler_logs)")
    log_cols = {row[1] for row in cursor.fetchall()}
    if "crawler_id" not in log_cols:
        cursor.execute("ALTER TABLE crawler_logs ADD COLUMN crawler_id INTEGER")
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

        # Mark any stale "running" logs as "error" (server restart mid-scan)
        stale = db.query(CrawlerLog).filter(CrawlerLog.status == "running").all()
        for log in stale:
            log.status = "error"
            log.error_msg = "Interrupted (server restart)"
            log.ended_at = datetime.utcnow()
        if stale:
            db.commit()
    finally:
        db.close()

import os
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

_default_db = os.path.join(os.path.dirname(os.path.abspath(__file__)), "predictions.db")
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{_default_db}",
)

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class Scan(Base):
    __tablename__ = "scans"

    id = Column(Integer, primary_key=True)
    scanned_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    opportunities_found = Column(Integer, default=0)


class Opportunity(Base):
    __tablename__ = "opportunities"

    id = Column(Integer, primary_key=True)
    scan_id = Column(Integer, nullable=True)
    found_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    ticker = Column(String, index=True)
    event_ticker = Column(String)
    series_ticker = Column(String)
    title = Column(Text)
    yes_sub_title = Column(Text)
    yes_bid = Column(Integer)
    yes_ask = Column(Integer)
    spread = Column(Integer)
    volume = Column(Integer)
    close_time = Column(String)


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True)
    placed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    ticker = Column(String, index=True)
    event_ticker = Column(String)
    title = Column(Text)
    side = Column(String)  # yes/no
    action = Column(String)  # buy/sell
    count = Column(Integer)
    yes_price = Column(Integer)  # cents
    cost_cents = Column(Integer)
    potential_profit_cents = Column(Integer)
    status = Column(String, default="placed")  # placed, filled, settled_win, settled_loss
    settled_at = Column(DateTime, nullable=True)
    pnl_cents = Column(Integer, nullable=True)
    dry_run = Column(Boolean, default=True)
    order_id = Column(String, nullable=True)
    error = Column(Text, nullable=True)


class StretchOpportunity(Base):
    """Near-miss markets that didn't quite meet our filters.

    Tracked to see if loosening risk params would be profitable.
    """

    __tablename__ = "stretch_opportunities"

    id = Column(Integer, primary_key=True)
    found_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    ticker = Column(String, index=True)
    event_ticker = Column(String)
    series_ticker = Column(String)
    title = Column(Text)
    yes_sub_title = Column(Text)
    yes_ask = Column(Integer)
    volume = Column(Integer)
    sport_path = Column(String)
    score_lead = Column(Integer)
    min_score_lead = Column(Integer)
    espn_period = Column(Integer)
    espn_clock = Column(String)
    # Why it was a stretch (which filter it missed)
    reason = Column(String)  # "price", "score_lead", "time"
    # Which what-if strategy set this belongs to
    strategy_set = Column(String, default="default", index=True)
    # Settlement tracking
    status = Column(String, default="open")  # open, settled_win, settled_loss
    pnl_cents = Column(Integer, nullable=True)  # hypothetical P&L


class BalanceSnapshot(Base):
    __tablename__ = "balance_snapshots"

    id = Column(Integer, primary_key=True)
    recorded_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    balance_cents = Column(Integer)
    portfolio_value_cents = Column(Integer, nullable=True)


class ConfigEntry(Base):
    """Key-value config store for runtime-tunable parameters."""

    __tablename__ = "config"

    key = Column(String, primary_key=True)
    value = Column(Text, nullable=False)


def init_db():
    Base.metadata.create_all(engine)
    # Add columns that may not exist in older DBs
    _migrate_add_columns()


def _migrate_add_columns():
    """Add columns to existing tables if they don't exist."""
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    if "stretch_opportunities" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("stretch_opportunities")}
        if "strategy_set" not in cols:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE stretch_opportunities "
                        "ADD COLUMN strategy_set VARCHAR DEFAULT 'default'"
                    )
                )


def get_session():
    return SessionLocal()


# --- Runtime config helpers ---

# Defaults used when no DB override exists
_CONFIG_DEFAULTS: dict[str, str] = {
    "min_yes_price": "92",
    "max_bet_cents": "500",
    "max_positions": "20",
    "min_volume": "50",
    "stretch_price_min": "85",
    # Per-sport score leads: sport_path -> min lead
    "lead:basketball/nba": "8",
    "lead:basketball/mens-college-basketball": "8",
    "lead:hockey/nhl": "2",
    "lead:football/nfl": "10",
    "lead:football/college-football": "10",
    "lead:baseball/mlb": "3",
    "lead:soccer/eng.1": "2",
    "lead:soccer/esp.1": "2",
    "lead:soccer/usa.1": "2",
    "lead:mma/ufc": "0",
    # Per-sport final minutes (seconds): clock <= X for countdown, clock >= X for count-up
    "final_seconds:basketball/nba": "300",
    "final_seconds:basketball/mens-college-basketball": "300",
    "final_seconds:hockey/nhl": "300",
    "final_seconds:football/nfl": "300",
    "final_seconds:football/college-football": "300",
    "final_seconds:soccer/eng.1": "4800",
    "final_seconds:soccer/esp.1": "4800",
    "final_seconds:soccer/usa.1": "4800",
    "final_seconds:mma/ufc": "300",
}


def get_config(key: str) -> str:
    """Get a config value from DB, falling back to defaults."""
    session = get_session()
    entry = session.query(ConfigEntry).filter_by(key=key).first()
    session.close()
    if entry:
        return entry.value
    return _CONFIG_DEFAULTS.get(key, "")


def get_config_int(key: str) -> int:
    return int(get_config(key) or "0")


def set_config(key: str, value: str):
    """Set a config value in the DB."""
    session = get_session()
    entry = session.query(ConfigEntry).filter_by(key=key).first()
    if entry:
        entry.value = value
    else:
        session.add(ConfigEntry(key=key, value=value))
    session.commit()
    session.close()


def get_all_config() -> dict[str, str]:
    """Get all config as a dict (defaults merged with DB overrides)."""
    result = dict(_CONFIG_DEFAULTS)
    session = get_session()
    for entry in session.query(ConfigEntry).all():
        result[entry.key] = entry.value
    session.close()
    return result

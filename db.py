import os
from datetime import datetime, timezone
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Boolean, DateTime, Text
)
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://predictions:predictions@localhost:5432/predictions",
)

engine = create_engine(DATABASE_URL)
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


class BalanceSnapshot(Base):
    __tablename__ = "balance_snapshots"

    id = Column(Integer, primary_key=True)
    recorded_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    balance_cents = Column(Integer)
    portfolio_value_cents = Column(Integer, nullable=True)


def init_db():
    Base.metadata.create_all(engine)


def get_session():
    return SessionLocal()

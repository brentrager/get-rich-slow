"""FastAPI backend serving dashboard data from Postgres."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, desc

from db import init_db, get_session, Scan, Opportunity, Trade, BalanceSnapshot


# --- Pydantic response models ---

class StatsResponse(BaseModel):
    total_trades: int
    live_trades: int
    dry_run_trades: int
    total_cost_cents: int
    total_potential_profit_cents: int
    realized_pnl_cents: int
    wins: int
    losses: int
    win_rate: float
    total_scans: int
    total_opportunities: int
    balance_cents: int
    portfolio_value_cents: int


class TradeResponse(BaseModel):
    id: int
    placed_at: Optional[datetime] = None
    ticker: str
    event_ticker: Optional[str] = None
    title: Optional[str] = None
    side: str
    count: int
    yes_price: int
    cost_cents: int
    potential_profit_cents: int
    status: str
    pnl_cents: Optional[int] = None
    dry_run: bool
    error: Optional[str] = None


class TradesListResponse(BaseModel):
    trades: list[TradeResponse]


class OpportunityResponse(BaseModel):
    id: int
    found_at: Optional[datetime] = None
    ticker: str
    title: Optional[str] = None
    yes_sub_title: Optional[str] = None
    yes_bid: int
    yes_ask: int
    spread: int
    volume: int
    series_ticker: Optional[str] = None


class OpportunitiesListResponse(BaseModel):
    opportunities: list[OpportunityResponse]


class BalanceSnapshotResponse(BaseModel):
    recorded_at: Optional[datetime] = None
    balance_cents: int
    portfolio_value_cents: Optional[int] = None


class BalanceHistoryResponse(BaseModel):
    snapshots: list[BalanceSnapshotResponse]


class ScanResponse(BaseModel):
    id: int
    scanned_at: Optional[datetime] = None
    opportunities_found: int


class ScansListResponse(BaseModel):
    scans: list[ScanResponse]


# --- App ---

app = FastAPI(title="Predictions Dashboard API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3777"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    init_db()


@app.get("/api/stats", response_model=StatsResponse)
def get_stats():
    session = get_session()

    total_trades = session.query(Trade).count()
    live_trades = session.query(Trade).filter(Trade.dry_run == False).count()
    dry_trades = session.query(Trade).filter(Trade.dry_run == True).count()

    total_cost = session.query(func.sum(Trade.cost_cents)).filter(Trade.dry_run == False).scalar() or 0
    total_potential_profit = session.query(func.sum(Trade.potential_profit_cents)).filter(Trade.dry_run == False).scalar() or 0
    total_pnl = session.query(func.sum(Trade.pnl_cents)).filter(Trade.pnl_cents.isnot(None)).scalar() or 0

    wins = session.query(Trade).filter(Trade.status == "settled_win").count()
    losses = session.query(Trade).filter(Trade.status == "settled_loss").count()
    settled = wins + losses
    win_rate = (wins / settled * 100) if settled > 0 else 0

    total_scans = session.query(Scan).count()
    total_opportunities = session.query(Opportunity).count()

    latest_balance = session.query(BalanceSnapshot).order_by(desc(BalanceSnapshot.recorded_at)).first()

    session.close()

    return StatsResponse(
        total_trades=total_trades,
        live_trades=live_trades,
        dry_run_trades=dry_trades,
        total_cost_cents=total_cost,
        total_potential_profit_cents=total_potential_profit,
        realized_pnl_cents=total_pnl,
        wins=wins,
        losses=losses,
        win_rate=round(win_rate, 1),
        total_scans=total_scans,
        total_opportunities=total_opportunities,
        balance_cents=latest_balance.balance_cents if latest_balance else 0,
        portfolio_value_cents=latest_balance.portfolio_value_cents if latest_balance else 0,
    )


@app.get("/api/trades", response_model=TradesListResponse)
def get_trades(limit: int = 50, offset: int = 0):
    session = get_session()
    trades = (
        session.query(Trade)
        .order_by(desc(Trade.placed_at))
        .offset(offset)
        .limit(limit)
        .all()
    )
    result = [
        TradeResponse(
            id=t.id,
            placed_at=t.placed_at,
            ticker=t.ticker,
            event_ticker=t.event_ticker,
            title=t.title,
            side=t.side,
            count=t.count,
            yes_price=t.yes_price,
            cost_cents=t.cost_cents,
            potential_profit_cents=t.potential_profit_cents,
            status=t.status,
            pnl_cents=t.pnl_cents,
            dry_run=t.dry_run,
            error=t.error,
        )
        for t in trades
    ]
    session.close()
    return TradesListResponse(trades=result)


@app.get("/api/opportunities", response_model=OpportunitiesListResponse)
def get_opportunities(limit: int = 50, offset: int = 0):
    session = get_session()
    opps = (
        session.query(Opportunity)
        .order_by(desc(Opportunity.found_at))
        .offset(offset)
        .limit(limit)
        .all()
    )
    result = [
        OpportunityResponse(
            id=o.id,
            found_at=o.found_at,
            ticker=o.ticker,
            title=o.title,
            yes_sub_title=o.yes_sub_title,
            yes_bid=o.yes_bid,
            yes_ask=o.yes_ask,
            spread=o.spread,
            volume=o.volume,
            series_ticker=o.series_ticker,
        )
        for o in opps
    ]
    session.close()
    return OpportunitiesListResponse(opportunities=result)


@app.get("/api/balance-history", response_model=BalanceHistoryResponse)
def get_balance_history(limit: int = 200):
    session = get_session()
    snapshots = (
        session.query(BalanceSnapshot)
        .order_by(BalanceSnapshot.recorded_at)
        .limit(limit)
        .all()
    )
    result = [
        BalanceSnapshotResponse(
            recorded_at=s.recorded_at,
            balance_cents=s.balance_cents,
            portfolio_value_cents=s.portfolio_value_cents,
        )
        for s in snapshots
    ]
    session.close()
    return BalanceHistoryResponse(snapshots=result)


@app.get("/api/scans", response_model=ScansListResponse)
def get_scans(limit: int = 50):
    session = get_session()
    scans = (
        session.query(Scan)
        .order_by(desc(Scan.scanned_at))
        .limit(limit)
        .all()
    )
    result = [
        ScanResponse(
            id=s.id,
            scanned_at=s.scanned_at,
            opportunities_found=s.opportunities_found,
        )
        for s in scans
    ]
    session.close()
    return ScansListResponse(scans=result)

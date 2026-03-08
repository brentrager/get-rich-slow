"""FastAPI backend serving dashboard data and live game tracking."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import desc, func

from db import (
    BalanceSnapshot,
    Opportunity,
    Scan,
    StretchOpportunity,
    Trade,
    get_all_config,
    get_session,
    init_db,
    set_config,
)
from espn import KALSHI_TO_ESPN, SPORT_FINAL_PERIOD, get_scoreboard, match_kalshi_to_espn
from kalshi_client import KalshiClient
from scanner import MIN_SCORE_LEAD

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
    open_positions: int
    open_cost_cents: int
    open_potential_profit_cents: int


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


class StrategySetStats(BaseModel):
    label: str
    total: int
    wins: int
    losses: int
    open: int
    win_rate: float
    hypothetical_pnl_cents: int
    by_reason: dict[str, dict]


class StretchStatsResponse(BaseModel):
    total: int
    wins: int
    losses: int
    open: int
    win_rate: float
    hypothetical_pnl_cents: int
    by_reason: dict[str, dict]
    strategies: dict[str, StrategySetStats]


# --- App ---

log = logging.getLogger(__name__)
_kalshi_client: KalshiClient | None = None


async def _run_scanner_loop():
    """Run the scanner in the background as a native async task."""
    from scanner import run_scanner

    min_price = int(os.getenv("MIN_YES_PRICE", "88"))
    max_bet = int(os.getenv("MAX_BET_AMOUNT_CENTS", "500"))
    interval = int(os.getenv("POLL_INTERVAL_SECONDS", "30"))
    dry = os.getenv("DRY_RUN", "true").lower() == "true"

    log.info(
        f"Starting scanner: min_price={min_price}c, "
        f"max_bet={max_bet}c, interval={interval}s, dry_run={dry}"
    )
    await run_scanner(
        min_yes_price=min_price,
        max_bet_cents=max_bet,
        poll_interval=interval,
        dry_run=dry,
    )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _kalshi_client
    init_db()

    if os.getenv("KALSHI_API_KEY"):
        key_id = os.environ["KALSHI_API_KEY"]
        key_pem = os.environ.get("KALSHI_PRIVATE_KEY")
        if key_pem:
            _kalshi_client = KalshiClient.from_key_string(key_id, key_pem)
        else:
            key_path = os.environ.get("KALSHI_PRIVATE_KEY_PATH", "")
            _kalshi_client = KalshiClient.from_key_file(key_id, key_path)

        asyncio.create_task(_run_scanner_loop())
    yield


app = FastAPI(title="Predictions Dashboard API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,  # type: ignore[arg-type]  # starlette typing issue
    allow_origins=[
        "https://getrich.rager.tech",
        "http://localhost:3777",
        "http://localhost:3000",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def health():
    return {"status": "ok"}


@app.get("/api/stats", response_model=StatsResponse)
def get_stats():
    session = get_session()

    total_trades = session.query(Trade).count()
    live_trades = session.query(Trade).filter(Trade.dry_run == False).count()
    dry_trades = session.query(Trade).filter(Trade.dry_run == True).count()

    total_cost = (
        session.query(func.sum(Trade.cost_cents)).filter(Trade.dry_run == False).scalar() or 0
    )
    total_potential_profit = (
        session.query(func.sum(Trade.potential_profit_cents))
        .filter(Trade.dry_run == False)
        .scalar()
        or 0
    )
    total_pnl = (
        session.query(func.sum(Trade.pnl_cents)).filter(Trade.pnl_cents.isnot(None)).scalar() or 0
    )

    wins = session.query(Trade).filter(Trade.status == "settled_win").count()
    losses = session.query(Trade).filter(Trade.status == "settled_loss").count()
    settled = wins + losses
    win_rate = (wins / settled * 100) if settled > 0 else 0

    total_scans = session.query(Scan).count()
    total_opportunities = session.query(func.count(func.distinct(Opportunity.ticker))).scalar() or 0

    latest_balance = (
        session.query(BalanceSnapshot).order_by(desc(BalanceSnapshot.recorded_at)).first()
    )

    # Open positions (active bets on the line)
    open_trades = (
        session.query(Trade)
        .filter(Trade.status.in_(("placed", "filled")), Trade.dry_run == False)
        .all()
    )
    open_positions = len(open_trades)
    open_cost = sum(t.cost_cents for t in open_trades)
    open_potential = sum(t.potential_profit_cents for t in open_trades)

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
        open_positions=open_positions,
        open_cost_cents=open_cost,
        open_potential_profit_cents=open_potential,
    )


@app.get("/api/trades", response_model=TradesListResponse)
def get_trades(limit: int = 50, offset: int = 0):
    session = get_session()
    trades = session.query(Trade).order_by(desc(Trade.placed_at)).offset(offset).limit(limit).all()
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
def get_balance_history(limit: int = 500):
    session = get_session()
    # Get the most recent snapshots (descending), then reverse for chronological order
    snapshots = (
        session.query(BalanceSnapshot)
        .order_by(desc(BalanceSnapshot.recorded_at))
        .limit(limit)
        .all()
    )
    snapshots.reverse()

    # Downsample: keep first, last, and any where balance/portfolio changed
    if len(snapshots) > 2:
        filtered = [snapshots[0]]
        for s in snapshots[1:-1]:
            prev = filtered[-1]
            if (
                s.balance_cents != prev.balance_cents
                or s.portfolio_value_cents != prev.portfolio_value_cents
            ):
                filtered.append(s)
        filtered.append(snapshots[-1])
        snapshots = filtered

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
    scans = session.query(Scan).order_by(desc(Scan.scanned_at)).limit(limit).all()
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


async def _get_live_games() -> list[dict]:
    """Fetch all live games across all sports from ESPN, enriched with Kalshi prices."""
    all_games = []

    # Fetch Kalshi markets for all sports series in parallel
    kalshi_markets: dict[str, list[dict]] = {}
    if _kalshi_client:
        for series in KALSHI_TO_ESPN:
            try:
                data = await _kalshi_client.get_events(
                    status="open",
                    series_ticker=series,
                    with_nested_markets=True,
                )
                kalshi_markets[series] = data.get("events", [])
            except Exception:
                pass

    for series, sport_path in KALSHI_TO_ESPN.items():
        games = await get_scoreboard(sport_path)
        for g in games:
            # Only show live games and pre-game (skip post/settled)
            # Skip "pre" games — they're scheduled future games, not actionable
            if g.state != "in":
                continue

            # Check game status relative to our betting criteria
            min_lead = MIN_SCORE_LEAD.get(sport_path, 5)
            meets_score_lead = g.score_diff >= min_lead
            is_target = g.is_in_final_minutes and meets_score_lead
            # "watching" = approaching criteria (has one but not both conditions)
            is_watching = (
                not is_target
                and g.state == "in"
                and (g.is_in_final_minutes or meets_score_lead or g.is_final_period)
            )

            # Check if we have an active trade on this event
            has_bet = False
            session = get_session()
            bet_count = (
                session.query(Trade)
                .filter(
                    Trade.event_ticker.like(f"{series}%"),
                    Trade.status.in_(("placed", "filled")),
                )
                .all()
            )
            # Match by team names in the event ticker
            for t in bet_count:
                if (
                    g.home_team.upper() in (t.event_ticker or "").upper()
                    or g.away_team.upper() in (t.event_ticker or "").upper()
                ):
                    has_bet = True
                    break
            session.close()

            game_data: dict = {
                "espn_id": g.espn_id,
                "sport": sport_path,
                "series": series,
                "home_team": g.home_team,
                "away_team": g.away_team,
                "home_score": g.home_score,
                "away_score": g.away_score,
                "period": g.period,
                "display_clock": g.display_clock,
                "clock_seconds": g.clock_seconds,
                "state": g.state,
                "is_final_minutes": g.is_in_final_minutes,
                "is_target": is_target,
                "is_watching": is_watching,
                "has_bet": has_bet,
                "score_diff": g.score_diff,
                "min_score_lead": min_lead,
                "final_period": g.final_period,
                "kalshi_markets": [],
            }

            # Match Kalshi markets to this ESPN game
            for event in kalshi_markets.get(series, []):
                title = event.get("title", "")
                for market in event.get("markets", []):
                    ticker = market.get("ticker", "")
                    if market.get("status") not in ("active", "open"):
                        continue
                    matched = match_kalshi_to_espn(ticker, title, [g])
                    if matched:
                        # Determine which ESPN team this market is for
                        kalshi_code = ticker.split("-")[-1].upper() if "-" in ticker else ""
                        from espn import _espn_to_kalshi_codes

                        espn_team = ""
                        for team in (g.home_team, g.away_team):
                            if kalshi_code in [c.upper() for c in _espn_to_kalshi_codes(team)]:
                                espn_team = team
                                break
                        game_data["kalshi_markets"].append(
                            {
                                "ticker": ticker,
                                "team": espn_team,
                                "yes_sub_title": market.get("yes_sub_title", ""),
                                "yes_bid": market.get("yes_bid", 0),
                                "yes_ask": market.get("yes_ask", 0),
                                "volume": market.get("volume", 0),
                            }
                        )

            all_games.append(game_data)
    return all_games


@app.get("/api/live-games")
async def get_live_games():
    return {"games": await _get_live_games()}


def _compute_stretch_stats(stretches: list) -> dict:
    """Compute stats for a list of stretch opportunities."""
    total = len(stretches)
    wins = sum(1 for s in stretches if s.status == "settled_win")
    losses = sum(1 for s in stretches if s.status == "settled_loss")
    open_count = sum(1 for s in stretches if s.status == "open")
    settled = wins + losses
    win_rate = (wins / settled * 100) if settled > 0 else 0
    hyp_pnl = sum(s.pnl_cents or 0 for s in stretches)

    by_reason: dict[str, dict] = {}
    for s in stretches:
        for reason in (s.reason or "unknown").split(","):
            reason = reason.strip()
            if reason not in by_reason:
                by_reason[reason] = {"total": 0, "wins": 0, "losses": 0, "pnl_cents": 0}
            by_reason[reason]["total"] += 1
            if s.status == "settled_win":
                by_reason[reason]["wins"] += 1
            elif s.status == "settled_loss":
                by_reason[reason]["losses"] += 1
            by_reason[reason]["pnl_cents"] += s.pnl_cents or 0

    return {
        "total": total,
        "wins": wins,
        "losses": losses,
        "open": open_count,
        "win_rate": round(win_rate, 1),
        "hypothetical_pnl_cents": hyp_pnl,
        "by_reason": by_reason,
    }


@app.get("/api/stretch-stats", response_model=StretchStatsResponse)
def get_stretch_stats():
    from scanner import WHAT_IF_STRATEGIES

    session = get_session()
    all_stretches = session.query(StretchOpportunity).all()

    # Overall stats (all strategy sets combined)
    overall = _compute_stretch_stats(all_stretches)

    # Per-strategy stats
    by_strategy: dict[str, list] = {}
    for s in all_stretches:
        strat = s.strategy_set or "default"
        by_strategy.setdefault(strat, []).append(s)

    strategies = {}
    # Always include all defined strategies even if empty
    for name, cfg in WHAT_IF_STRATEGIES.items():
        strat_stretches = by_strategy.get(name, [])
        stats = _compute_stretch_stats(strat_stretches)
        strategies[name] = StrategySetStats(
            label=str(cfg["label"]),
            **stats,
        )

    # Include "default" (the original stretch set) if it has data
    if "default" in by_strategy:
        stats = _compute_stretch_stats(by_strategy["default"])
        strategies["default"] = StrategySetStats(
            label="Default (near-miss)",
            **stats,
        )

    session.close()
    return StretchStatsResponse(
        **overall,
        strategies=strategies,
    )


SPORT_DISPLAY_NAMES = {
    "basketball/nba": "NBA",
    "basketball/mens-college-basketball": "NCAAMB",
    "hockey/nhl": "NHL",
    "football/nfl": "NFL",
    "football/college-football": "NCAAFB",
    "baseball/mlb": "MLB",
    "soccer/eng.1": "EPL",
    "soccer/esp.1": "La Liga",
    "soccer/usa.1": "MLS",
    "mma/ufc": "UFC",
}

# Clock direction per sport: "down" = countdown, "up" = counts up, "none" = no clock
SPORT_CLOCK_DIR = {
    "basketball/nba": "down",
    "basketball/mens-college-basketball": "down",
    "hockey/nhl": "down",
    "football/nfl": "down",
    "football/college-football": "down",
    "baseball/mlb": "none",
    "soccer/eng.1": "up",
    "soccer/esp.1": "up",
    "soccer/usa.1": "up",
    "mma/ufc": "down",
}


def _check_token(authorization: str | None):
    """Verify Bearer token for mutable endpoints."""
    expected = os.getenv("API_TOKEN", "")
    if not expected:
        raise HTTPException(403, "API_TOKEN not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing Bearer token")
    if authorization.removeprefix("Bearer ") != expected:
        raise HTTPException(401, "Invalid token")


def _format_final_minutes(clock_dir: str, secs: int) -> str:
    if clock_dir == "none":
        return "final period"
    if clock_dir == "up":
        return f"{secs // 60}th minute"
    mins = secs // 60
    remainder = secs % 60
    return f"{mins}:{remainder:02d} remaining"


@app.get("/api/config")
def get_config_endpoint():
    cfg = get_all_config()
    dry_run = os.getenv("DRY_RUN", "true").lower() == "true"

    sports = []
    for sport_path, kalshi_series in sorted([(v, k) for k, v in KALSHI_TO_ESPN.items()]):
        clock_dir = SPORT_CLOCK_DIR.get(sport_path, "down")
        final_secs = int(cfg.get(f"final_seconds:{sport_path}", "0"))
        if not final_secs:
            final_secs = 4800 if clock_dir == "up" else 300
        lead = int(cfg.get(f"lead:{sport_path}", "0"))
        if not lead and sport_path in MIN_SCORE_LEAD:
            lead = MIN_SCORE_LEAD[sport_path]
        stretch_lead = max(1, lead - (lead * 4 // 10))

        sports.append(
            {
                "sport_path": sport_path,
                "name": SPORT_DISPLAY_NAMES.get(sport_path, sport_path),
                "kalshi_series": kalshi_series,
                "final_period": SPORT_FINAL_PERIOD.get(sport_path, 4),
                "min_score_lead": lead,
                "stretch_score_lead": stretch_lead,
                "clock_direction": clock_dir,
                "final_minutes_desc": _format_final_minutes(clock_dir, final_secs),
                "final_minutes_seconds": (None if clock_dir == "none" else final_secs),
            }
        )

    return {
        "trading": {
            "min_yes_price": int(cfg.get("min_yes_price", "92")),
            "max_bet_cents": int(cfg.get("max_bet_cents", "500")),
            "max_positions": int(cfg.get("max_positions", "20")),
            "min_volume": int(cfg.get("min_volume", "50")),
            "dry_run": dry_run,
        },
        "stretch": {
            "price_min": int(cfg.get("stretch_price_min", "85")),
        },
        "polling": {
            "espn_interval_s": 10,
            "kalshi_scan_interval_s": 5,
            "kalshi_ws": True,
            "db_backup_interval_s": 1800,
        },
        "sports": sports,
    }


class ConfigUpdate(BaseModel):
    key: str
    value: str


@app.put("/api/config")
def update_config(
    body: ConfigUpdate,
    authorization: str | None = Header(None),
):
    _check_token(authorization)
    set_config(body.key, body.value)
    return {"ok": True, "key": body.key, "value": body.value}

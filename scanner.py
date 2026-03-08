"""
Kalshi Sports Market Scanner

Scans for sports prediction markets where:
  1. Yes price >= 88 cents (outcome nearly decided)
  2. ESPN confirms the game is in its FINAL MINUTES
     (4th quarter <=5 min, 9th inning, 2nd half final minutes, etc)
  3. Sufficient liquidity to trade

Uses ESPN live scoreboard to verify game state, so we only buy
when a game is truly almost over - not just pre-game favorites.

Strategy: Buy Yes at 88-99c on nearly-finished games,
collect $1 at settlement. High volume, high win rate.
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

from db import (
    BalanceSnapshot,
    Opportunity,
    Scan,
    StretchOpportunity,
    Trade,
    get_config_int,
    get_session,
    init_db,
)
from espn import (
    game_meets_timing,
    get_categorized_games,
    match_kalshi_to_espn,
)
from kalshi_client import KalshiClient, KalshiWebSocket

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("scanner.log"),
    ],
)
log = logging.getLogger(__name__)

# Module-level market prices dict, populated by WS/API in run_scanner
market_prices: dict[str, dict] = {}

# Only bet on games expiring within this many minutes.
# Games typically last 2-3 hours. If expected expiry is 15 min away,
# we're in the final stretch - 4th quarter, 9th inning, etc.
MAX_MINUTES_TO_EXPIRY = 15

# Minimum volume on the market to ensure there's liquidity
MIN_VOLUME = 50

# Minimum score lead by sport to filter out close games that could flip
MIN_SCORE_LEAD = {
    "basketball/nba": 8,
    "basketball/mens-college-basketball": 8,
    "hockey/nhl": 2,
    "football/nfl": 10,
    "football/college-football": 10,
    "baseball/mlb": 3,
    "soccer/eng.1": 2,
    "soccer/esp.1": 2,
    "soccer/usa.1": 2,
    "mma/ufc": 0,  # no score lead in fights
}

# Sports game series on Kalshi - these are individual game markets
# (not futures/championships which have long expiry windows)
SPORTS_GAME_SERIES = [
    "KXNBAGAME",  # NBA games
    "KXNFLGAME",  # NFL games
    "KXNHLGAME",  # NHL games
    "KXMLBGAME",  # MLB games
    "KXNCAAMBGAME",  # College basketball games
    "KXNCAAFBGAME",  # College football games
    "KXUFCFIGHT",  # UFC fights
    "KXLALIGAGAME",  # La Liga games
    "KXEPLGAME",  # Premier League games
    "KXMLSGAME",  # MLS games
    "KXMLBSTGAME",  # MLB spring training games
    "KXTENNISGAME",  # Tennis matches
]


def load_client() -> KalshiClient:
    key_id = os.environ["KALSHI_API_KEY"]
    # Support private key as env var (for ECS) or file path (for local)
    key_pem = os.environ.get("KALSHI_PRIVATE_KEY")
    if key_pem:
        return KalshiClient.from_key_string(key_id, key_pem)
    key_path = os.environ["KALSHI_PRIVATE_KEY_PATH"]
    return KalshiClient.from_key_file(key_id, key_path)


async def find_sports_game_series(client: KalshiClient) -> list[str]:
    """Discover sports game series (not futures/awards)."""
    series_data = await client.get_series()
    game_tickers = []
    for s in series_data.get("series", []):
        ticker = s.get("ticker", "")
        # Match known game series or anything with "GAME" / "FIGHT" / "MATCH" in ticker
        if any(ticker.startswith(p) for p in SPORTS_GAME_SERIES):
            game_tickers.append(ticker)
        elif s.get("category", "") == "Sports" and any(
            kw in ticker.upper() for kw in ["GAME", "FIGHT", "MATCH", "BOUT"]
        ):
            game_tickers.append(ticker)
    return game_tickers


def is_game_nearly_over(market: dict, max_minutes: float = MAX_MINUTES_TO_EXPIRY) -> bool:
    """
    Check if a game is in its final stretch.

    Uses expected_expiration_time (when Kalshi expects the game to end).
    We only buy when the game is within max_minutes of ending,
    meaning we're in the last quarter/period/set where the outcome
    is essentially locked in.
    """
    exp_str = market.get("expected_expiration_time", "")
    if not exp_str:
        return False

    try:
        exp_time = datetime.fromisoformat(exp_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return False

    now = datetime.now(timezone.utc)
    time_until_expiry = exp_time - now

    # Game must expire in the future (not settled yet)
    # AND within our tight window (game is nearly over)
    return timedelta(0) < time_until_expiry <= timedelta(minutes=max_minutes)


def has_liquidity(market: dict, min_volume: int = MIN_VOLUME) -> bool:
    """Check that the market has enough volume/liquidity to trade."""
    volume = market.get("volume", 0) or 0
    # Also check there's actually a bid (someone's on the other side)
    yes_bid = market.get("yes_bid", 0) or 0
    return volume >= min_volume and yes_bid > 0


async def place_bet(
    client: KalshiClient,
    opp: dict,
    max_cost_cents: int,
    dry_run: bool = True,
) -> Optional[dict]:
    yes_price = opp["yes_ask"]
    count = max_cost_cents // yes_price
    if count < 1:
        log.info(f"  Cannot afford any contracts at {yes_price}c (budget: {max_cost_cents}c)")
        return None

    profit_per_contract = 100 - yes_price
    total_profit_if_win = count * profit_per_contract
    total_cost = count * yes_price

    log.info(
        f"  Order: BUY {count}x YES @ {yes_price}c = ${total_cost / 100:.2f} cost, "
        f"${total_profit_if_win / 100:.2f} potential profit | "
        f"ESPN: P{opp.get('espn_period', '')} {opp.get('espn_clock', '')}"
    )

    session = get_session()
    trade = Trade(
        ticker=opp["ticker"],
        event_ticker=opp["event_ticker"],
        title=opp["title"],
        side="yes",
        action="buy",
        count=count,
        yes_price=yes_price,
        cost_cents=total_cost,
        potential_profit_cents=total_profit_if_win,
        dry_run=dry_run,
    )

    if dry_run:
        log.info("  [DRY RUN] Order not placed")
        trade.status = "dry_run"
        session.add(trade)
        session.commit()
        session.close()
        return {"dry_run": True, "count": count, "yes_price": yes_price}

    try:
        result = await client.create_order(
            ticker=opp["ticker"],
            side="yes",
            action="buy",
            count=count,
            yes_price=yes_price,
        )
        log.info(f"  Order placed: {result}")
        order = result.get("order", {})
        trade.order_id = order.get("order_id", "")
        trade.status = "placed"
        session.add(trade)
        session.commit()
        session.close()
        return result
    except Exception as e:
        log.error(f"  Order failed: {e}")
        trade.status = "error"
        trade.error = str(e)
        session.add(trade)
        session.commit()
        session.close()
        return None


async def check_settlements(client: KalshiClient):
    """Check open trades for settlement and update P&L."""
    session = get_session()
    open_trades = (
        session.query(Trade)
        .filter(Trade.status.in_(("placed", "filled")), Trade.dry_run == False)
        .all()
    )

    for trade in open_trades:
        try:
            market = await client.get_market(trade.ticker)
            status = market.get("status", "")
            result = market.get("result", "")

            if status in ("finalized", "settled"):
                if result == trade.side:
                    # Won: each contract pays $1, profit = (100 - price) * count
                    trade.status = "settled_win"
                    trade.pnl_cents = trade.potential_profit_cents
                    log.info(
                        f"  WIN: {trade.ticker} settled {result} | "
                        f"P&L: +${trade.pnl_cents / 100:.2f}"
                    )
                else:
                    # Lost: lose the cost
                    trade.status = "settled_loss"
                    trade.pnl_cents = -trade.cost_cents
                    log.info(
                        f"  LOSS: {trade.ticker} settled {result} | "
                        f"P&L: -${trade.cost_cents / 100:.2f}"
                    )
        except Exception as e:
            log.warning(f"  Failed to check {trade.ticker}: {e}")

    session.commit()
    session.close()


async def record_balance(client: KalshiClient):
    try:
        balance = await client.get_balance()
        session = get_session()
        snap = BalanceSnapshot(
            balance_cents=balance.get("balance", 0),
            portfolio_value_cents=balance.get("portfolio_value", 0),
        )
        session.add(snap)
        session.commit()
        session.close()
        bal = balance.get("balance", 0) / 100
        port = balance.get("portfolio_value", 0) / 100
        log.info(f"Balance: ${bal:.2f}, Portfolio: ${port:.2f}")
    except Exception as e:
        log.warning(f"Failed to record balance: {e}")

    # Stretch thresholds: looser filters for shadow-tracking


STRETCH_PRICE_MIN = 85  # vs current 92c
STRETCH_SCORE_LEAD = {
    k: max(1, v - (v * 4 // 10))  # ~40% lower lead requirement
    for k, v in MIN_SCORE_LEAD.items()
}

# What-If strategy sets: each defines a different parameter combination
# to shadow-track alongside real bets. Results show which tuning works best.
WHAT_IF_STRATEGIES = {
    "lower_price": {
        "label": "Lower Price (88¢)",
        "min_yes_price": 88,
        "lead_pct": 100,  # % of configured lead
        "countdown_secs": 300,
        "countup_secs": 4500,  # 75th minute
    },
    "loose_leads": {
        "label": "Loose Leads (50%)",
        "min_yes_price": 92,
        "lead_pct": 50,
        "countdown_secs": 300,
        "countup_secs": 4500,  # 75th minute
    },
    "early_entry": {
        "label": "Early Entry (10 min)",
        "min_yes_price": 92,
        "lead_pct": 100,
        "countdown_secs": 600,
        "countup_secs": 3900,  # 65th minute
    },
    "yolo": {
        "label": "YOLO (85¢ + loose + early)",
        "min_yes_price": 85,
        "lead_pct": 50,
        "countdown_secs": 600,
        "countup_secs": 3900,  # 65th minute
    },
    "sniper": {
        "label": "Sniper (95¢ + 2 min)",
        "min_yes_price": 95,
        "lead_pct": 100,
        "countdown_secs": 120,
        "countup_secs": 5100,  # 85th minute
    },
}


async def scan_kalshi_with_espn(
    client: KalshiClient,
    espn_final: dict,
    min_yes_price: int,
    max_bet_cents: int,
    dry_run: bool,
    espn_final_period: dict | None = None,
):
    """Scan Kalshi markets against cached ESPN game state and place bets."""
    opportunities = []
    stretch_opps = []

    if not espn_final and not espn_final_period:
        log.info("No ESPN games in final minutes — skipping Kalshi scan")
        return

    # Scan Kalshi markets against ESPN games
    for series_ticker, espn_games in espn_final.items():
        try:
            cursor = None
            while True:
                data = await client.get_events(
                    status="open",
                    series_ticker=series_ticker,
                    with_nested_markets=True,
                    cursor=cursor,
                )
                events = data.get("events", [])
                if not events:
                    break

                for event in events:
                    event_ticker = event.get("event_ticker", "")
                    title = event.get("title", "")
                    markets = event.get("markets", [])

                    for market in markets:
                        status = market.get("status", "")
                        if status not in ("active", "open"):
                            continue
                        if not has_liquidity(market):
                            continue

                        yes_bid = market.get("yes_bid", 0)
                        yes_ask = market.get("yes_ask", 0)
                        ticker = market.get("ticker", "")

                        # Need at least stretch-level price
                        stretch_min = get_config_int("stretch_price_min") or STRETCH_PRICE_MIN
                        if not (yes_ask and yes_ask >= stretch_min and yes_ask <= 99):
                            continue

                        espn_game = match_kalshi_to_espn(ticker, title, espn_games)
                        if not espn_game:
                            continue

                        db_lead = get_config_int(f"lead:{espn_game.sport_path}")
                        fallback = MIN_SCORE_LEAD.get(espn_game.sport_path, 5)
                        min_lead = db_lead if db_lead else fallback
                        stretch_lead = max(1, min_lead - (min_lead * 4 // 10))
                        meets_price = yes_ask >= min_yes_price
                        meets_lead = espn_game.score_diff >= min_lead

                        if meets_price and meets_lead:
                            # Full opportunity — meets all filters
                            spread = 100 - yes_ask
                            opportunities.append(
                                {
                                    "ticker": ticker,
                                    "event_ticker": event_ticker,
                                    "title": title,
                                    "yes_sub_title": market.get("yes_sub_title", ""),
                                    "yes_bid": yes_bid,
                                    "yes_ask": yes_ask,
                                    "spread": spread,
                                    "volume": market.get("volume", 0),
                                    "close_time": market.get("close_time", ""),
                                    "expected_expiration": market.get(
                                        "expected_expiration_time", ""
                                    ),
                                    "series_ticker": series_ticker,
                                    "sport_path": espn_game.sport_path,
                                    "espn_period": espn_game.period,
                                    "espn_clock": espn_game.display_clock,
                                    "espn_home": espn_game.home_team,
                                    "espn_away": espn_game.away_team,
                                    "espn_home_score": espn_game.home_score,
                                    "espn_away_score": espn_game.away_score,
                                    "espn_score": f"{espn_game.away_score}-{espn_game.home_score}",
                                    "espn_lead": espn_game.score_diff,
                                }
                            )
                        else:
                            # Stretch: close but missed at least one filter
                            meets_stretch_lead = espn_game.score_diff >= stretch_lead
                            if not meets_stretch_lead:
                                continue  # too far outside even stretch range

                            reason = []
                            if not meets_price:
                                reason.append("price")
                            if not meets_lead:
                                reason.append("score_lead")

                            stretch_opps.append(
                                {
                                    "ticker": ticker,
                                    "event_ticker": event_ticker,
                                    "title": title,
                                    "yes_sub_title": market.get("yes_sub_title", ""),
                                    "yes_ask": yes_ask,
                                    "volume": market.get("volume", 0),
                                    "series_ticker": series_ticker,
                                    "sport_path": espn_game.sport_path,
                                    "score_lead": espn_game.score_diff,
                                    "min_score_lead": min_lead,
                                    "espn_period": espn_game.period,
                                    "espn_clock": espn_game.display_clock,
                                    "reason": ",".join(reason),
                                }
                            )

                cursor = data.get("cursor", "")
                if not cursor:
                    break

        except Exception as e:
            log.warning(f"Error scanning series {series_ticker}: {e}")
            continue

    opportunities.sort(key=lambda x: (-x["spread"], -x["espn_lead"]))

    # Record scan and process opportunities
    session = get_session()
    scan = Scan(opportunities_found=len(opportunities))
    session.add(scan)
    session.commit()
    scan_id = scan.id

    if not opportunities:
        log.info("No Kalshi opportunities matched ESPN games")
    else:
        open_statuses = ("placed", "filled", "dry_run")
        open_trades = (
            session.query(Trade)
            .filter(Trade.status.in_(open_statuses), Trade.dry_run == dry_run)
            .all()
        )
        open_event_tickers = {t.event_ticker for t in open_trades}
        open_count = len(open_trades)

        log.info(
            f"Found {len(opportunities)} opportunities on live games "
            f"({open_count}/20 open positions):"
        )
        for opp in opportunities:
            log.info(
                f"  {opp['ticker']} | {opp['yes_sub_title']} | "
                f"Yes Ask: {opp['yes_ask']}c | Spread: {opp['spread']}c | "
                f"ESPN: P{opp['espn_period']} {opp['espn_clock']} "
                f"{opp['espn_away']}@{opp['espn_home']} {opp['espn_score']} | "
                f"Vol: {opp['volume']}"
            )

            db_opp = Opportunity(
                scan_id=scan_id,
                ticker=opp["ticker"],
                event_ticker=opp["event_ticker"],
                series_ticker=opp["series_ticker"],
                title=opp["title"],
                yes_sub_title=opp["yes_sub_title"],
                yes_bid=opp["yes_bid"],
                yes_ask=opp["yes_ask"],
                spread=opp["spread"],
                volume=opp["volume"],
                close_time=opp["close_time"],
                sport_path=opp.get("sport_path"),
                espn_period=opp.get("espn_period"),
                espn_clock=opp.get("espn_clock"),
                espn_home=opp.get("espn_home"),
                espn_away=opp.get("espn_away"),
                espn_home_score=opp.get("espn_home_score"),
                espn_away_score=opp.get("espn_away_score"),
                espn_score_diff=opp.get("espn_lead"),
            )
            session.add(db_opp)

            if opp["event_ticker"] in open_event_tickers:
                log.info(f"  SKIP: already have position on {opp['event_ticker']}")
                continue

            max_pos = get_config_int("max_positions") or 20
            if open_count >= max_pos:
                log.info("  SKIP: at max 20 open positions")
                continue

            result = await place_bet(client, opp, max_cost_cents=max_bet_cents, dry_run=dry_run)
            if result:
                open_event_tickers.add(opp["event_ticker"])
                open_count += 1

    session.commit()

    # Record stretch opportunities (dedupe by ticker+strategy — only record first sighting)
    if stretch_opps:
        existing_stretch = {
            (t[0], t[1])
            for t in session.query(StretchOpportunity.ticker, StretchOpportunity.strategy_set)
            .filter(StretchOpportunity.status == "open")
            .all()
        }
        new_stretches = 0
        for s in stretch_opps:
            strategy = s.get("strategy_set", "default")
            if (s["ticker"], strategy) in existing_stretch:
                continue
            session.add(
                StretchOpportunity(
                    ticker=s["ticker"],
                    event_ticker=s["event_ticker"],
                    series_ticker=s["series_ticker"],
                    title=s["title"],
                    yes_sub_title=s["yes_sub_title"],
                    yes_ask=s["yes_ask"],
                    volume=s["volume"],
                    sport_path=s["sport_path"],
                    score_lead=s["score_lead"],
                    min_score_lead=s["min_score_lead"],
                    espn_period=s["espn_period"],
                    espn_clock=s["espn_clock"],
                    reason=s["reason"],
                    strategy_set=strategy,
                )
            )
            existing_stretch.add((s["ticker"], strategy))
            new_stretches += 1
        if new_stretches:
            log.info(f"Recorded {new_stretches} new stretch opportunities")
        session.commit()

    # --- What-If strategy evaluation ---
    # Evaluate all final-period games against each what-if strategy
    if espn_final_period:
        _evaluate_what_if_strategies(session, espn_final_period, max_bet_cents)

    session.close()


def _evaluate_what_if_strategies(session, espn_final_period: dict, max_bet_cents: int):
    """Shadow-evaluate markets against each what-if strategy set."""
    # Pre-load existing open what-if tickers to dedupe
    existing = {
        (t[0], t[1])
        for t in session.query(StretchOpportunity.ticker, StretchOpportunity.strategy_set)
        .filter(StretchOpportunity.status == "open")
        .all()
    }

    new_count = 0
    for strategy_name, strategy in WHAT_IF_STRATEGIES.items():
        strat_price = int(strategy["min_yes_price"])
        lead_pct = int(strategy["lead_pct"])
        cd_secs = int(strategy["countdown_secs"])
        cu_secs = int(strategy["countup_secs"])

        for series_ticker, espn_games in espn_final_period.items():
            for game in espn_games:
                # Check if game meets this strategy's timing
                if not game_meets_timing(game, cd_secs, cu_secs):
                    continue

                # Get the configured lead for this sport
                db_lead = get_config_int(f"lead:{game.sport_path}")
                base_lead = db_lead if db_lead else MIN_SCORE_LEAD.get(game.sport_path, 5)
                strat_lead = max(1, base_lead * lead_pct // 100)

                if game.score_diff < strat_lead:
                    continue

                # This game meets the strategy's filters — check market prices
                # We use market_prices dict if available (populated by WS/API)
                from espn import _espn_to_kalshi_codes

                home_codes = _espn_to_kalshi_codes(game.home_team)
                away_codes = _espn_to_kalshi_codes(game.away_team)

                # Check all known market tickers for this game
                for ticker, prices in list(market_prices.items()):
                    prefix = series_ticker.replace("GAME", "").replace("FIGHT", "")
                    if not ticker.startswith(prefix):
                        # Quick filter: ticker should relate to this series
                        # Use a broader match — check if team codes appear in ticker
                        ticker_upper = ticker.upper()
                        home_match = any(c in ticker_upper for c in home_codes)
                        away_match = any(c in ticker_upper for c in away_codes)
                        if not (home_match and away_match):
                            continue

                    yes_ask = prices.get("yes_ask", 0)
                    volume = prices.get("volume", 0)

                    if not (yes_ask and strat_price <= yes_ask <= 99 and volume >= 50):
                        continue

                    # This market would qualify under this strategy
                    # Skip if it already qualifies under real filters (don't double-count)
                    cur_price = get_config_int("min_yes_price") or 92
                    cur_lead = db_lead if db_lead else base_lead
                    real_timing = game.is_in_final_minutes
                    real_price = yes_ask >= cur_price
                    real_lead = game.score_diff >= cur_lead
                    if real_timing and real_price and real_lead:
                        continue  # already a real opportunity

                    if (ticker, strategy_name) in existing:
                        continue

                    # Determine what filters this strategy relaxes
                    reasons = []
                    if not real_price:
                        reasons.append("price")
                    if not real_lead:
                        reasons.append("score_lead")
                    if not real_timing:
                        reasons.append("timing")

                    session.add(
                        StretchOpportunity(
                            ticker=ticker,
                            event_ticker=series_ticker,
                            series_ticker=series_ticker,
                            title=f"{game.away_team} @ {game.home_team}",
                            yes_sub_title="",
                            yes_ask=yes_ask,
                            volume=volume,
                            sport_path=game.sport_path,
                            score_lead=game.score_diff,
                            min_score_lead=strat_lead,
                            espn_period=game.period,
                            espn_clock=game.display_clock,
                            reason=",".join(reasons) if reasons else "strategy",
                            strategy_set=strategy_name,
                        )
                    )
                    existing.add((ticker, strategy_name))
                    new_count += 1

    if new_count:
        log.info(f"Recorded {new_count} new what-if opportunities across strategies")
        session.commit()


async def check_stretch_settlements(client: KalshiClient):
    """Check stretch opportunities for settlement — would we have won?"""
    session = get_session()
    open_stretches = (
        session.query(StretchOpportunity).filter(StretchOpportunity.status == "open").all()
    )
    for stretch in open_stretches:
        try:
            market = await client.get_market(stretch.ticker)
            status = market.get("status", "")
            result = market.get("result", "")

            if status in ("finalized", "settled"):
                # Hypothetical: if we'd bought YES at the ask price
                cost = stretch.yes_ask * 5  # assume 5 contracts like real bets
                profit = (100 - stretch.yes_ask) * 5
                if result == "yes":
                    stretch.status = "settled_win"
                    stretch.pnl_cents = profit
                    log.info(
                        f"  STRETCH WIN: {stretch.ticker} | "
                        f"Would have made +${profit / 100:.2f} "
                        f"(reason: {stretch.reason})"
                    )
                else:
                    stretch.status = "settled_loss"
                    stretch.pnl_cents = -cost
                    log.info(
                        f"  STRETCH LOSS: {stretch.ticker} | "
                        f"Would have lost -${cost / 100:.2f} "
                        f"(reason: {stretch.reason})"
                    )
        except Exception as e:
            log.warning(f"  Failed to check stretch {stretch.ticker}: {e}")

    session.commit()
    session.close()


async def backup_db():
    """Copy SQLite DB to S3 if bucket is configured."""
    bucket = os.getenv("DB_BACKUP_BUCKET")
    if not bucket:
        return
    db_url = os.getenv("DATABASE_URL", "")
    db_path = db_url.replace("sqlite:///", "") if db_url.startswith("sqlite:///") else None
    if not db_path or not os.path.exists(db_path):
        return
    try:
        import shutil
        from datetime import datetime, timezone

        import boto3

        # Copy to temp file first (safe while DB is in use)
        tmp = db_path + ".backup"
        shutil.copy2(db_path, tmp)

        s3 = boto3.client("s3")
        now = datetime.now(timezone.utc)
        key = f"backups/{now.strftime('%Y-%m-%d/%H%M')}-predictions.db"
        s3.upload_file(tmp, bucket, key)

        # Also keep a "latest" copy for easy restore
        s3.upload_file(tmp, bucket, "backups/latest.db")
        os.remove(tmp)
        log.info(f"DB backed up to s3://{bucket}/{key}")
    except Exception as e:
        log.warning(f"DB backup failed: {e}")


async def run_scanner(
    min_yes_price: int = 88,
    max_bet_cents: int = 500,
    poll_interval: int = 30,
    dry_run: bool = True,
):
    init_db()
    client = load_client()
    await record_balance(client)

    espn_interval = 10  # Refresh ESPN game state every 10s

    # Shared state protected by locks
    espn_cache: dict = {}
    espn_final_period_cache: dict = {}
    espn_lock = asyncio.Lock()

    # Track live market prices from WebSocket ticker updates (module-level for what-if access)
    global market_prices
    market_prices = {}  # ticker -> {yes_bid, yes_ask, volume}

    # Track which market tickers we're subscribed to
    subscribed_tickers: set[str] = set()
    ticker_sub_sid: int | None = None
    lifecycle_sub_sid: int | None = None

    ws = KalshiWebSocket(client)

    def on_ticker(msg: dict):
        """Handle real-time price updates from WebSocket."""
        data = msg.get("msg", {})
        ticker = data.get("market_ticker", "")
        if ticker:
            market_prices[ticker] = {
                "yes_bid": data.get("yes_bid", 0),
                "yes_ask": data.get("yes_ask", 0),
                "volume": data.get("volume", 0),
                "open_interest": data.get("open_interest", 0),
            }

    async def on_lifecycle(msg: dict):
        """Handle market lifecycle events (settlement)."""
        data = msg.get("msg", {})
        ticker = data.get("market_ticker", "")
        new_status = data.get("market_status", "")
        result = data.get("result", "")

        if new_status in ("finalized", "settled") and ticker:
            log.info(f"WS lifecycle: {ticker} -> {new_status} result={result}")
            # Update real trades
            session = get_session()
            open_trades = (
                session.query(Trade)
                .filter(
                    Trade.ticker == ticker,
                    Trade.status.in_(("placed", "filled")),
                    Trade.dry_run == False,
                )
                .all()
            )
            for trade in open_trades:
                if result == trade.side:
                    trade.status = "settled_win"
                    trade.pnl_cents = trade.potential_profit_cents
                    log.info(f"  WIN: {trade.ticker} | P&L: +${trade.pnl_cents / 100:.2f}")
                else:
                    trade.status = "settled_loss"
                    trade.pnl_cents = -trade.cost_cents
                    log.info(f"  LOSS: {trade.ticker} | P&L: -${trade.cost_cents / 100:.2f}")

            # Update stretch opportunities
            open_stretches = (
                session.query(StretchOpportunity)
                .filter(StretchOpportunity.ticker == ticker, StretchOpportunity.status == "open")
                .all()
            )
            for stretch in open_stretches:
                cost = stretch.yes_ask * 5
                profit = (100 - stretch.yes_ask) * 5
                if result == "yes":
                    stretch.status = "settled_win"
                    stretch.pnl_cents = profit
                    log.info(f"  STRETCH WIN: {stretch.ticker} | +${profit / 100:.2f}")
                else:
                    stretch.status = "settled_loss"
                    stretch.pnl_cents = -cost
                    log.info(f"  STRETCH LOSS: {stretch.ticker} | -${cost / 100:.2f}")

            session.commit()
            session.close()
            await record_balance(client)

    ws.on("ticker", on_ticker)
    ws.on("market_lifecycle_v2", on_lifecycle)

    async def espn_loop():
        """Refresh ESPN final-minutes games every 10s."""
        nonlocal espn_cache, espn_final_period_cache
        while True:
            try:
                log.info("ESPN: refreshing live game state...")
                fresh, fresh_fp = await get_categorized_games()
                async with espn_lock:
                    espn_cache = fresh
                    espn_final_period_cache = fresh_fp
                total = sum(len(g) for g in fresh.values())
                if total:
                    log.info(f"ESPN: {total} games in final minutes across {list(fresh.keys())}")
                    for games in fresh.values():
                        for g in games:
                            log.info(
                                f"  ESPN: {g.away_team} @ {g.home_team} | "
                                f"{g.away_score}-{g.home_score} | "
                                f"P{g.period} {g.display_clock} | "
                                f"Lead: {g.score_diff}pts by {g.leading_team}"
                            )
                else:
                    log.info("ESPN: no games in final minutes")
            except Exception as e:
                log.warning(f"ESPN refresh error: {e}")
            await asyncio.sleep(espn_interval)

    async def kalshi_scan_loop():
        """Fetch Kalshi events, subscribe to new tickers, evaluate."""
        nonlocal ticker_sub_sid, lifecycle_sub_sid
        kalshi_interval = 5  # Discover new markets every 5s

        # Wait for first ESPN fetch + WS connect
        await asyncio.sleep(3)

        while True:
            try:
                log.info("=" * 60)
                # Re-read config each loop so changes take effect immediately
                cur_price = get_config_int("min_yes_price") or min_yes_price
                cur_bet = get_config_int("max_bet_cents") or max_bet_cents
                log.info(f"Kalshi: scanning for Yes >= {cur_price}c...")
                async with espn_lock:
                    current_espn = dict(espn_cache)
                    current_espn_fp = dict(espn_final_period_cache)

                # Discover all active market tickers from Kalshi API
                # Include both final-minutes and final-period series for what-if tracking
                all_series = set(current_espn.keys()) | set(current_espn_fp.keys())
                new_tickers: set[str] = set()
                for series_ticker in all_series:
                    try:
                        cursor = None
                        while True:
                            data = await client.get_events(
                                status="open",
                                series_ticker=series_ticker,
                                with_nested_markets=True,
                                cursor=cursor,
                            )
                            for event in data.get("events", []):
                                for market in event.get("markets", []):
                                    t = market.get("ticker", "")
                                    if t and market.get("status") in ("active", "open"):
                                        new_tickers.add(t)
                                        # Seed prices from API if WS hasn't updated yet
                                        if t not in market_prices:
                                            market_prices[t] = {
                                                "yes_bid": market.get("yes_bid", 0),
                                                "yes_ask": market.get("yes_ask", 0),
                                                "volume": market.get("volume", 0),
                                            }
                            cursor = data.get("cursor", "")
                            if not cursor:
                                break
                    except Exception as e:
                        log.warning(f"Error fetching series {series_ticker}: {e}")

                # Subscribe to any new tickers via WebSocket
                to_add = new_tickers - subscribed_tickers
                if to_add:
                    tickers_list = list(to_add)
                    try:
                        if ticker_sub_sid is None:
                            ticker_sub_sid = await ws.subscribe(["ticker"], tickers_list)
                            lifecycle_sub_sid = await ws.subscribe(
                                ["market_lifecycle_v2"], tickers_list
                            )
                        else:
                            assert ticker_sub_sid is not None
                            assert lifecycle_sub_sid is not None
                            await ws.update_subscription(ticker_sub_sid, tickers_list)
                            await ws.update_subscription(lifecycle_sub_sid, tickers_list)
                        subscribed_tickers.update(to_add)
                        n = len(to_add)
                        total = len(subscribed_tickers)
                        log.info(f"WS: subscribed to {n} new tickers ({total} total)")
                    except Exception as e:
                        log.warning(f"WS subscribe error: {e}")

                # Now evaluate using real-time prices from WS
                await scan_kalshi_with_espn(
                    client,
                    current_espn,
                    cur_price,
                    cur_bet,
                    dry_run,
                    espn_final_period=current_espn_fp,
                )

                # Settlement checks as fallback (WS lifecycle handles most)
                await check_settlements(client)
                await check_stretch_settlements(client)
                await record_balance(client)
            except Exception as e:
                log.warning(f"Kalshi scan error: {e}")

            await asyncio.sleep(kalshi_interval)

    async def ws_loop():
        """Maintain WebSocket connection and listen for events."""
        while True:
            try:
                await ws.connect()
                await ws.listen()
            except Exception as e:
                log.warning(f"WS loop error: {e}, restarting in 5s...")
                await asyncio.sleep(5)

    async def backup_loop():
        """Back up DB to S3 every 30 minutes."""
        while True:
            await asyncio.sleep(1800)  # 30 min
            await backup_db()

    # Run all loops concurrently
    await asyncio.gather(espn_loop(), kalshi_scan_loop(), ws_loop(), backup_loop())


if __name__ == "__main__":
    min_price = int(os.getenv("MIN_YES_PRICE", "88"))
    max_bet = int(os.getenv("MAX_BET_AMOUNT_CENTS", "500"))
    interval = int(os.getenv("POLL_INTERVAL_SECONDS", "30"))
    dry = os.getenv("DRY_RUN", "true").lower() == "true"

    log.info(
        f"Starting scanner: min_price={min_price}c, max_bet={max_bet}c, "
        f"ESPN=10s, Kalshi=5s, dry_run={dry}"
    )
    asyncio.run(
        run_scanner(
            min_yes_price=min_price,
            max_bet_cents=max_bet,
            poll_interval=interval,
            dry_run=dry,
        )
    )

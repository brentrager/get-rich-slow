"""
Kalshi Sports Market Scanner

Scans for sports prediction markets where:
  1. Yes price >= 88 cents (outcome nearly decided)
  2. Game is currently in progress and near ending
     (expected_expiration_time is within MAX_HOURS_TO_EXPIRY)

This ensures we only buy when a game is almost over and the
outcome is effectively locked in, not pre-game favorites.

Strategy: Buy Yes at 88-99c on nearly-finished games,
collect $1 at settlement. High volume, high win rate.
"""

import os
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

from kalshi_client import KalshiClient
from db import init_db, get_session, Scan, Opportunity, Trade, BalanceSnapshot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("scanner.log"),
    ],
)
log = logging.getLogger(__name__)

# Only bet on games expiring within this many minutes.
# Games typically last 2-3 hours. If expected expiry is 15 min away,
# we're in the final stretch - 4th quarter, 9th inning, etc.
MAX_MINUTES_TO_EXPIRY = 15

# Minimum volume on the market to ensure there's liquidity
MIN_VOLUME = 50

# Sports game series on Kalshi - these are individual game markets
# (not futures/championships which have long expiry windows)
SPORTS_GAME_SERIES = [
    "KXNBAGAME",       # NBA games
    "KXNFLGAME",       # NFL games
    "KXNHLGAME",       # NHL games
    "KXMLBGAME",       # MLB games
    "KXNCAAMBGAME",    # College basketball games
    "KXNCAAFBGAME",    # College football games
    "KXUFCFIGHT",      # UFC fights
    "KXLALIGAGAME",    # La Liga games
    "KXEPLGAME",       # Premier League games
    "KXSOCCERGAME",    # Soccer games
    "KXTENNISGAME",    # Tennis matches
]


def load_client() -> KalshiClient:
    key_id = os.environ["KALSHI_API_KEY"]
    key_path = os.environ["KALSHI_PRIVATE_KEY_PATH"]
    return KalshiClient.from_key_file(key_id, key_path)


def find_sports_game_series(client: KalshiClient) -> list[str]:
    """Discover sports game series (not futures/awards)."""
    series_data = client.get_series()
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


def scan_markets(client: KalshiClient, min_yes_price: int = 88) -> list[dict]:
    opportunities = []

    log.info("Discovering sports game series...")
    game_series = find_sports_game_series(client)
    log.info(f"Found {len(game_series)} game series")

    if not game_series:
        log.info("No game series found via API, using hardcoded list...")
        game_series = SPORTS_GAME_SERIES

    now = datetime.now(timezone.utc)

    for series_ticker in game_series:
        try:
            cursor = None
            while True:
                data = client.get_events(
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

                        # KEY FILTERS:
                        # 1. Game must be nearly over
                        if not is_game_nearly_over(market):
                            continue
                        # 2. Must have enough liquidity
                        if not has_liquidity(market):
                            continue

                        yes_bid = market.get("yes_bid", 0)
                        yes_ask = market.get("yes_ask", 0)
                        ticker = market.get("ticker", "")
                        exp_time = market.get("expected_expiration_time", "")

                        # Calculate hours until expected expiry
                        try:
                            exp_dt = datetime.fromisoformat(exp_time.replace("Z", "+00:00"))
                            hours_left = (exp_dt - now).total_seconds() / 3600
                        except (ValueError, TypeError):
                            hours_left = 0

                        if yes_ask and yes_ask >= min_yes_price and yes_ask <= 99:
                            spread = 100 - yes_ask
                            opportunities.append({
                                "ticker": ticker,
                                "event_ticker": event_ticker,
                                "title": title,
                                "yes_sub_title": market.get("yes_sub_title", ""),
                                "yes_bid": yes_bid,
                                "yes_ask": yes_ask,
                                "spread": spread,
                                "volume": market.get("volume", 0),
                                "close_time": market.get("close_time", ""),
                                "expected_expiration": exp_time,
                                "hours_left": round(hours_left, 2),
                                "series_ticker": series_ticker,
                            })

                cursor = data.get("cursor", "")
                if not cursor:
                    break

        except Exception as e:
            log.warning(f"Error scanning series {series_ticker}: {e}")
            continue

    # Sort by hours_left ascending (closest to ending first), then spread
    opportunities.sort(key=lambda x: (x["hours_left"], -x["spread"]))
    return opportunities


def place_bet(
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
        f"  Order: BUY {count}x YES @ {yes_price}c = ${total_cost/100:.2f} cost, "
        f"${total_profit_if_win/100:.2f} potential profit | "
        f"{opp['hours_left']}h until expiry"
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
        result = client.create_order(
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


def record_balance(client: KalshiClient):
    try:
        balance = client.get_balance()
        session = get_session()
        snap = BalanceSnapshot(
            balance_cents=balance.get("balance", 0),
            portfolio_value_cents=balance.get("portfolio_value", 0),
        )
        session.add(snap)
        session.commit()
        session.close()
        log.info(f"Balance: ${balance.get('balance', 0)/100:.2f}, Portfolio: ${balance.get('portfolio_value', 0)/100:.2f}")
    except Exception as e:
        log.warning(f"Failed to record balance: {e}")


def run_scanner(
    min_yes_price: int = 88,
    max_bet_cents: int = 500,
    poll_interval: int = 30,
    dry_run: bool = True,
):
    init_db()
    client = load_client()
    record_balance(client)

    while True:
        log.info("=" * 60)
        log.info(f"Scanning for Yes >= {min_yes_price}c on in-progress games...")

        opportunities = scan_markets(client, min_yes_price)

        session = get_session()
        scan = Scan(opportunities_found=len(opportunities))
        session.add(scan)
        session.commit()
        scan_id = scan.id

        if not opportunities:
            log.info("No in-progress game opportunities found")
        else:
            log.info(f"Found {len(opportunities)} opportunities on live games:")
            for opp in opportunities:
                log.info(
                    f"  {opp['ticker']} | {opp['yes_sub_title']} | "
                    f"Yes Ask: {opp['yes_ask']}c | Spread: {opp['spread']}c | "
                    f"Expires in {opp['hours_left']}h | Vol: {opp['volume']}"
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
                )
                session.add(db_opp)

                place_bet(client, opp, max_cost_cents=max_bet_cents, dry_run=dry_run)

        session.commit()
        session.close()

        record_balance(client)

        log.info(f"Sleeping {poll_interval}s...")
        time.sleep(poll_interval)


if __name__ == "__main__":
    min_price = int(os.getenv("MIN_YES_PRICE", "88"))
    max_bet = int(os.getenv("MAX_BET_AMOUNT_CENTS", "500"))
    interval = int(os.getenv("POLL_INTERVAL_SECONDS", "30"))
    dry = os.getenv("DRY_RUN", "true").lower() == "true"

    log.info(f"Starting scanner: min_price={min_price}c, max_bet={max_bet}c, interval={interval}s, dry_run={dry}")
    run_scanner(
        min_yes_price=min_price,
        max_bet_cents=max_bet,
        poll_interval=interval,
        dry_run=dry,
    )

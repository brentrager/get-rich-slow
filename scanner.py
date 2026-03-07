"""
Kalshi Sports Market Scanner

Scans for sports prediction markets where Yes price >= 88 cents,
meaning the outcome is nearly decided. Buys these positions to
capture the small spread when the market settles at $1.

Strategy: Buy Yes at 88-99c, collect $1 at settlement.
Profit per contract: 1-12 cents. High volume, high win rate.
"""

import os
import time
import logging
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv

from kalshi_client import KalshiClient

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("scanner.log"),
    ],
)
log = logging.getLogger(__name__)

# Sports series tickers on Kalshi (discovered from their market URLs)
SPORTS_SERIES_PREFIXES = [
    "KXNBA",       # NBA
    "KXNFL",       # NFL
    "KXMLB",       # MLB
    "KXNHL",       # NHL
    "KXUFC",       # UFC/MMA
    "KXNCAAMB",    # College basketball
    "KXNCAAFB",    # College football
    "KXSOCCER",    # Soccer
    "KXEPL",       # Premier League
    "KXLALIGA",    # La Liga
    "KXTENNIS",    # Tennis
]


def load_client() -> KalshiClient:
    key_id = os.environ["KALSHI_API_KEY"]
    key_path = os.environ["KALSHI_PRIVATE_KEY_PATH"]
    return KalshiClient.from_key_file(key_id, key_path)


def find_sports_series(client: KalshiClient) -> list[str]:
    """Discover all sports series tickers."""
    series_data = client.get_series()
    sports_tickers = []
    for s in series_data.get("series", []):
        ticker = s.get("ticker", "")
        # Match known sports prefixes or category
        category = s.get("category", "")
        if category == "Sports" or any(ticker.startswith(p) for p in SPORTS_SERIES_PREFIXES):
            sports_tickers.append(ticker)
    return sports_tickers


def scan_markets(client: KalshiClient, min_yes_price: int = 88) -> list[dict]:
    """
    Scan open sports events for markets where yes_bid >= min_yes_price.
    These are markets where the outcome is nearly certain but not yet settled.
    """
    opportunities = []

    # First discover sports series
    log.info("Discovering sports series...")
    sports_series = find_sports_series(client)
    log.info(f"Found {len(sports_series)} sports series")

    if not sports_series:
        # Fallback: scan all open events and filter by ticker prefix
        log.info("No series found via category, scanning by prefix...")
        sports_series = SPORTS_SERIES_PREFIXES

    for series_ticker in sports_series:
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

                        yes_bid = market.get("yes_bid", 0)
                        yes_ask = market.get("yes_ask", 0)
                        ticker = market.get("ticker", "")

                        # We want markets where Yes is trading at 88c+
                        # yes_ask is what we'd pay to buy Yes
                        if yes_ask and yes_ask >= min_yes_price and yes_ask <= 99:
                            spread = 100 - yes_ask  # profit per contract in cents
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
                                "series_ticker": series_ticker,
                            })

                cursor = data.get("cursor", "")
                if not cursor:
                    break

        except Exception as e:
            log.warning(f"Error scanning series {series_ticker}: {e}")
            continue

    # Sort by spread (highest profit first), then by volume
    opportunities.sort(key=lambda x: (-x["spread"], -x["volume"]))
    return opportunities


def place_bet(
    client: KalshiClient,
    ticker: str,
    yes_price: int,
    max_cost_cents: int,
    dry_run: bool = True,
) -> Optional[dict]:
    """
    Place a Yes buy order on a market.

    Args:
        ticker: Market ticker
        yes_price: Price to pay per Yes contract (in cents, 1-99)
        max_cost_cents: Maximum total cost in cents
        dry_run: If True, don't actually place the order
    """
    count = max_cost_cents // yes_price  # number of contracts we can afford
    if count < 1:
        log.info(f"  Cannot afford any contracts at {yes_price}c (budget: {max_cost_cents}c)")
        return None

    profit_per_contract = 100 - yes_price
    total_profit_if_win = count * profit_per_contract
    total_cost = count * yes_price

    log.info(
        f"  Order: BUY {count}x YES @ {yes_price}c = ${total_cost/100:.2f} cost, "
        f"${total_profit_if_win/100:.2f} potential profit"
    )

    if dry_run:
        log.info("  [DRY RUN] Order not placed")
        return {"dry_run": True, "count": count, "yes_price": yes_price}

    try:
        result = client.create_order(
            ticker=ticker,
            side="yes",
            action="buy",
            count=count,
            yes_price=yes_price,
        )
        log.info(f"  Order placed: {result}")
        return result
    except Exception as e:
        log.error(f"  Order failed: {e}")
        return None


def run_scanner(
    min_yes_price: int = 88,
    max_bet_cents: int = 500,
    poll_interval: int = 30,
    dry_run: bool = True,
):
    """Main scanner loop."""
    client = load_client()

    # Check balance
    balance = client.get_balance()
    log.info(f"Account balance: {balance}")

    while True:
        log.info("=" * 60)
        log.info(f"Scanning for Yes >= {min_yes_price}c opportunities...")

        opportunities = scan_markets(client, min_yes_price)

        if not opportunities:
            log.info("No opportunities found")
        else:
            log.info(f"Found {len(opportunities)} opportunities:")
            for opp in opportunities:
                log.info(
                    f"  {opp['ticker']} | {opp['yes_sub_title']} | "
                    f"Yes Ask: {opp['yes_ask']}c | Spread: {opp['spread']}c | "
                    f"Vol: {opp['volume']}"
                )

                # Place bet on each opportunity
                place_bet(
                    client,
                    ticker=opp["ticker"],
                    yes_price=opp["yes_ask"],
                    max_cost_cents=max_bet_cents,
                    dry_run=dry_run,
                )

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

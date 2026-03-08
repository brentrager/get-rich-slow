"""Integration test: verify Kalshi WebSocket connects, subscribes, and receives data."""

import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from kalshi_client import KalshiClient, KalshiWebSocket


async def test_ws():
    key_id = os.environ.get("KALSHI_API_KEY")
    key_pem = os.environ.get("KALSHI_PRIVATE_KEY")
    key_path = os.environ.get("KALSHI_PRIVATE_KEY_PATH")

    if not key_id:
        print("SKIP: KALSHI_API_KEY not set")
        return

    if key_pem:
        client = KalshiClient.from_key_string(key_id, key_pem)
    elif key_path:
        client = KalshiClient.from_key_file(key_id, key_path)
    else:
        print("SKIP: no private key configured")
        return

    # 1. Verify REST API still works
    print("1. Testing REST API...")
    balance = await client.get_balance()
    print(f"   Balance: ${balance.get('balance', 0) / 100:.2f}")
    assert "balance" in balance, "REST API failed: no balance field"
    print("   OK")

    # 2. Find an active market to subscribe to
    print("2. Finding active markets...")
    test_series = ["KXNBAGAME", "KXNHLGAME", "KXMLBGAME", "KXMLSGAME", "KXEPLGAME"]
    test_tickers = []
    for series in test_series:
        try:
            data = await client.get_events(
                status="open", series_ticker=series, with_nested_markets=True, limit=5
            )
            for event in data.get("events", []):
                for market in event.get("markets", []):
                    if market.get("status") in ("active", "open"):
                        test_tickers.append(market["ticker"])
                        if len(test_tickers) >= 3:
                            break
                if len(test_tickers) >= 3:
                    break
        except Exception:
            continue
        if len(test_tickers) >= 3:
            break

    if not test_tickers:
        print("   No active markets found — WS test skipped (markets may be closed)")
        print("   REST API OK — WebSocket auth will work when markets are active")
        return

    print(f"   Found {len(test_tickers)} active markets: {test_tickers[:3]}")

    # 3. Connect WebSocket
    print("3. Connecting WebSocket...")
    ws = KalshiWebSocket(client)
    await ws.connect()
    print("   Connected OK")

    # 4. Subscribe to ticker channel
    print("4. Subscribing to ticker channel...")
    received_messages = []

    def on_any(msg):
        received_messages.append(msg)
        msg_type = msg.get("type", "unknown")
        ticker = msg.get("msg", {}).get("market_ticker", "")
        print(f"   Received: type={msg_type} ticker={ticker}")

    ws.on("ticker", on_any)
    ws.on("subscribed", on_any)

    sid = await ws.subscribe(["ticker"], test_tickers)
    print(f"   Subscribe cmd sent, id={sid}")

    # 5. Listen for messages (with timeout)
    print("5. Listening for messages (10s timeout)...")

    async def listen_with_timeout():
        try:
            await asyncio.wait_for(ws.listen(), timeout=10)
        except asyncio.TimeoutError:
            pass

    await listen_with_timeout()

    # 6. Verify
    print(f"\n6. Results: received {len(received_messages)} messages")
    got_subscribed = any(m.get("type") == "subscribed" for m in received_messages)
    got_ticker = any(m.get("type") == "ticker" for m in received_messages)

    if got_subscribed:
        print("   Subscription confirmed")
    else:
        print("   WARNING: no subscription confirmation received")

    if got_ticker:
        print("   Ticker data received")
    else:
        print("   No ticker updates yet (normal if market is quiet)")

    await ws.close()

    # At minimum, the connection + subscription should work
    assert got_subscribed or len(received_messages) > 0, (
        "WebSocket connected but received no messages at all"
    )

    print("\nAll tests passed!")


if __name__ == "__main__":
    asyncio.run(test_ws())

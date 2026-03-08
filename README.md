<p align="center">
  <img src="https://getrich.rager.tech/opengraph-image" alt="Rager's Get Rich Slow Scheme" width="600" />
</p>

<h1 align="center">Rager's Get Rich Slow Scheme</h1>

<p align="center">
  <strong>Automated Kalshi sports prediction market scanner</strong><br>
  Buy YES contracts at 88-99c on games that are already decided. Collect $1 at settlement.
</p>

<p align="center">
  <a href="https://getrich.rager.tech">Live Dashboard</a>
</p>

---

## How It Works

The scanner watches live sports games across **NBA, NHL, MLB, NFL, MLS, Premier League, La Liga, NCAA, and UFC** — and buys YES contracts on Kalshi when:

1. **ESPN confirms the game is in its final minutes** (4th quarter <5min, 9th inning, final period, etc.)
2. **The leading team has a comfortable margin** (8+ pts NBA, 2+ goals NHL/soccer, 10+ pts NFL, etc.)
3. **Kalshi YES price is 88-99c** (market already expects this outcome)
4. **Sufficient liquidity** (50+ volume, active bid)

The edge: Kalshi prices lag behind live game state. A team up 15 points with 2 minutes left in the 4th quarter is a near-certainty, but the YES contract might still be at 92c. We buy at 92c, collect $1 at settlement. Small margins, high win rate.

## Architecture

```
                    ┌─────────────────┐
                    │   ESPN API      │  Game scores, periods, clocks
                    │   (poll 10s)    │
                    └────────┬────────┘
                             │
┌────────────────┐   ┌──────▼──────────┐   ┌──────────────────┐
│ Kalshi WebSocket│──▶│    Scanner      │──▶│   SQLite (EFS)   │
│ (real-time)    │   │  (Python/async) │   │ trades, balance, │
│ ticker prices  │   │                 │   │ opportunities    │
│ settlements    │   └──────┬──────────┘   └────────┬─────────┘
└────────────────┘          │                       │
                    ┌───────▼──────────┐   ┌────────▼─────────┐
                    │  Kalshi REST API │   │  FastAPI Backend  │
                    │  (discover 5s)   │   │  /api/*           │
                    │  place orders    │   └────────┬─────────┘
                    └──────────────────┘            │
                                            ┌───────▼─────────┐
                                            │  Next.js Dashboard│
                                            │  getrich.rager.tech│
                                            └─────────────────┘
```

### Real-Time Data Pipeline

- **Kalshi WebSocket** streams live prices (`ticker` channel) and instant settlement notifications (`market_lifecycle_v2`) — no polling delay
- **Kalshi REST API** discovers new markets every 5s and places orders
- **ESPN API** polls game state every 10s for score, period, and clock verification
- **FastAPI** serves dashboard data from SQLite
- **Next.js** renders the live dashboard with P&L tracking, live games, and stretch analysis

### Stretch Opportunity Tracking

The scanner also shadow-tracks "near miss" markets that almost met our criteria (price 85-87c, or slightly lower score lead). These are recorded as **stretch opportunities** with hypothetical P&L — a backtesting mechanism to evaluate whether loosening risk parameters would be profitable.

## Stack

| Component | Technology |
|-----------|-----------|
| Scanner | Python, asyncio, websockets |
| API | FastAPI, SQLAlchemy, SQLite |
| Dashboard | Next.js 16, React, Tailwind CSS |
| Infra | SST v3, AWS ECS (API), Lambda + CloudFront (dashboard), EFS (SQLite) |
| Market Data | Kalshi WebSocket + REST API |
| Game Data | ESPN Scoreboard API |

## Deployment

```bash
# Deploy to AWS
pnpm deploy

# Local development
pnpm dev
```

Requires AWS credentials (`assume smooai.dev`) and Kalshi API keys (`KALSHI_API_KEY`, `KALSHI_PRIVATE_KEY`).

## Dashboard

The dashboard at [getrich.rager.tech](https://getrich.rager.tech) shows:

- **Account Value** — step chart tracking balance over time with each win/loss
- **Live Games** — real-time ESPN game state with Kalshi market prices, color-coded by betting criteria
- **Trade History** — every bet placed with P&L
- **Stretch Analysis** — hypothetical P&L from near-miss opportunities
- **Stats** — win rate, realized P&L, open positions

---

<p align="center">
  <sub>Built by <a href="https://github.com/brentrager">@brentrager</a> with Claude Code</sub>
</p>

<p align="center">
  <a href="https://smoo.ai"><img src="images/smoo-logo.png" alt="Smoo AI" width="100" /></a>
</p>

<p align="center">
  <em>A project by <a href="https://rager.tech">Brent Rager</a> — founder of <a href="https://smoo.ai">Smoo AI</a></em><br>
  <sub><a href="https://smoo.ai">Smoo AI</a> — AI that integrates with everything you build. Agents, CRM, support, and campaigns that work alongside your team.<br>Connect your tools, feed it your knowledge, and let AI work across your entire stack. <a href="https://rager.tech">Let's talk.</a></sub>
</p>

---

<p align="center">
  <img src="https://getrich.rager.tech/opengraph-image" alt="Rager's Get Rich Slow Scheme" width="600" />
</p>

<h1 align="center">Rager's Get Rich Slow Scheme</h1>

<p align="center">
  <strong>Automated Kalshi sports prediction market scanner</strong><br>
  <sub>Buy YES contracts at 88–99¢ on games that are already decided. Collect $1 at settlement.</sub>
</p>

<p align="center">
  <a href="https://getrich.rager.tech"><img src="https://img.shields.io/badge/Live_Dashboard-getrich.rager.tech-F59E0B?style=for-the-badge&logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9IndoaXRlIiBzdHJva2Utd2lkdGg9IjIiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIgc3Ryb2tlLWxpbmVqb2luPSJyb3VuZCI+PHBhdGggZD0iTTEyIDIwVjEwIi8+PHBhdGggZD0iTTE4IDIwVjQiLz48cGF0aCBkPSJNNiAyMHYtNCIvPjwvc3ZnPg==&logoColor=white" alt="Live Dashboard" /></a>
  <a href="https://github.com/brentrager/get-rich-slow/actions"><img src="https://img.shields.io/github/actions/workflow/status/brentrager/get-rich-slow/ci.yml?style=for-the-badge&label=CI&color=22c55e" alt="CI" /></a>
  <a href="https://github.com/brentrager/get-rich-slow"><img src="https://img.shields.io/github/license/brentrager/get-rich-slow?style=for-the-badge&color=64748b" alt="License" /></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/Next.js_16-000000?style=flat-square&logo=next.js&logoColor=white" alt="Next.js" />
  <img src="https://img.shields.io/badge/React-61DAFB?style=flat-square&logo=react&logoColor=black" alt="React" />
  <img src="https://img.shields.io/badge/Tailwind_CSS-06B6D4?style=flat-square&logo=tailwindcss&logoColor=white" alt="Tailwind" />
  <img src="https://img.shields.io/badge/SQLite-003B57?style=flat-square&logo=sqlite&logoColor=white" alt="SQLite" />
  <img src="https://img.shields.io/badge/AWS_ECS-FF9900?style=flat-square&logo=amazonecs&logoColor=white" alt="AWS ECS" />
  <img src="https://img.shields.io/badge/SST_v3-E27152?style=flat-square&logo=sst&logoColor=white" alt="SST" />
  <img src="https://img.shields.io/badge/Docker-2496ED?style=flat-square&logo=docker&logoColor=white" alt="Docker" />
  <img src="https://img.shields.io/badge/WebSockets-010101?style=flat-square&logo=socketdotio&logoColor=white" alt="WebSockets" />
</p>

---

## How It Works

The scanner watches live sports games across **NBA, NHL, MLB, NFL, MLS, Premier League, La Liga, NCAA, and UFC** — and buys YES contracts on Kalshi when:

1. **ESPN confirms the game is in its final minutes** — 4th quarter <5min, 9th inning, final period, etc.
2. **The leading team has a comfortable margin** — 8+ pts NBA, 2+ goals NHL/soccer, 10+ pts NFL, etc.
3. **Kalshi YES price is 88–99¢** — market already expects this outcome
4. **Sufficient liquidity** — 50+ volume, active bid

> **The edge:** Kalshi prices lag behind live game state. A team up 15 points with 2 minutes left in the 4th quarter is a near-certainty, but the YES contract might still be at 92¢. We buy at 92¢, collect $1 at settlement. Small margins, high win rate.

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

| Layer | Source | Method | Purpose |
|:------|:-------|:-------|:--------|
| **Prices** | Kalshi WebSocket | `ticker` channel, real-time | Live YES/NO bid-ask streaming |
| **Settlements** | Kalshi WebSocket | `market_lifecycle_v2` | Instant win/loss detection |
| **Markets** | Kalshi REST API | Poll every 5s | Discover new markets, place orders |
| **Game State** | ESPN API | Poll every 10s | Score, period, clock verification |
| **Dashboard** | FastAPI + Next.js | REST → SSR | P&L tracking, live games, analytics |

### What-If Strategy Tracking

Five shadow strategies run in parallel — evaluating every market against different price thresholds, timing windows, and lead requirements. Each tracks hypothetical P&L so we can backtest parameter changes before risking real capital.

## Dashboard

The dashboard at [getrich.rager.tech](https://getrich.rager.tech) shows:

- **Account Value** — step chart tracking balance over time with each win/loss
- **Live Games** — real-time ESPN game state with Kalshi market prices, color-coded by betting criteria
- **Scanner Config** — live view of all trading parameters and per-sport rules
- **Trade History** — every bet placed with P&L
- **Strategy Comparison** — side-by-side what-if analysis across 5 parameter sets
- **Stats** — win rate, realized P&L, open positions

## Quick Start

```bash
# Local development (Docker)
pnpm dev

# Deploy to AWS
pnpm deploy
```

Requires Kalshi API keys (`KALSHI_API_KEY`, `KALSHI_PRIVATE_KEY`) and AWS credentials.

---

<p align="center">
  <sub>Built by <a href="https://rager.tech">Brent Rager</a> at <a href="https://smoo.ai">Smoo AI</a> with <a href="https://claude.ai/claude-code">Claude Code</a></sub>
</p>

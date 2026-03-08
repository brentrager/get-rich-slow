<p align="center">
  <img src="https://getrich.rager.tech/opengraph-image" alt="Rager's Get Rich Slow Scheme" width="600" />
</p>

<h1 align="center">Rager's Get Rich Slow Scheme</h1>

<p align="center">
  <strong>Automated Kalshi sports prediction market scanner</strong><br>
  <sub>Buy YES contracts at 88–99¢ on games that are already decided. Collect $1 at settlement.</sub>
</p>

<p align="center">
  <a href="https://getrich.rager.tech"><img src="https://img.shields.io/badge/Live_Dashboard-getrich.rager.tech-F59E0B?style=for-the-badge&logoColor=white" alt="Live Dashboard" /></a>
  <a href="https://github.com/brentrager/get-rich-slow/actions"><img src="https://img.shields.io/github/actions/workflow/status/brentrager/get-rich-slow/ci.yml?style=for-the-badge&label=CI&color=22c55e" alt="CI" /></a>
</p>

<table align="center"><tr><td align="center">
  <a href="https://smoo.ai"><img src="images/smoo-logo.png" alt="Smoo AI" width="60" /></a><br>
  <sub><em>A project by <a href="https://rager.tech">Brent Rager</a> — founder of <a href="https://smoo.ai">Smoo AI</a></em></sub><br>
  <sub>AI agents, dev tools, CRM, support &amp; campaigns that integrate with everything you build.<br><a href="https://smoo.ai/work-with-us">Let's talk.</a></sub>
</td></tr></table>

---

## How It Works

The scanner watches live sports games across **NBA, NHL, MLB, NFL, MLS, Premier League, La Liga, NCAA, and UFC** — and buys YES contracts on Kalshi when:

1. **ESPN confirms the game is in its final minutes** — 4th quarter <5min, 9th inning, final period, etc.
2. **The leading team has a comfortable margin** — 8+ pts NBA, 2+ goals NHL/soccer, 10+ pts NFL, etc.
3. **Kalshi YES price is 88–99¢** — market already expects this outcome
4. **Sufficient liquidity** — 50+ volume, active bid

> **The edge:** Kalshi prices lag behind live game state. A team up 15 points with 2 minutes left in the 4th quarter is a near-certainty, but the YES contract might still be at 92¢. We buy at 92¢, collect $1 at settlement. Small margins, high win rate.

## Architecture

```mermaid
graph TD
    ESPN["🏈 ESPN API<br/>scores, periods, clocks · 10s poll"]
    KWS["⚡ Kalshi WebSocket<br/>real-time prices + settlements"]
    KREST["📡 Kalshi REST API<br/>discover markets, place orders · 5s"]
    SCANNER["🐍 Scanner<br/>Python / asyncio"]
    DB["🗄️ SQLite on EFS<br/>trades, balance, opportunities"]
    API["🚀 FastAPI<br/>/api/*"]
    DASH["🖥️ Next.js Dashboard<br/>getrich.rager.tech"]

    ESPN --> SCANNER
    KWS --> SCANNER
    SCANNER --> DB
    SCANNER --> KREST
    DB --> API
    API --> DASH

    style ESPN fill:#1a1a2e,stroke:#FF0000,color:#fff
    style KWS fill:#1a1a2e,stroke:#64748b,color:#fff
    style KREST fill:#1a1a2e,stroke:#64748b,color:#fff
    style SCANNER fill:#1a1a2e,stroke:#F59E0B,color:#fff
    style DB fill:#1a1a2e,stroke:#003B57,color:#fff
    style API fill:#1a1a2e,stroke:#009688,color:#fff
    style DASH fill:#1a1a2e,stroke:#fff,color:#fff
```

### Real-Time Data Pipeline

| Layer | Source | Method | Purpose |
|:------|:-------|:-------|:--------|
| **Prices** | Kalshi WebSocket | `ticker` channel, real-time | Live YES/NO bid-ask streaming |
| **Settlements** | Kalshi WebSocket | `market_lifecycle_v2` | Instant win/loss detection |
| **Markets** | Kalshi REST API | Poll every 5s | Discover new markets, place orders |
| **Game State** | ESPN API | Poll every 10s | Score, period, clock verification |
| **Dashboard** | FastAPI → Next.js | REST | P&L tracking, live games, analytics |

### What-If Strategy Tracking

Five shadow strategies run in parallel — evaluating every market against different price thresholds, timing windows, and lead requirements. Each tracks hypothetical P&L so we can backtest parameter changes before risking real capital.

## Tech Stack

<table>
  <tr>
    <td align="center" width="96"><img src="https://cdn.simpleicons.org/python/3776AB" width="32" /><br><sub>Python 3.12</sub></td>
    <td align="center" width="96"><img src="https://cdn.simpleicons.org/fastapi/009688" width="32" /><br><sub>FastAPI</sub></td>
    <td align="center" width="96"><img src="https://cdn.simpleicons.org/sqlite/003B57" width="32" /><br><sub>SQLite</sub></td>
    <td align="center" width="96"><img src="https://cdn.simpleicons.org/next.js/000000" width="32" /><br><sub>Next.js 16</sub></td>
    <td align="center" width="96"><img src="https://cdn.simpleicons.org/react/61DAFB" width="32" /><br><sub>React 19</sub></td>
    <td align="center" width="96"><img src="https://cdn.simpleicons.org/tailwindcss/06B6D4" width="32" /><br><sub>Tailwind CSS</sub></td>
  </tr>
  <tr>
    <td align="center" width="96"><img src="https://cdn.simpleicons.org/docker/2496ED" width="32" /><br><sub>Docker</sub></td>
    <td align="center" width="96"><img src="https://cdn.simpleicons.org/amazonecs/FF9900" width="32" /><br><sub>AWS ECS</sub></td>
    <td align="center" width="96"><img src="https://cdn.simpleicons.org/sst/E27152" width="32" /><br><sub>SST v3</sub></td>
    <td align="center" width="96"><img src="https://cdn.simpleicons.org/cloudflare/F38020" width="32" /><br><sub>Cloudflare</sub></td>
    <td align="center" width="96"><img src="https://cdn.simpleicons.org/socketdotio/010101" width="32" /><br><sub>WebSockets</sub></td>
    <td align="center" width="96"><img src="https://cdn.simpleicons.org/espn/FF0000" width="32" /><br><sub>ESPN API</sub></td>
  </tr>
</table>

## Dashboard

The dashboard at [getrich.rager.tech](https://getrich.rager.tech) shows:

- **Account Value** — step chart tracking balance over time with each win/loss
- **Live Games** — real-time ESPN game state with Kalshi market prices, color-coded by betting criteria
- **Scanner Config** — live view of all trading parameters and per-sport rules
- **Trade History** — every bet placed with P&L
- **Strategy Comparison** — side-by-side what-if analysis across 5 parameter sets
- **Stats** — win rate, realized P&L, open positions

## Deployment

### Prerequisites

- [SST v3](https://sst.dev) + [pnpm](https://pnpm.io)
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- AWS account (us-east-2)
- Cloudflare account (DNS)
- [Kalshi API keys](https://kalshi.com/sign-up/api)

### Secrets

SST secrets must be set before first deploy:

```bash
npx sst secret set KalshiApiKey "your-kalshi-api-key-id"
npx sst secret set KalshiPrivateKey "-----BEGIN RSA PRIVATE KEY-----\n..."
npx sst secret set DashboardPassword "your-dashboard-password"
npx sst secret set ApiToken "your-api-bearer-token"
```

### Infrastructure

SST provisions everything in `sst.config.ts`:

| Resource | What | Notes |
|:---------|:-----|:------|
| **VPC** | Networking with NAT | EC2-based NAT to save cost |
| **ECS Cluster** | Container orchestration | Single service runs API + Scanner |
| **EFS** | Persistent storage | SQLite database lives here |
| **S3 Bucket** | DB backups | Periodic SQLite snapshots |
| **Next.js (SST)** | Dashboard | Lambda + CloudFront via OpenNext |
| **Cloudflare DNS** | Domain routing | `getrich.rager.tech` + `getrich-api.rager.tech` |

### Commands

```bash
# Deploy to AWS (requires AWS creds + Cloudflare token in .envrc)
pnpm deploy

# Local development (Docker Compose)
pnpm dev

# Run API locally (without Docker)
pnpm dev:api

# Tear down all infrastructure
pnpm deploy:remove
```

### CLI

A react-ink TUI for managing the scanner from the terminal:

```bash
# View current config (interactive TUI)
pnpm cli config

# Update a config value
pnpm cli config set trading.min_yes_price 90

# View stats / trades
pnpm cli stats
pnpm cli trades

# JSON output for piping / automation
pnpm cli stats --json
pnpm cli trades --json | jq '.trades[0]'
```

Requires `API_TOKEN` env var (or `--token` flag). Set `GETRICH_API_URL` to override the default API endpoint.

### Runtime Configuration (API)

The scanner reads config from the database at startup. Update settings via the CLI above or the API directly:

```bash
# Update a config value (requires API_TOKEN)
curl -X PUT https://getrich-api.rager.tech/api/config \
  -H "Authorization: Bearer $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"key": "trading.min_yes_price", "value": "92"}'

# View current config
curl https://getrich-api.rager.tech/api/config \
  -H "Authorization: Bearer $API_TOKEN"
```

## Development

```bash
# Format + lint Python
uv run ruff format . && uv run ruff check . && uv run ty check

# Format + lint TypeScript
cd dashboard && pnpm oxfmt . && pnpm oxlint

# Build dashboard
cd dashboard && pnpm build
```

A pre-commit hook runs automatically: formats Python (ruff) and TypeScript (oxfmt), then type-checks with ty.

---

<p align="center">
  <sub>Built by <a href="https://rager.tech">Brent Rager</a> at <a href="https://smoo.ai">Smoo AI</a> with <a href="https://claude.ai/claude-code">Claude Code</a></sub>
</p>

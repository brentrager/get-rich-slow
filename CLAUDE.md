# Predictions Project

Kalshi sports prediction market scanner. Buys YES contracts at 88-99c on games that are nearly decided, collects $1 at settlement.

## Stack
- **Python**: FastAPI + SQLAlchemy + SQLite (api.py, scanner.py, espn.py, db.py)
- **Dashboard**: Next.js 16 (dashboard/)
- **Infra**: SST v3 on AWS (sst.config.ts) — ECS for API, Lambda/CloudFront for dashboard, EFS for SQLite

## Tooling
- **Python**: uv (not pip), ruff (not black), ty (not mypy)
- **JS/TS**: pnpm, oxfmt (4 spaces), oxlint (not eslint)
- **No dev server**: Use Docker for everything locally

## Deploy
```bash
# Deploy to AWS (requires `assume smooai.dev` for AWS auth)
pnpm deploy

# Or manually:
rm -rf dashboard/.open-next dashboard/.next && AWS_PROFILE=smooai.dev npx sst deploy
```

## Runtime Config (Tunable Parameters)

Config is stored in SQLite (`config` table) and read by the scanner every loop iteration. Changes take effect within 5 seconds without redeploying.

### View current config
```bash
uv run python config_cli.py
```

### Update config via CLI (local — requires DB access)
```bash
uv run python config_cli.py set KEY VALUE
uv run python config_cli.py delete KEY     # revert to default
```

### Update config via API (remote — works from anywhere)
```bash
curl -X PUT https://getrich-api.rager.tech/api/config \
  -H "Authorization: Bearer $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"key": "min_yes_price", "value": "88"}'
```

### Available config keys

**Trading parameters:**
| Key | Default | Description |
|-----|---------|-------------|
| `min_yes_price` | 92 | Minimum YES ask price in cents to place a bet |
| `max_bet_cents` | 500 | Maximum cost per bet in cents |
| `max_positions` | 20 | Maximum concurrent open positions |
| `min_volume` | 50 | Minimum market volume for liquidity |
| `stretch_price_min` | 85 | Minimum YES price for stretch (shadow) tracking |

**Per-sport score leads** (`lead:{sport_path}`):
| Key | Default | Description |
|-----|---------|-------------|
| `lead:basketball/nba` | 8 | Min point lead for NBA |
| `lead:basketball/mens-college-basketball` | 8 | Min point lead for NCAAMB |
| `lead:hockey/nhl` | 2 | Min goal lead for NHL |
| `lead:football/nfl` | 10 | Min point lead for NFL |
| `lead:football/college-football` | 10 | Min point lead for NCAAFB |
| `lead:baseball/mlb` | 3 | Min run lead for MLB |
| `lead:soccer/eng.1` | 2 | Min goal lead for EPL |
| `lead:soccer/esp.1` | 2 | Min goal lead for La Liga |
| `lead:soccer/usa.1` | 2 | Min goal lead for MLS |
| `lead:mma/ufc` | 0 | Min score lead for UFC |

**Per-sport end-of-game timing** (`final_seconds:{sport_path}`):
| Key | Default | Description |
|-----|---------|-------------|
| `final_seconds:basketball/nba` | 300 | Clock <= 5:00 in final quarter |
| `final_seconds:hockey/nhl` | 300 | Clock <= 5:00 in final period |
| `final_seconds:football/nfl` | 300 | Clock <= 5:00 in 4th quarter |
| `final_seconds:soccer/eng.1` | 4800 | Clock >= 80th minute |
| `final_seconds:soccer/esp.1` | 4800 | Clock >= 80th minute |
| `final_seconds:soccer/usa.1` | 4800 | Clock >= 80th minute |

Note: For countdown sports (NBA, NHL, NFL, etc.) the value means "clock must be <= X seconds". For count-up sports (soccer) it means "clock must be >= X seconds".

## Key Files
- `sst.config.ts` — SST infra (VPC, ECS, EFS, S3, secrets)
- `scanner.py` — Main scanner with WebSocket + ESPN integration
- `api.py` — FastAPI backend serving dashboard + config endpoints
- `db.py` — SQLAlchemy models + config helpers
- `espn.py` — ESPN live game data
- `kalshi_client.py` — Kalshi REST + WebSocket client
- `config_cli.py` — CLI to view/update runtime config
- `dashboard/` — Next.js app (read-only display)

## Architecture
- Scanner runs 4 concurrent async loops: ESPN poll (10s), Kalshi API scan (5s), WebSocket listener (real-time prices + settlements), DB backup (30m)
- Config stored in SQLite `config` table, read each scan loop — changes take effect immediately
- Dashboard is read-only, all config changes go through CLI or Bearer-protected PUT endpoint

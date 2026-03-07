#!/bin/bash
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

# Kill any existing processes on our ports
lsof -ti:8000 | xargs kill -9 2>/dev/null || true
lsof -ti:3777 | xargs kill -9 2>/dev/null || true
pkill -f "scanner.py" 2>/dev/null || true

# Clean stale Next.js lock
rm -f "$ROOT/dashboard/.next/dev/lock"

# Start Postgres if not running
docker compose up -d 2>/dev/null

echo "Starting FastAPI (port 8000)..."
uv run uvicorn api:app --reload --port 8000 &
API_PID=$!

echo "Starting Next.js dashboard (port 3777)..."
(cd "$ROOT/dashboard" && npm run dev) &
NEXT_PID=$!

echo "Starting scanner (dry run)..."
uv run python "$ROOT/scanner.py" &
SCANNER_PID=$!

echo ""
echo "==================================="
echo "  Dashboard: http://localhost:3777"
echo "  API:       http://localhost:8000"
echo "  Scanner:   running (PID $SCANNER_PID)"
echo "==================================="
echo ""

trap "kill $API_PID $NEXT_PID $SCANNER_PID 2>/dev/null; exit" INT TERM
wait

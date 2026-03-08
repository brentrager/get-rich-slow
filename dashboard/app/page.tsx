"use client";

import { useEffect, useState } from "react";
import { Tweet } from "react-tweet";
import { login, checkAuth } from "./actions";

const API = (
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
).replace(/\/+$/, "");

interface Stats {
  total_trades: number;
  live_trades: number;
  dry_run_trades: number;
  total_cost_cents: number;
  total_potential_profit_cents: number;
  realized_pnl_cents: number;
  wins: number;
  losses: number;
  win_rate: number;
  total_scans: number;
  total_opportunities: number;
  balance_cents: number;
  portfolio_value_cents: number;
  open_positions: number;
  open_cost_cents: number;
  open_potential_profit_cents: number;
}

interface Trade {
  id: number;
  placed_at: string;
  ticker: string;
  title: string;
  side: string;
  count: number;
  yes_price: number;
  cost_cents: number;
  potential_profit_cents: number;
  status: string;
  pnl_cents: number | null;
  dry_run: boolean;
  error: string | null;
}

interface Opportunity {
  id: number;
  found_at: string;
  ticker: string;
  title: string;
  yes_sub_title: string;
  yes_bid: number;
  yes_ask: number;
  spread: number;
  volume: number;
  series_ticker: string;
}

interface BalanceSnapshot {
  recorded_at: string;
  balance_cents: number;
  portfolio_value_cents: number;
}

interface KalshiMarket {
  ticker: string;
  team: string;
  yes_sub_title: string;
  yes_bid: number;
  yes_ask: number;
  volume: number;
}

interface LiveGame {
  espn_id: string;
  sport: string;
  series: string;
  home_team: string;
  away_team: string;
  home_score: number;
  away_score: number;
  period: number;
  display_clock: string;
  clock_seconds: number;
  state: string;
  is_final_minutes: boolean;
  is_target: boolean;
  is_watching: boolean;
  has_bet: boolean;
  score_diff: number;
  min_score_lead: number;
  final_period: number;
  kalshi_markets: KalshiMarket[];
}

interface SportConfig {
  sport_path: string;
  name: string;
  kalshi_series: string;
  final_period: number;
  min_score_lead: number;
  stretch_score_lead: number;
  clock_direction: "down" | "up" | "none";
  final_minutes_desc: string;
  final_minutes_seconds: number | null;
}

interface AppConfig {
  trading: {
    min_yes_price: number;
    max_bet_cents: number;
    max_positions: number;
    min_volume: number;
    dry_run: boolean;
  };
  stretch: {
    price_min: number;
  };
  polling: {
    espn_interval_s: number;
    kalshi_scan_interval_s: number;
    kalshi_ws: boolean;
    db_backup_interval_s: number;
  };
  sports: SportConfig[];
}

interface StrategySetStats {
  label: string;
  total: number;
  wins: number;
  losses: number;
  open: number;
  win_rate: number;
  hypothetical_pnl_cents: number;
  by_reason: Record<
    string,
    { total: number; wins: number; losses: number; pnl_cents: number }
  >;
}

interface StretchStats {
  total: number;
  wins: number;
  losses: number;
  open: number;
  win_rate: number;
  hypothetical_pnl_cents: number;
  by_reason: Record<
    string,
    { total: number; wins: number; losses: number; pnl_cents: number }
  >;
  strategies: Record<string, StrategySetStats>;
}

function cents(c: number): string {
  return `$${(c / 100).toFixed(2)}`;
}

function formatGameTime(g: LiveGame): string {
  const sport = g.sport;
  const p = g.period;
  const clock = g.display_clock;

  // Format clock: "33.2" → "0:33", "11:48" stays, "0.0"/"0:00" → "End"
  const clockNum = parseFloat(clock);
  let timeStr: string;
  if (clock.includes(":")) {
    timeStr = clockNum === 0 ? "End" : clock;
  } else {
    // seconds only (e.g. "33.2")
    const secs = Math.floor(clockNum);
    timeStr = secs === 0 ? "End" : `0:${secs.toString().padStart(2, "0")}`;
  }

  if (sport.startsWith("basketball/")) {
    if (g.final_period === 2) {
      // College basketball: 2 halves
      const label = p > 2 ? "OT" : p === 1 ? "1st Half" : "2nd Half";
      return `${label} · ${timeStr}`;
    }
    const label = p > g.final_period ? "OT" : `Q${p}`;
    return `${label} · ${timeStr}`;
  }
  if (sport.startsWith("hockey/")) {
    const ord = p === 1 ? "1st" : p === 2 ? "2nd" : p === 3 ? "3rd" : "OT";
    return `${ord} · ${timeStr}`;
  }
  if (sport.startsWith("football/")) {
    const label = p > g.final_period ? "OT" : `Q${p}`;
    return `${label} · ${timeStr}`;
  }
  if (sport.startsWith("baseball/")) {
    const ord = p === 1 ? "1st" : p === 2 ? "2nd" : p === 3 ? "3rd" : `${p}th`;
    return `${ord} inning`;
  }
  if (sport.startsWith("soccer/")) {
    // ESPN reports match minute for soccer (e.g. "76" = 76th minute)
    const minute = Math.floor(clockNum);
    return minute > 0 ? `${minute}'` : p === 1 ? "1st Half" : "2nd Half";
  }
  if (sport.startsWith("mma/")) {
    return `R${p} · ${timeStr}`;
  }
  return `P${p} · ${timeStr}`;
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function sportLabel(sport: string): string {
  const map: Record<string, string> = {
    "basketball/nba": "NBA",
    "hockey/nhl": "NHL",
    "football/nfl": "NFL",
    "baseball/mlb": "MLB",
    "basketball/mens-college-basketball": "NCAAM",
    "football/college-football": "NCAAF",
    "mma/ufc": "UFC",
    "soccer/eng.1": "EPL",
    "soccer/esp.1": "La Liga",
    "soccer/usa.1": "MLS",
  };
  return map[sport] || sport;
}

function StatCard({
  label,
  value,
  sub,
  delay,
}: {
  label: string;
  value: string;
  sub?: string;
  delay?: number;
}) {
  return (
    <div
      className="animate-fade-in gold-glow bg-zinc-900/80 border border-amber-900/30 rounded-xl p-5 backdrop-blur-sm"
      style={{ animationDelay: `${delay || 0}ms` }}
    >
      <div className="text-amber-600 text-sm mb-1 font-medium">{label}</div>
      <div className="text-2xl font-bold text-amber-100">{value}</div>
      {sub && <div className="text-amber-700 text-sm mt-1">{sub}</div>}
    </div>
  );
}

function StatusBadge({ status, dryRun }: { status: string; dryRun: boolean }) {
  if (dryRun)
    return (
      <span className="px-2 py-0.5 text-xs rounded-full bg-zinc-700 text-zinc-300 border border-zinc-600">
        DRY RUN
      </span>
    );
  const colors: Record<string, string> = {
    placed: "bg-amber-900/30 text-amber-300 border-amber-700/50",
    filled: "bg-yellow-900/30 text-yellow-300 border-yellow-700/50",
    settled_win: "bg-green-900/30 text-green-300 border-green-700/50",
    settled_loss: "bg-red-900/30 text-red-300 border-red-700/50",
    error: "bg-red-900/30 text-red-300 border-red-700/50",
  };
  return (
    <span
      className={`px-2 py-0.5 text-xs rounded-full border ${colors[status] || "bg-zinc-700 text-zinc-300 border-zinc-600"}`}
    >
      {status.replace("_", " ").toUpperCase()}
    </span>
  );
}

function PnlChart({
  trades,
  balanceCents,
  portfolioCents,
}: {
  trades: Trade[];
  balanceCents: number;
  portfolioCents: number;
}) {
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);

  const totalNow = balanceCents + portfolioCents;

  // Build timeline: total account value over time
  // Start = current total minus realized P&L (what we deposited)
  const settledTrades = trades
    .filter((t) => !t.dry_run && t.pnl_cents !== null && t.placed_at)
    .sort(
      (a, b) =>
        new Date(a.placed_at).getTime() - new Date(b.placed_at).getTime(),
    );

  let totalPnl = 0;
  for (const t of settledTrades) totalPnl += t.pnl_cents!;

  const startingBalance = totalNow - totalPnl;

  // Build step data: evenly-spaced points so steps are always visible
  // Each settlement gets equal horizontal space
  const steps: { value: number; label: string; date: Date | null }[] = [
    {
      value: startingBalance,
      label: "Start",
      date:
        settledTrades.length > 0 ? new Date(settledTrades[0].placed_at) : null,
    },
  ];
  let runningValue = startingBalance;
  for (const t of settledTrades) {
    runningValue += t.pnl_cents!;
    const result = t.pnl_cents! >= 0 ? "WIN" : "LOSS";
    steps.push({
      value: runningValue,
      label: `${result} ${t.pnl_cents! >= 0 ? "+" : ""}${(t.pnl_cents! / 100).toFixed(2)}`,
      date: new Date(t.placed_at),
    });
  }
  steps.push({ value: totalNow, label: "Now", date: new Date() });

  // Y-axis: center the data vertically
  const values = steps.map((d) => d.value);
  const rawMin = Math.min(...values);
  const rawMax = Math.max(...values);
  const dataRange = rawMax - rawMin || 1;
  const padding = dataRange * 0.35;
  const yMin = rawMin - padding;
  const yMax = rawMax + padding;
  const range = yMax - yMin;

  const w = 800;
  const h = 200;
  const padLeft = 60;
  const padRight = 12;
  const padTop = 14;
  const padBottom = 24;
  const chartW = w - padLeft - padRight;
  const chartH = h - padTop - padBottom;

  const toY = (val: number) =>
    padTop + chartH - ((val - yMin) / range) * chartH;

  // Evenly space steps across chart width, with step-function shape
  const stepCount = steps.length;
  const points: {
    x: number;
    y: number;
    value: number;
    label: string;
    date: Date | null;
  }[] = [];
  for (let i = 0; i < stepCount; i++) {
    const x = padLeft + (i / (stepCount - 1)) * chartW;
    const y = toY(steps[i].value);
    // For step chart: draw horizontal line from previous x to this x at previous y, then vertical step
    if (i > 0) {
      points.push({
        x,
        y: toY(steps[i - 1].value),
        value: steps[i - 1].value,
        label: "",
        date: null,
      });
    }
    points.push({
      x,
      y,
      value: steps[i].value,
      label: steps[i].label,
      date: steps[i].date,
    });
  }

  const line = points
    .map((p, i) => `${i === 0 ? "M" : "L"}${p.x},${p.y}`)
    .join(" ");
  const baseY = toY(startingBalance);
  const area = `${line} L${points[points.length - 1].x},${baseY} L${points[0].x},${baseY} Z`;

  // X-axis labels from step dates
  const timeLabels: { x: number; label: string }[] = [];
  for (let i = 0; i < points.length; i++) {
    if (points[i].label && points[i].date) {
      const d = points[i].date!;
      const label = `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${d.getMinutes().toString().padStart(2, "0")}`;
      timeLabels.push({ x: points[i].x, label });
    }
  }

  const findClosest = (mouseX: number) => {
    let closest = 0;
    let closestDist = Infinity;
    for (let i = 0; i < points.length; i++) {
      const dist = Math.abs(points[i].x - mouseX);
      if (dist < closestDist) {
        closestDist = dist;
        closest = i;
      }
    }
    return closest;
  };

  const hp = hoverIdx !== null ? points[hoverIdx] : null;

  return (
    <div className="animate-fade-in gold-glow bg-zinc-900/80 border border-amber-900/30 rounded-xl p-5 mb-8 backdrop-blur-sm">
      <div className="flex justify-between items-center mb-3">
        <h2 className="text-sm text-amber-600 font-medium">Account Value</h2>
        <div className="flex items-center gap-4 text-sm">
          <span className="text-zinc-500 font-mono">
            {cents(startingBalance)}
          </span>
          <span className="text-amber-200 font-bold font-mono">
            {cents(totalNow)}
          </span>
          {totalPnl !== 0 && (
            <span
              className={`font-bold font-mono px-2 py-0.5 rounded ${totalPnl > 0 ? "text-green-400 bg-green-900/30" : "text-red-400 bg-red-900/30"}`}
            >
              {totalPnl > 0 ? "+" : ""}
              {cents(totalPnl)}
            </span>
          )}
        </div>
      </div>
      <svg
        viewBox={`0 0 ${w} ${h}`}
        className="w-full h-48"
        onMouseMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          setHoverIdx(findClosest(((e.clientX - rect.left) / rect.width) * w));
        }}
        onMouseLeave={() => setHoverIdx(null)}
        onTouchMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          const touch = e.touches[0];
          setHoverIdx(
            findClosest(((touch.clientX - rect.left) / rect.width) * w),
          );
        }}
        onTouchEnd={() => setHoverIdx(null)}
      >
        <defs>
          <linearGradient id="pnlGrad" x1="0" y1="0" x2="0" y2="1">
            <stop
              offset="0%"
              stopColor={totalPnl >= 0 ? "#4ade80" : "#f87171"}
              stopOpacity="0.3"
            />
            <stop
              offset="100%"
              stopColor={totalPnl >= 0 ? "#4ade80" : "#f87171"}
              stopOpacity="0.02"
            />
          </linearGradient>
        </defs>

        {/* Starting balance baseline */}
        <line
          x1={padLeft}
          y1={baseY}
          x2={w - padRight}
          y2={baseY}
          stroke="#78716c"
          strokeWidth="1"
          strokeDasharray="4,4"
        />
        <text
          x={padLeft - 6}
          y={baseY + 4}
          textAnchor="end"
          fill="#78716c"
          fontSize="10"
          fontFamily="monospace"
        >
          {cents(startingBalance)}
        </text>

        {/* Current value level */}
        {totalPnl !== 0 && (
          <>
            <line
              x1={padLeft}
              y1={toY(totalNow)}
              x2={w - padRight}
              y2={toY(totalNow)}
              stroke={totalPnl >= 0 ? "#4ade80" : "#f87171"}
              strokeWidth="0.5"
              strokeDasharray="2,4"
              opacity="0.5"
            />
            <text
              x={padLeft - 6}
              y={toY(totalNow) + 4}
              textAnchor="end"
              fill={totalPnl >= 0 ? "#4ade80" : "#f87171"}
              fontSize="10"
              fontWeight="bold"
              fontFamily="monospace"
            >
              {cents(totalNow)}
            </text>
          </>
        )}

        {/* X-axis time labels */}
        {timeLabels.map(({ x, label }, i) => (
          <text
            key={i}
            x={x}
            y={h - 4}
            textAnchor="middle"
            fill="#78716c"
            fontSize="9"
            fontFamily="monospace"
          >
            {label}
          </text>
        ))}

        {/* Area + line */}
        <path d={area} fill="url(#pnlGrad)" />
        <path
          d={line}
          fill="none"
          stroke={totalPnl >= 0 ? "#4ade80" : "#f87171"}
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {/* Settlement event dots */}
        {points
          .filter((p) => p.label && !["Start", "Now", ""].includes(p.label))
          .map((p, i) => (
            <circle
              key={i}
              cx={p.x}
              cy={p.y}
              r="4"
              fill={p.value >= startingBalance ? "#4ade80" : "#f87171"}
              stroke="#000"
              strokeWidth="1"
            />
          ))}

        {/* End dot */}
        {hoverIdx === null && points.length > 0 && (
          <circle
            cx={points[points.length - 1].x}
            cy={points[points.length - 1].y}
            r="4"
            fill={totalPnl >= 0 ? "#4ade80" : "#f87171"}
            className="animate-pulse"
          />
        )}

        {/* Hover tooltip */}
        {hp && (
          <>
            <line
              x1={hp.x}
              y1={padTop}
              x2={hp.x}
              y2={padTop + chartH}
              stroke="#d4a017"
              strokeWidth="1"
              strokeDasharray="3,3"
              opacity="0.5"
            />
            <circle
              cx={hp.x}
              cy={hp.y}
              r="5"
              fill="#f0d060"
              stroke="#000"
              strokeWidth="1.5"
            />
            <rect
              x={hp.x < w / 2 ? hp.x + 10 : hp.x - 130}
              y={Math.max(hp.y - 30, padTop)}
              width="120"
              height="36"
              rx="5"
              fill="#1c1917"
              stroke="#92400e"
              strokeWidth="0.5"
              opacity="0.95"
            />
            <text
              x={hp.x < w / 2 ? hp.x + 18 : hp.x - 122}
              y={Math.max(hp.y - 14, padTop + 16)}
              fill="#fbbf24"
              fontSize="12"
              fontWeight="bold"
              fontFamily="monospace"
            >
              {cents(hp.value)}
            </text>
            <text
              x={hp.x < w / 2 ? hp.x + 18 : hp.x - 122}
              y={Math.max(hp.y + 2, padTop + 32)}
              fill={hp.value >= startingBalance ? "#4ade80" : "#f87171"}
              fontSize="10"
              fontFamily="monospace"
            >
              {hp.label ||
                `${hp.value >= startingBalance ? "+" : ""}${cents(hp.value - startingBalance)}`}
            </text>
          </>
        )}
      </svg>
    </div>
  );
}

function LiveGamesPanel({ games }: { games: LiveGame[] }) {
  if (games.length === 0) {
    return (
      <div className="animate-fade-in bg-zinc-900/80 border border-amber-900/30 rounded-xl p-5 mb-8 backdrop-blur-sm">
        <h2 className="text-sm text-amber-600 font-medium mb-3">Live Games</h2>
        <p className="text-amber-900 text-sm">No live games right now.</p>
      </div>
    );
  }

  return (
    <div className="animate-fade-in bg-zinc-900/80 border border-amber-900/30 rounded-xl p-5 mb-8 backdrop-blur-sm">
      <div className="flex items-center gap-3 mb-4">
        <h2 className="text-sm text-amber-600 font-medium">Live Games</h2>
        <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
        <span className="text-xs text-zinc-500">{games.length} active</span>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {[...games]
          .sort((a, b) => {
            // Bet placed first, then targets, then watching, then live, then pre
            if (a.has_bet !== b.has_bet) return a.has_bet ? -1 : 1;
            if (a.is_target !== b.is_target) return a.is_target ? -1 : 1;
            if (a.is_watching !== b.is_watching) return a.is_watching ? -1 : 1;
            if (a.state !== b.state) return a.state === "in" ? -1 : 1;
            return 0;
          })
          .map((g) => {
            // Find the leading team's Kalshi market
            const leadingTeam =
              g.home_score >= g.away_score ? g.home_team : g.away_team;
            const trailingTeam =
              g.home_score >= g.away_score ? g.away_team : g.home_team;
            const leadingMarket = g.kalshi_markets?.find(
              (m) => m.team === leadingTeam,
            );
            const trailingMarket = g.kalshi_markets?.find(
              (m) => m.team === trailingTeam,
            );

            return (
              <div
                key={g.espn_id}
                className={`border rounded-lg p-3 transition-all ${
                  g.has_bet
                    ? "border-green-500/50 bg-green-950/20"
                    : g.is_target
                      ? "border-amber-500/50 bg-amber-950/20 gold-glow"
                      : g.is_watching
                        ? "border-amber-800/40 bg-amber-950/10"
                        : "border-zinc-800 bg-zinc-900/50"
                }`}
              >
                <div className="flex justify-between items-start mb-2">
                  <span className="text-xs font-medium text-amber-600">
                    {sportLabel(g.sport)}
                  </span>
                  <div className="flex items-center gap-1.5">
                    {g.has_bet && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-green-600/20 text-green-400 border border-green-600/30 font-bold">
                        BET PLACED
                      </span>
                    )}
                    {g.is_target && !g.has_bet && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-600/20 text-amber-400 border border-amber-600/30 font-bold">
                        TARGET
                      </span>
                    )}
                    {g.is_watching && !g.is_target && !g.has_bet && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-900/20 text-amber-600 border border-amber-800/30">
                        WATCHING
                      </span>
                    )}
                    {g.state === "in" ? (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-900/30 text-red-400 border border-red-700/30">
                        LIVE
                      </span>
                    ) : (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 border border-zinc-700">
                        PRE
                      </span>
                    )}
                  </div>
                </div>
                <div className="flex justify-between items-center">
                  <div className="space-y-1">
                    <div
                      className={`text-sm font-medium ${g.away_score > g.home_score ? "text-amber-200" : "text-zinc-400"}`}
                    >
                      {g.away_team}
                    </div>
                    <div
                      className={`text-sm font-medium ${g.home_score > g.away_score ? "text-amber-200" : "text-zinc-400"}`}
                    >
                      {g.home_team}
                    </div>
                  </div>
                  <div className="text-right space-y-1">
                    <div className="flex items-center gap-2 justify-end">
                      {g.away_team === leadingTeam && leadingMarket && (
                        <span className="text-[10px] text-green-400 font-mono">
                          {leadingMarket.yes_ask}¢
                        </span>
                      )}
                      {g.away_team === trailingTeam && trailingMarket && (
                        <span className="text-[10px] text-zinc-600 font-mono">
                          {trailingMarket.yes_ask}¢
                        </span>
                      )}
                      <span
                        className={`text-sm font-bold ${g.away_score > g.home_score ? "text-amber-100" : "text-zinc-500"}`}
                      >
                        {g.away_score}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 justify-end">
                      {g.home_team === leadingTeam && leadingMarket && (
                        <span className="text-[10px] text-green-400 font-mono">
                          {leadingMarket.yes_ask}¢
                        </span>
                      )}
                      {g.home_team === trailingTeam && trailingMarket && (
                        <span className="text-[10px] text-zinc-600 font-mono">
                          {trailingMarket.yes_ask}¢
                        </span>
                      )}
                      <span
                        className={`text-sm font-bold ${g.home_score > g.away_score ? "text-amber-100" : "text-zinc-500"}`}
                      >
                        {g.home_score}
                      </span>
                    </div>
                  </div>
                </div>
                {g.state === "in" && (
                  <div className="mt-2 text-xs text-amber-700">
                    {formatGameTime(g)}
                  </div>
                )}
              </div>
            );
          })}
      </div>
    </div>
  );
}

function LoginForm({ onLogin }: { onLogin: () => void }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState(false);
  const [config, setConfig] = useState<AppConfig | null>(null);

  useEffect(() => {
    fetch(`${API}/api/config`)
      .then((r) => (r.ok ? r.json() : null))
      .then(setConfig)
      .catch(() => {});
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const result = await login(password);
    if (result.success) {
      onLogin();
    } else {
      setError(true);
      setPassword("");
    }
  };

  return (
    <div className="min-h-screen bg-black text-white p-6">
      <div className="max-w-7xl mx-auto">
        <div className="flex items-center justify-between mb-8 animate-fade-in">
          <div>
            <h1 className="text-4xl font-black gold-shimmer tracking-tight">
              Rager's Get Rich Slow Scheme
            </h1>
            <p className="text-amber-800 text-sm mt-1">
              Kalshi Sports Market Scanner
            </p>
          </div>
        </div>

        {/* Strategy + Config + Inspiration */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8 animate-fade-in">
          <div className="lg:col-span-2 space-y-6">
            <div className="bg-zinc-900/60 border border-amber-900/20 rounded-xl p-6">
              <h2 className="text-lg font-bold text-amber-400 mb-3">
                The Strategy
              </h2>
              <div className="space-y-2 text-sm text-zinc-400">
                <p>
                  Buy{" "}
                  <span className="text-amber-300 font-semibold">
                    YES contracts at 92c+
                  </span>{" "}
                  on Kalshi sports markets when a team is winning by a
                  comfortable margin in the final minutes of the game.
                </p>
                <p>
                  ESPN live data confirms the game state — we only bet when the
                  outcome is nearly certain. Each $20 bet earns $0.20–$1.60
                  profit in minutes.
                </p>
                <div className="grid grid-cols-2 gap-3 mt-4">
                  <div className="bg-black/40 rounded-lg p-3 border border-amber-900/10">
                    <div className="text-amber-600 text-xs uppercase tracking-wider mb-1">
                      Filters
                    </div>
                    <div className="text-zinc-300 text-xs leading-relaxed">
                      YES price ≥ 92c
                      <br />
                      Final period only
                      <br />
                      ESPN-verified score lead
                      <br />
                      Volume ≥ 50 contracts
                    </div>
                  </div>
                  <div className="bg-black/40 rounded-lg p-3 border border-amber-900/10">
                    <div className="text-amber-600 text-xs uppercase tracking-wider mb-1">
                      Risk Controls
                    </div>
                    <div className="text-zinc-300 text-xs leading-relaxed">
                      Max $20 per bet
                      <br />
                      Max 10 concurrent positions
                      <br />
                      No duplicate event bets
                      <br />
                      Min score lead by sport
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Scanner Configuration */}
            {config && (
              <div className="bg-zinc-900/80 border border-amber-900/30 rounded-xl p-5 backdrop-blur-sm">
                <h2 className="text-sm text-amber-600 font-medium mb-4">
                  Scanner Configuration
                </h2>
                <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-5">
                  <div className="bg-black/30 rounded-lg p-3 border border-zinc-800">
                    <div className="text-zinc-500 text-xs">Min YES Price</div>
                    <div className="text-amber-200 text-lg font-bold font-mono">
                      {config.trading.min_yes_price}¢
                    </div>
                  </div>
                  <div className="bg-black/30 rounded-lg p-3 border border-zinc-800">
                    <div className="text-zinc-500 text-xs">Max Bet</div>
                    <div className="text-amber-200 text-lg font-bold font-mono">
                      {cents(config.trading.max_bet_cents)}
                    </div>
                  </div>
                  <div className="bg-black/30 rounded-lg p-3 border border-zinc-800">
                    <div className="text-zinc-500 text-xs">Max Positions</div>
                    <div className="text-amber-200 text-lg font-bold font-mono">
                      {config.trading.max_positions}
                    </div>
                  </div>
                  <div className="bg-black/30 rounded-lg p-3 border border-zinc-800">
                    <div className="text-zinc-500 text-xs">Min Volume</div>
                    <div className="text-amber-200 text-lg font-bold font-mono">
                      {config.trading.min_volume}
                    </div>
                  </div>
                  <div className="bg-black/30 rounded-lg p-3 border border-zinc-800">
                    <div className="text-zinc-500 text-xs">Mode</div>
                    <div
                      className={`text-lg font-bold ${config.trading.dry_run ? "text-yellow-400" : "text-green-400"}`}
                    >
                      {config.trading.dry_run ? "DRY RUN" : "LIVE"}
                    </div>
                  </div>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-zinc-500 border-b border-zinc-800">
                        <th className="text-left py-2 pr-4">Sport</th>
                        <th className="text-left py-2 pr-4">Kalshi Series</th>
                        <th className="text-center py-2 pr-4">Final Period</th>
                        <th className="text-center py-2 pr-4">End-of-Game</th>
                        <th className="text-center py-2 pr-4">Min Lead</th>
                      </tr>
                    </thead>
                    <tbody>
                      {config.sports.map((s) => (
                        <tr
                          key={s.sport_path}
                          className="border-b border-zinc-800/50 hover:bg-zinc-800/30"
                        >
                          <td className="py-2 pr-4 text-amber-200 font-medium">
                            {s.name}
                          </td>
                          <td className="py-2 pr-4 text-zinc-400 font-mono">
                            {s.kalshi_series}
                          </td>
                          <td className="py-2 pr-4 text-center text-zinc-300">
                            {s.clock_direction === "none"
                              ? `Inning ${s.final_period}`
                              : `P${s.final_period}`}
                          </td>
                          <td className="py-2 pr-4 text-center text-zinc-300">
                            {s.final_minutes_desc}
                          </td>
                          <td className="py-2 pr-4 text-center text-amber-300 font-mono">
                            {s.min_score_lead}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
          <div className="space-y-6">
            <div className="bg-zinc-900/60 border border-amber-900/20 rounded-xl p-4 flex flex-col">
              <h2 className="text-lg font-bold text-amber-400 mb-2">
                Inspiration
              </h2>
              <div
                className="flex-1 overflow-hidden [&_article]:!bg-transparent [&_article]:!border-amber-900/20 [&_.react-tweet-theme]:!bg-transparent"
                data-theme="dark"
              >
                <Tweet id="2023814333088637426" />
              </div>
            </div>

            {/* Password Form */}
            <form
              onSubmit={handleSubmit}
              className="gold-glow bg-zinc-900/90 border border-amber-900/40 rounded-xl p-8 backdrop-blur-sm"
            >
              <input
                type="password"
                value={password}
                onChange={(e) => {
                  setPassword(e.target.value);
                  setError(false);
                }}
                placeholder="Password"
                className="w-full bg-zinc-800/80 border border-amber-900/30 rounded-lg px-4 py-3 text-white placeholder-zinc-500 mb-4 focus:outline-none focus:border-amber-600 transition-colors"
                autoFocus
              />
              {error && (
                <p className="text-red-400 text-sm mb-4">Wrong password</p>
              )}
              <button
                type="submit"
                className="w-full bg-gradient-to-r from-amber-700 via-amber-500 to-amber-700 text-black font-bold py-3 rounded-lg hover:from-amber-600 hover:via-amber-400 hover:to-amber-600 transition-all shadow-lg shadow-amber-900/30"
              >
                Enter
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}

function useLiveGames(authed: boolean | null) {
  const [games, setGames] = useState<LiveGame[]>([]);

  useEffect(() => {
    if (!authed) return;

    const fetchGames = async () => {
      try {
        const res = await fetch(`${API}/api/live-games`);
        const data = await res.json();
        setGames(data.games);
      } catch {
        // ignore
      }
    };

    fetchGames();
    const interval = setInterval(fetchGames, 5000);
    return () => clearInterval(interval);
  }, [authed]);

  return games;
}

export default function Dashboard() {
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [balanceHistory, setBalanceHistory] = useState<BalanceSnapshot[]>([]);
  const [stretchStats, setStretchStats] = useState<StretchStats | null>(null);
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"trades" | "opportunities">("trades");
  const games = useLiveGames(authed);

  useEffect(() => {
    checkAuth().then(setAuthed);
  }, []);

  useEffect(() => {
    if (!authed) return;

    const fetchData = async () => {
      try {
        const [statsRes, tradesRes, oppsRes, balRes, stretchRes, configRes] =
          await Promise.all([
            fetch(`${API}/api/stats`),
            fetch(`${API}/api/trades?limit=50`),
            fetch(`${API}/api/opportunities?limit=50`),
            fetch(`${API}/api/balance-history?limit=200`),
            fetch(`${API}/api/stretch-stats`),
            fetch(`${API}/api/config`),
          ]);
        setStats(await statsRes.json());
        setTrades((await tradesRes.json()).trades);
        setOpportunities((await oppsRes.json()).opportunities);
        setBalanceHistory((await balRes.json()).snapshots);
        setStretchStats(await stretchRes.json());
        if (configRes.ok) setConfig(await configRes.json());
        setError(null);
      } catch {
        setError("Cannot connect to API");
      }
    };

    fetchData();
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, [authed]);

  if (authed === null) return <div className="min-h-screen bg-black" />;
  if (!authed) return <LoginForm onLogin={() => setAuthed(true)} />;

  if (error) {
    return (
      <div className="min-h-screen bg-black text-white flex items-center justify-center">
        <div className="text-center animate-fade-in">
          <h1 className="text-2xl font-bold mb-2 gold-shimmer">
            Rager's Get Rich Slow Scheme
          </h1>
          <p className="text-amber-700">{error}</p>
          <p className="text-zinc-500 text-sm mt-2">
            Make sure the API is running
          </p>
        </div>
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="min-h-screen bg-black text-white flex items-center justify-center">
        <div className="text-amber-500 gold-shimmer text-lg font-bold">
          Loading...
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-black text-white p-6">
      <div className="max-w-7xl mx-auto">
        <div className="flex items-center justify-between mb-8 animate-fade-in">
          <div>
            <h1 className="text-4xl font-black gold-shimmer tracking-tight">
              Rager's Get Rich Slow Scheme
            </h1>
            <p className="text-amber-800 text-sm mt-1">
              Kalshi Sports Market Scanner
            </p>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <div className="w-2.5 h-2.5 rounded-full bg-amber-400 animate-pulse shadow-lg shadow-amber-500/50" />
              <span className="text-amber-700 text-sm">Live 5s</span>
            </div>
          </div>
        </div>

        {/* Strategy + Config + Inspiration */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8 animate-fade-in">
          <div className="lg:col-span-2 space-y-6">
            <div className="bg-zinc-900/60 border border-amber-900/20 rounded-xl p-6">
              <h2 className="text-lg font-bold text-amber-400 mb-3">
                The Strategy
              </h2>
              <div className="space-y-2 text-sm text-zinc-400">
                <p>
                  Buy{" "}
                  <span className="text-amber-300 font-semibold">
                    YES contracts at 92c+
                  </span>{" "}
                  on Kalshi sports markets when a team is winning by a
                  comfortable margin in the final minutes of the game.
                </p>
                <p>
                  ESPN live data confirms the game state — we only bet when the
                  outcome is nearly certain. Each $20 bet earns $0.20–$1.60
                  profit in minutes.
                </p>
                <div className="grid grid-cols-2 gap-3 mt-4">
                  <div className="bg-black/40 rounded-lg p-3 border border-amber-900/10">
                    <div className="text-amber-600 text-xs uppercase tracking-wider mb-1">
                      Filters
                    </div>
                    <div className="text-zinc-300 text-xs leading-relaxed">
                      YES price ≥ 92c
                      <br />
                      Final period only
                      <br />
                      ESPN-verified score lead
                      <br />
                      Volume ≥ 50 contracts
                    </div>
                  </div>
                  <div className="bg-black/40 rounded-lg p-3 border border-amber-900/10">
                    <div className="text-amber-600 text-xs uppercase tracking-wider mb-1">
                      Risk Controls
                    </div>
                    <div className="text-zinc-300 text-xs leading-relaxed">
                      Max $20 per bet
                      <br />
                      Max 10 concurrent positions
                      <br />
                      No duplicate event bets
                      <br />
                      Min score lead by sport
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Scanner Configuration - nested in left column */}
            {config && (
              <div className="bg-zinc-900/80 border border-amber-900/30 rounded-xl p-5 backdrop-blur-sm">
                <h2 className="text-sm text-amber-600 font-medium mb-4">
                  Scanner Configuration
                </h2>
                <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-5">
                  <div className="bg-black/30 rounded-lg p-3 border border-zinc-800">
                    <div className="text-zinc-500 text-xs">Min YES Price</div>
                    <div className="text-amber-200 text-lg font-bold font-mono">
                      {config.trading.min_yes_price}¢
                    </div>
                  </div>
                  <div className="bg-black/30 rounded-lg p-3 border border-zinc-800">
                    <div className="text-zinc-500 text-xs">Max Bet</div>
                    <div className="text-amber-200 text-lg font-bold font-mono">
                      {cents(config.trading.max_bet_cents)}
                    </div>
                  </div>
                  <div className="bg-black/30 rounded-lg p-3 border border-zinc-800">
                    <div className="text-zinc-500 text-xs">Max Positions</div>
                    <div className="text-amber-200 text-lg font-bold font-mono">
                      {config.trading.max_positions}
                    </div>
                  </div>
                  <div className="bg-black/30 rounded-lg p-3 border border-zinc-800">
                    <div className="text-zinc-500 text-xs">Min Volume</div>
                    <div className="text-amber-200 text-lg font-bold font-mono">
                      {config.trading.min_volume}
                    </div>
                  </div>
                  <div className="bg-black/30 rounded-lg p-3 border border-zinc-800">
                    <div className="text-zinc-500 text-xs">Mode</div>
                    <div
                      className={`text-lg font-bold ${config.trading.dry_run ? "text-yellow-400" : "text-green-400"}`}
                    >
                      {config.trading.dry_run ? "DRY RUN" : "LIVE"}
                    </div>
                  </div>
                </div>
                <div className="flex flex-wrap gap-4 mb-5 text-xs text-zinc-500">
                  <span>ESPN: {config.polling.espn_interval_s}s</span>
                  <span>
                    Kalshi scan: {config.polling.kalshi_scan_interval_s}s
                  </span>
                  <span>
                    Kalshi WS:{" "}
                    {config.polling.kalshi_ws ? "✓ real-time" : "off"}
                  </span>
                  <span>Stretch min: {config.stretch.price_min}¢</span>
                  <span>
                    DB backup: {config.polling.db_backup_interval_s / 60}m
                  </span>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-zinc-500 border-b border-zinc-800">
                        <th className="text-left py-2 pr-4">Sport</th>
                        <th className="text-left py-2 pr-4">Kalshi Series</th>
                        <th className="text-center py-2 pr-4">Final Period</th>
                        <th className="text-center py-2 pr-4">End-of-Game</th>
                        <th className="text-center py-2 pr-4">Min Lead</th>
                        <th className="text-center py-2 pr-4">Stretch Lead</th>
                      </tr>
                    </thead>
                    <tbody>
                      {config.sports.map((s) => (
                        <tr
                          key={s.sport_path}
                          className="border-b border-zinc-800/50 hover:bg-zinc-800/30"
                        >
                          <td className="py-2 pr-4 text-amber-200 font-medium">
                            {s.name}
                          </td>
                          <td className="py-2 pr-4 text-zinc-400 font-mono">
                            {s.kalshi_series}
                          </td>
                          <td className="py-2 pr-4 text-center text-zinc-300">
                            {s.clock_direction === "none"
                              ? `Inning ${s.final_period}`
                              : `P${s.final_period}`}
                          </td>
                          <td className="py-2 pr-4 text-center text-zinc-300">
                            {s.final_minutes_desc}
                          </td>
                          <td className="py-2 pr-4 text-center text-amber-300 font-mono">
                            {s.min_score_lead}
                          </td>
                          <td className="py-2 pr-4 text-center text-zinc-500 font-mono">
                            {s.stretch_score_lead}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
          <div className="bg-zinc-900/60 border border-amber-900/20 rounded-xl p-4 flex flex-col">
            <h2 className="text-lg font-bold text-amber-400 mb-2">
              Inspiration
            </h2>
            <div
              className="flex-1 overflow-hidden [&_article]:!bg-transparent [&_article]:!border-amber-900/20 [&_.react-tweet-theme]:!bg-transparent"
              data-theme="dark"
            >
              <Tweet id="2023814333088637426" />
            </div>
          </div>
        </div>

        {/* Stats Grid */}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4 mb-8">
          <StatCard
            label="Balance"
            value={cents(stats.balance_cents)}
            delay={0}
          />
          <StatCard
            label="On the Line"
            value={cents(stats.open_cost_cents || 0)}
            sub={`${stats.open_positions || 0} open positions`}
            delay={50}
          />
          <StatCard
            label="Win Rate"
            value={`${stats.win_rate}%`}
            sub={`${stats.wins}W / ${stats.losses}L`}
            delay={100}
          />
          <StatCard
            label="Realized P&L"
            value={cents(stats.realized_pnl_cents)}
            delay={150}
          />
          <StatCard
            label="Trades"
            value={String(stats.live_trades)}
            sub={`${cents(stats.total_cost_cents)} deployed`}
            delay={200}
          />
        </div>

        {/* P&L Chart */}
        <PnlChart
          trades={trades}
          balanceCents={stats.balance_cents}
          portfolioCents={stats.portfolio_value_cents}
        />

        {/* What If? Strategy Comparison */}
        {stretchStats &&
          stretchStats.strategies &&
          Object.keys(stretchStats.strategies).length > 0 && (
            <div className="animate-fade-in bg-zinc-900/80 border border-amber-900/30 rounded-xl p-5 mb-8 backdrop-blur-sm">
              <div className="flex justify-between items-center mb-4">
                <h2 className="text-sm text-amber-600 font-medium">
                  What If? Strategy Comparison
                </h2>
                <span className="text-xs text-zinc-500">
                  Shadow-tracking {stretchStats.total} markets across{" "}
                  {Object.keys(stretchStats.strategies).length} strategies
                </span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-zinc-700 text-zinc-500 text-xs">
                      <th className="text-left py-2 pr-4">Strategy</th>
                      <th className="text-center py-2 px-3">Tracked</th>
                      <th className="text-center py-2 px-3">W</th>
                      <th className="text-center py-2 px-3">L</th>
                      <th className="text-center py-2 px-3">Open</th>
                      <th className="text-center py-2 px-3">Win %</th>
                      <th className="text-right py-2 pl-3">Hyp P&L</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(stretchStats.strategies)
                      .sort(
                        ([, a], [, b]) =>
                          b.hypothetical_pnl_cents - a.hypothetical_pnl_cents,
                      )
                      .map(([key, s]) => (
                        <tr
                          key={key}
                          className="border-b border-zinc-800/50 hover:bg-zinc-800/30"
                        >
                          <td className="py-2 pr-4 text-amber-200 font-medium">
                            {s.label}
                          </td>
                          <td className="py-2 px-3 text-center text-zinc-300 font-mono">
                            {s.total}
                          </td>
                          <td className="py-2 px-3 text-center text-green-400 font-mono">
                            {s.wins}
                          </td>
                          <td className="py-2 px-3 text-center text-red-400 font-mono">
                            {s.losses}
                          </td>
                          <td className="py-2 px-3 text-center text-zinc-500 font-mono">
                            {s.open}
                          </td>
                          <td className="py-2 px-3 text-center text-zinc-300 font-mono">
                            {s.win_rate > 0 ? `${s.win_rate}%` : "-"}
                          </td>
                          <td
                            className={`py-2 pl-3 text-right font-mono font-bold ${s.hypothetical_pnl_cents >= 0 ? "text-green-400" : "text-red-400"}`}
                          >
                            {s.hypothetical_pnl_cents >= 0 ? "+" : ""}
                            {cents(s.hypothetical_pnl_cents)}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

        {/* Live Games */}
        <LiveGamesPanel games={games} />

        {/* Tabs */}
        <div className="flex gap-4 mb-4">
          <button
            onClick={() => setTab("trades")}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
              tab === "trades"
                ? "bg-gradient-to-r from-amber-900/50 to-amber-800/50 text-amber-200 border border-amber-700/50 shadow-lg shadow-amber-900/20"
                : "text-zinc-500 hover:text-amber-400"
            }`}
          >
            Recent Trades
          </button>
          <button
            onClick={() => setTab("opportunities")}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
              tab === "opportunities"
                ? "bg-gradient-to-r from-amber-900/50 to-amber-800/50 text-amber-200 border border-amber-700/50 shadow-lg shadow-amber-900/20"
                : "text-zinc-500 hover:text-amber-400"
            }`}
          >
            Recent Opportunities
          </button>
        </div>

        {/* Trades Table */}
        {tab === "trades" && (
          <div className="animate-fade-in bg-zinc-900/80 border border-amber-900/30 rounded-xl overflow-hidden backdrop-blur-sm">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-amber-900/20 text-amber-600">
                  <th className="text-left p-3">Time</th>
                  <th className="text-left p-3">Market</th>
                  <th className="text-right p-3">Qty</th>
                  <th className="text-right p-3">Price</th>
                  <th className="text-right p-3">Cost</th>
                  <th className="text-right p-3">Potential</th>
                  <th className="text-right p-3">P&L</th>
                  <th className="text-right p-3">Status</th>
                </tr>
              </thead>
              <tbody>
                {trades.length === 0 && (
                  <tr>
                    <td colSpan={8} className="p-8 text-center text-amber-900">
                      No trades yet. Scanner is watching for opportunities.
                    </td>
                  </tr>
                )}
                {trades.map((t) => (
                  <tr
                    key={t.id}
                    className="border-b border-amber-900/10 hover:bg-amber-900/10 transition-colors"
                  >
                    <td className="p-3 text-amber-700">
                      {t.placed_at ? timeAgo(t.placed_at) : "-"}
                    </td>
                    <td className="p-3">
                      <div className="text-amber-100 truncate max-w-xs">
                        {t.title}
                      </div>
                      <div className="text-amber-800 text-xs">{t.ticker}</div>
                    </td>
                    <td className="p-3 text-right text-amber-200">{t.count}</td>
                    <td className="p-3 text-right text-amber-200">
                      {t.yes_price}c
                    </td>
                    <td className="p-3 text-right text-amber-200">
                      {cents(t.cost_cents)}
                    </td>
                    <td className="p-3 text-right text-green-400">
                      +{cents(t.potential_profit_cents)}
                    </td>
                    <td className="p-3 text-right">
                      {t.pnl_cents !== null ? (
                        <span
                          className={
                            t.pnl_cents >= 0 ? "text-green-400" : "text-red-400"
                          }
                        >
                          {t.pnl_cents >= 0 ? "+" : ""}
                          {cents(t.pnl_cents)}
                        </span>
                      ) : (
                        <span className="text-zinc-600">-</span>
                      )}
                    </td>
                    <td className="p-3 text-right">
                      <StatusBadge status={t.status} dryRun={t.dry_run} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Opportunities Table */}
        {tab === "opportunities" && (
          <div className="animate-fade-in bg-zinc-900/80 border border-amber-900/30 rounded-xl overflow-hidden backdrop-blur-sm">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-amber-900/20 text-amber-600">
                  <th className="text-left p-3">Found</th>
                  <th className="text-left p-3">Market</th>
                  <th className="text-left p-3">Sport</th>
                  <th className="text-right p-3">Yes Bid</th>
                  <th className="text-right p-3">Yes Ask</th>
                  <th className="text-right p-3">Spread</th>
                  <th className="text-right p-3">Volume</th>
                </tr>
              </thead>
              <tbody>
                {opportunities.length === 0 && (
                  <tr>
                    <td colSpan={7} className="p-8 text-center text-amber-900">
                      No opportunities found yet.
                    </td>
                  </tr>
                )}
                {opportunities.map((o) => (
                  <tr
                    key={o.id}
                    className="border-b border-amber-900/10 hover:bg-amber-900/10 transition-colors"
                  >
                    <td className="p-3 text-amber-700">
                      {o.found_at ? timeAgo(o.found_at) : "-"}
                    </td>
                    <td className="p-3">
                      <div className="text-amber-100 truncate max-w-xs">
                        {o.yes_sub_title || o.title}
                      </div>
                      <div className="text-amber-800 text-xs">{o.ticker}</div>
                    </td>
                    <td className="p-3 text-amber-600">{o.series_ticker}</td>
                    <td className="p-3 text-right text-amber-200">
                      {o.yes_bid}c
                    </td>
                    <td className="p-3 text-right text-amber-200">
                      {o.yes_ask}c
                    </td>
                    <td className="p-3 text-right text-green-400">
                      {o.spread}c
                    </td>
                    <td className="p-3 text-right text-amber-600">
                      {o.volume.toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

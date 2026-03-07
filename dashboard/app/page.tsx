"use client";

import { useEffect, useState } from "react";

const API = "http://localhost:8000";

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

function cents(c: number): string {
  return `$${(c / 100).toFixed(2)}`;
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

function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
      <div className="text-zinc-500 text-sm mb-1">{label}</div>
      <div className="text-2xl font-bold text-white">{value}</div>
      {sub && <div className="text-zinc-400 text-sm mt-1">{sub}</div>}
    </div>
  );
}

function StatusBadge({ status, dryRun }: { status: string; dryRun: boolean }) {
  if (dryRun) return <span className="px-2 py-0.5 text-xs rounded-full bg-zinc-700 text-zinc-300">DRY RUN</span>;
  const colors: Record<string, string> = {
    placed: "bg-blue-900/50 text-blue-300",
    filled: "bg-yellow-900/50 text-yellow-300",
    settled_win: "bg-green-900/50 text-green-300",
    settled_loss: "bg-red-900/50 text-red-300",
    error: "bg-red-900/50 text-red-300",
  };
  return (
    <span className={`px-2 py-0.5 text-xs rounded-full ${colors[status] || "bg-zinc-700 text-zinc-300"}`}>
      {status.replace("_", " ").toUpperCase()}
    </span>
  );
}

export default function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [balanceHistory, setBalanceHistory] = useState<BalanceSnapshot[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"trades" | "opportunities">("trades");

  const fetchData = async () => {
    try {
      const [statsRes, tradesRes, oppsRes, balRes] = await Promise.all([
        fetch(`${API}/api/stats`),
        fetch(`${API}/api/trades?limit=50`),
        fetch(`${API}/api/opportunities?limit=50`),
        fetch(`${API}/api/balance-history?limit=200`),
      ]);
      setStats(await statsRes.json());
      setTrades((await tradesRes.json()).trades);
      setOpportunities((await oppsRes.json()).opportunities);
      setBalanceHistory((await balRes.json()).snapshots);
      setError(null);
    } catch {
      setError("Cannot connect to API at localhost:8000");
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, []);

  if (error) {
    return (
      <div className="min-h-screen bg-black text-white flex items-center justify-center">
        <div className="text-center">
          <h1 className="text-2xl font-bold mb-2">Predictions Dashboard</h1>
          <p className="text-zinc-400">{error}</p>
          <p className="text-zinc-500 text-sm mt-2">Run: uv run uvicorn api:app --reload --port 8000</p>
        </div>
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="min-h-screen bg-black text-white flex items-center justify-center">
        <div className="text-zinc-400">Loading...</div>
      </div>
    );
  }

  const balanceMax = Math.max(...balanceHistory.map((s) => s.balance_cents + (s.portfolio_value_cents || 0)), 1);

  return (
    <div className="min-h-screen bg-black text-white p-6">
      <div className="max-w-7xl mx-auto">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold">Predictions</h1>
            <p className="text-zinc-500 text-sm">Kalshi Sports Market Scanner</p>
          </div>
          <div className="flex items-center gap-3">
            <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
            <span className="text-zinc-400 text-sm">Auto-refresh 10s</span>
          </div>
        </div>

        {/* Stats Grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4 mb-8">
          <StatCard label="Balance" value={cents(stats.balance_cents)} />
          <StatCard label="Portfolio Value" value={cents(stats.portfolio_value_cents)} />
          <StatCard label="Win Rate" value={`${stats.win_rate}%`} sub={`${stats.wins}W / ${stats.losses}L`} />
          <StatCard label="Realized P&L" value={cents(stats.realized_pnl_cents)} />
          <StatCard
            label="Trades"
            value={String(stats.total_trades)}
            sub={`${stats.live_trades} live / ${stats.dry_run_trades} dry`}
          />
          <StatCard
            label="Scans"
            value={String(stats.total_scans)}
            sub={`${stats.total_opportunities} opps found`}
          />
        </div>

        {/* Balance Chart */}
        {balanceHistory.length > 1 && (
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 mb-8">
            <h2 className="text-sm text-zinc-500 mb-4">Balance + Portfolio Over Time</h2>
            <div className="h-40 flex items-end gap-px">
              {balanceHistory.map((s, i) => {
                const total = s.balance_cents + (s.portfolio_value_cents || 0);
                const pct = (total / balanceMax) * 100;
                return (
                  <div
                    key={i}
                    className="flex-1 bg-green-500/60 hover:bg-green-400 rounded-t transition-colors"
                    style={{ height: `${Math.max(pct, 2)}%` }}
                    title={`${new Date(s.recorded_at).toLocaleString()}: ${cents(total)}`}
                  />
                );
              })}
            </div>
          </div>
        )}

        {/* Tabs */}
        <div className="flex gap-4 mb-4">
          <button
            onClick={() => setTab("trades")}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              tab === "trades" ? "bg-zinc-800 text-white" : "text-zinc-500 hover:text-zinc-300"
            }`}
          >
            Recent Trades
          </button>
          <button
            onClick={() => setTab("opportunities")}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              tab === "opportunities" ? "bg-zinc-800 text-white" : "text-zinc-500 hover:text-zinc-300"
            }`}
          >
            Recent Opportunities
          </button>
        </div>

        {/* Trades Table */}
        {tab === "trades" && (
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-800 text-zinc-500">
                  <th className="text-left p-3">Time</th>
                  <th className="text-left p-3">Market</th>
                  <th className="text-right p-3">Contracts</th>
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
                    <td colSpan={8} className="p-8 text-center text-zinc-600">
                      No trades yet. Start the scanner to find opportunities.
                    </td>
                  </tr>
                )}
                {trades.map((t) => (
                  <tr key={t.id} className="border-b border-zinc-800/50 hover:bg-zinc-800/30">
                    <td className="p-3 text-zinc-400">{t.placed_at ? timeAgo(t.placed_at) : "-"}</td>
                    <td className="p-3">
                      <div className="text-white truncate max-w-xs">{t.title}</div>
                      <div className="text-zinc-500 text-xs">{t.ticker}</div>
                    </td>
                    <td className="p-3 text-right">{t.count}</td>
                    <td className="p-3 text-right">{t.yes_price}c</td>
                    <td className="p-3 text-right">{cents(t.cost_cents)}</td>
                    <td className="p-3 text-right text-green-400">+{cents(t.potential_profit_cents)}</td>
                    <td className="p-3 text-right">
                      {t.pnl_cents !== null ? (
                        <span className={t.pnl_cents >= 0 ? "text-green-400" : "text-red-400"}>
                          {t.pnl_cents >= 0 ? "+" : ""}
                          {cents(t.pnl_cents)}
                        </span>
                      ) : (
                        "-"
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
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-800 text-zinc-500">
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
                    <td colSpan={7} className="p-8 text-center text-zinc-600">
                      No opportunities found yet.
                    </td>
                  </tr>
                )}
                {opportunities.map((o) => (
                  <tr key={o.id} className="border-b border-zinc-800/50 hover:bg-zinc-800/30">
                    <td className="p-3 text-zinc-400">{o.found_at ? timeAgo(o.found_at) : "-"}</td>
                    <td className="p-3">
                      <div className="text-white truncate max-w-xs">{o.yes_sub_title || o.title}</div>
                      <div className="text-zinc-500 text-xs">{o.ticker}</div>
                    </td>
                    <td className="p-3 text-zinc-400">{o.series_ticker}</td>
                    <td className="p-3 text-right">{o.yes_bid}c</td>
                    <td className="p-3 text-right">{o.yes_ask}c</td>
                    <td className="p-3 text-right text-green-400">{o.spread}c</td>
                    <td className="p-3 text-right text-zinc-400">{o.volume.toLocaleString()}</td>
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

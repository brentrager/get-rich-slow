import React, { useEffect, useState } from "react";
import { Box, Text } from "ink";
import type { ApiClient } from "../api.js";

interface StatsViewProps {
    api: ApiClient;
}

function formatCents(cents: number): string {
    const dollars = cents / 100;
    return `$${dollars.toFixed(2)}`;
}

const STAT_LABELS: Record<string, string> = {
    total_trades: "Total Trades",
    live_trades: "Live Trades",
    dry_run_trades: "Dry Run Trades",
    total_cost_cents: "Total Cost",
    total_potential_profit_cents: "Potential Profit",
    realized_pnl_cents: "Realized P&L",
    wins: "Wins",
    losses: "Losses",
    win_rate: "Win Rate",
    total_scans: "Total Scans",
    total_opportunities: "Unique Opportunities",
    balance_cents: "Balance",
    portfolio_value_cents: "Portfolio Value",
    open_positions: "Open Positions",
    open_cost_cents: "Open Cost",
    open_potential_profit_cents: "Open Potential Profit",
};

const CENTS_FIELDS = new Set([
    "total_cost_cents",
    "total_potential_profit_cents",
    "realized_pnl_cents",
    "balance_cents",
    "portfolio_value_cents",
    "open_cost_cents",
    "open_potential_profit_cents",
]);

export function StatsView({ api }: StatsViewProps) {
    const [stats, setStats] = useState<Record<string, unknown> | null>(
        null,
    );
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        api.getStats()
            .then(setStats)
            .catch((err) => setError(String(err)));
    }, [api]);

    if (error) {
        return <Text color="red">Error: {error}</Text>;
    }
    if (!stats) {
        return <Text color="yellow">Loading stats...</Text>;
    }

    const entries = Object.entries(stats);
    const labelWidth = Math.max(
        ...entries.map(
            ([k]) => (STAT_LABELS[k] ?? k).length,
        ),
        5,
    );

    return (
        <Box flexDirection="column">
            <Text bold color="#F59E0B">
                Scanner Stats
            </Text>
            <Box marginTop={1} flexDirection="column">
                <Box>
                    <Box width={labelWidth + 2}>
                        <Text bold underline>
                            Metric
                        </Text>
                    </Box>
                    <Text bold underline>
                        Value
                    </Text>
                </Box>
                {entries.map(([key, val]) => {
                    const label = STAT_LABELS[key] ?? key;
                    let display: string;
                    if (CENTS_FIELDS.has(key)) {
                        display = formatCents(Number(val));
                    } else if (key === "win_rate") {
                        display = `${val}%`;
                    } else {
                        display = String(val);
                    }

                    // Color P&L values
                    let valueColor: string | undefined;
                    if (key === "realized_pnl_cents") {
                        valueColor =
                            Number(val) >= 0 ? "green" : "red";
                    }

                    return (
                        <Box key={key}>
                            <Box width={labelWidth + 2}>
                                <Text color="#a1a1aa">
                                    {label}
                                </Text>
                            </Box>
                            <Text color={valueColor}>
                                {display}
                            </Text>
                        </Box>
                    );
                })}
            </Box>
        </Box>
    );
}

import React, { useEffect, useState } from "react";
import { Box, Text } from "ink";
import type { ApiClient } from "../api.js";

interface Trade {
    id: number;
    placed_at: string | null;
    ticker: string;
    title: string | null;
    side: string;
    count: number;
    yes_price: number;
    cost_cents: number;
    potential_profit_cents: number;
    status: string;
    pnl_cents: number | null;
    dry_run: boolean;
}

interface TradesViewProps {
    api: ApiClient;
}

function formatCents(cents: number): string {
    const dollars = cents / 100;
    return `$${dollars.toFixed(2)}`;
}

function formatDate(iso: string | null): string {
    if (!iso) return "-";
    const d = new Date(iso);
    return d.toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
    });
}

function statusColor(status: string): string | undefined {
    switch (status) {
        case "settled_win":
            return "green";
        case "settled_loss":
            return "red";
        case "placed":
        case "filled":
            return "#F59E0B";
        default:
            return "#a1a1aa";
    }
}

// Column definitions for the trades table
const COLUMNS = [
    { key: "id", label: "ID", width: 5 },
    { key: "placed_at", label: "Date", width: 18 },
    { key: "ticker", label: "Ticker", width: 28 },
    { key: "side", label: "Side", width: 5 },
    { key: "yes_price", label: "Price", width: 7 },
    { key: "cost_cents", label: "Cost", width: 9 },
    { key: "status", label: "Status", width: 14 },
    { key: "pnl_cents", label: "P&L", width: 9 },
    { key: "dry_run", label: "Dry?", width: 5 },
] as const;

function cellValue(trade: Trade, key: string): string {
    switch (key) {
        case "placed_at":
            return formatDate(trade.placed_at);
        case "yes_price":
            return `${trade.yes_price}c`;
        case "cost_cents":
            return formatCents(trade.cost_cents);
        case "pnl_cents":
            return trade.pnl_cents != null
                ? formatCents(trade.pnl_cents)
                : "-";
        case "dry_run":
            return trade.dry_run ? "Y" : "N";
        default:
            return String(
                (trade as unknown as Record<string, unknown>)[key] ??
                    "",
            );
    }
}

export function TradesView({ api }: TradesViewProps) {
    const [trades, setTrades] = useState<Trade[] | null>(null);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        api.getTrades()
            .then((data) => setTrades(data.trades as Trade[]))
            .catch((err) => setError(String(err)));
    }, [api]);

    if (error) {
        return <Text color="red">Error: {error}</Text>;
    }
    if (!trades) {
        return <Text color="yellow">Loading trades...</Text>;
    }
    if (trades.length === 0) {
        return <Text color="#a1a1aa">No trades found.</Text>;
    }

    return (
        <Box flexDirection="column">
            <Text bold color="#F59E0B">
                Recent Trades
            </Text>
            <Box marginTop={1} flexDirection="column">
                {/* Header row */}
                <Box>
                    {COLUMNS.map((col) => (
                        <Box key={col.key} width={col.width + 1}>
                            <Text bold underline>
                                {col.label}
                            </Text>
                        </Box>
                    ))}
                </Box>
                {/* Data rows */}
                {trades.map((trade) => (
                    <Box key={trade.id}>
                        {COLUMNS.map((col) => {
                            const val = cellValue(trade, col.key);
                            let color: string | undefined;
                            if (col.key === "status") {
                                color = statusColor(trade.status);
                            } else if (col.key === "pnl_cents" && trade.pnl_cents != null) {
                                color =
                                    trade.pnl_cents >= 0
                                        ? "green"
                                        : "red";
                            }
                            return (
                                <Box
                                    key={col.key}
                                    width={col.width + 1}
                                >
                                    <Text color={color}>{val}</Text>
                                </Box>
                            );
                        })}
                    </Box>
                ))}
            </Box>
        </Box>
    );
}

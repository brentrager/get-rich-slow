import React, { useEffect, useState } from "react";
import { Box, Text } from "ink";
import type { ApiClient } from "../api.js";

// ── Flatten nested config into dot-separated key/value rows ──

function flattenConfig(
    obj: Record<string, unknown>,
    prefix = "",
): { key: string; value: string }[] {
    const rows: { key: string; value: string }[] = [];
    for (const [k, v] of Object.entries(obj)) {
        const fullKey = prefix ? `${prefix}.${k}` : k;
        if (
            v !== null &&
            typeof v === "object" &&
            !Array.isArray(v)
        ) {
            rows.push(
                ...flattenConfig(v as Record<string, unknown>, fullKey),
            );
        } else if (Array.isArray(v)) {
            // For arrays (like sports), show each item as a sub-group
            for (let i = 0; i < v.length; i++) {
                const item = v[i];
                if (typeof item === "object" && item !== null) {
                    const label =
                        (item as Record<string, unknown>).name ??
                        String(i);
                    rows.push(
                        ...flattenConfig(
                            item as Record<string, unknown>,
                            `${fullKey}[${label}]`,
                        ),
                    );
                } else {
                    rows.push({
                        key: `${fullKey}[${i}]`,
                        value: String(item),
                    });
                }
            }
        } else {
            rows.push({ key: fullKey, value: String(v ?? "") });
        }
    }
    return rows;
}

// ── Config View ──

interface ConfigViewProps {
    api: ApiClient;
}

export function ConfigView({ api }: ConfigViewProps) {
    const [rows, setRows] = useState<{ key: string; value: string }[]>(
        [],
    );
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        api.getConfig()
            .then((cfg) => {
                setRows(flattenConfig(cfg));
                setLoading(false);
            })
            .catch((err) => {
                setError(String(err));
                setLoading(false);
            });
    }, [api]);

    if (loading) {
        return <Text color="yellow">Loading config...</Text>;
    }
    if (error) {
        return <Text color="red">Error: {error}</Text>;
    }

    // Compute column widths
    const keyWidth = Math.max(...rows.map((r) => r.key.length), 3);

    return (
        <Box flexDirection="column">
            <Text bold color="#F59E0B">
                Scanner Configuration
            </Text>
            <Box marginTop={1} flexDirection="column">
                <Box>
                    <Box width={keyWidth + 2}>
                        <Text bold underline>
                            Key
                        </Text>
                    </Box>
                    <Text bold underline>
                        Value
                    </Text>
                </Box>
                {rows.map((row, idx) => (
                    <Box key={`${idx}-${row.key}`}>
                        <Box width={keyWidth + 2}>
                            <Text color="#a1a1aa">{row.key}</Text>
                        </Box>
                        <Text>{row.value}</Text>
                    </Box>
                ))}
            </Box>
        </Box>
    );
}

// ── Config Set ──

interface ConfigSetProps {
    api: ApiClient;
    configKey: string;
    configValue: string;
}

export function ConfigSet({
    api,
    configKey,
    configValue,
}: ConfigSetProps) {
    const [result, setResult] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        api.setConfig(configKey, configValue)
            .then(() => {
                setResult(
                    `Set ${configKey} = ${configValue}`,
                );
            })
            .catch((err) => {
                setError(String(err));
            });
    }, [api, configKey, configValue]);

    if (error) {
        return <Text color="red">Error: {error}</Text>;
    }
    if (!result) {
        return <Text color="yellow">Updating...</Text>;
    }

    return (
        <Text color="green">
            {result}
        </Text>
    );
}

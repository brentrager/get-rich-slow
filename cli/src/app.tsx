import React from "react";
import { Box, Text } from "ink";
import BigText from "ink-big-text";
import { ApiClient } from "./api.js";
import { ConfigView, ConfigSet } from "./components/config.js";
import { StatsView } from "./components/stats.js";
import { TradesView } from "./components/trades.js";

export interface AppProps {
    command: string;
    apiUrl: string;
    token: string;
    configKey?: string;
    configValue?: string;
}

export function App({
    command,
    apiUrl,
    token,
    configKey,
    configValue,
}: AppProps) {
    const api = new ApiClient({ baseUrl: apiUrl, token });

    let content: React.ReactNode;

    switch (command) {
        case "config:set":
            content = (
                <ConfigSet
                    api={api}
                    configKey={configKey!}
                    configValue={configValue!}
                />
            );
            break;
        case "stats":
            content = <StatsView api={api} />;
            break;
        case "trades":
            content = <TradesView api={api} />;
            break;
        case "config":
        default:
            content = <ConfigView api={api} />;
            break;
    }

    return (
        <Box flexDirection="column">
            <BigText text="Get Rich Slow" colors={["#F59E0B"]} />
            <Box marginBottom={1}>
                <Text color="#a1a1aa">
                    {apiUrl}
                </Text>
            </Box>
            {content}
        </Box>
    );
}

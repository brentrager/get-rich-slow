#!/usr/bin/env node
import React from "react";
import { render } from "ink";
import meow from "meow";
import { App } from "./app.js";
import { ApiClient } from "./api.js";

const cli = meow(
    `
  Usage
    $ getrich [command] [options]

  Commands
    config              Show current scanner configuration (default)
    config set <k> <v>  Update a config value
    stats               Show scanner stats
    trades              Show recent trades

  Options
    --api-url, -u   API base URL (default: GETRICH_API_URL env or https://getrich-api.rager.tech)
    --token, -t     API token (default: API_TOKEN env)
    --json          Output raw JSON (non-interactive, no TUI)

  Examples
    $ getrich config
    $ getrich config set min_yes_price 90
    $ getrich stats --json
    $ getrich trades --json | jq '.trades[0]'
`,
    {
        importMeta: import.meta,
        flags: {
            apiUrl: {
                type: "string",
                shortFlag: "u",
                default:
                    process.env.GETRICH_API_URL ??
                    "https://getrich-api.rager.tech",
            },
            token: {
                type: "string",
                shortFlag: "t",
                default: process.env.API_TOKEN ?? "",
            },
            json: {
                type: "boolean",
                default: false,
            },
        },
    },
);

const apiUrl = cli.flags.apiUrl;
const token = cli.flags.token;

// When invoked via `pnpm start -- <flags>`, the `--` causes meow to
// treat flags as positional args. Handle them manually.
const rawJson =
    cli.flags.json || cli.input.includes("--json");
if (cli.input.includes("--help") || cli.input.includes("-h")) {
    cli.showHelp();
}

// Filter out any leaked flags from positional input
const input = cli.input.filter((s) => !s.startsWith("--"));

if (!token) {
    console.error(
        "Error: API token required. Set API_TOKEN env var or pass --token.",
    );
    process.exit(1);
}

// Determine the command
const [cmd, sub, ...rest] = input;
let command: string;
let configKey: string | undefined;
let configValue: string | undefined;

if (cmd === "config" && sub === "set") {
    command = "config:set";
    configKey = rest[0];
    configValue = rest[1];
    if (!configKey || configValue === undefined) {
        console.error("Usage: getrich config set <key> <value>");
        process.exit(1);
    }
} else if (cmd === "stats") {
    command = "stats";
} else if (cmd === "trades") {
    command = "trades";
} else {
    command = "config";
}

// ── Raw JSON mode ──

if (rawJson) {
    const api = new ApiClient({ baseUrl: apiUrl, token });

    async function runRaw() {
        try {
            let result: unknown;
            switch (command) {
                case "config":
                    result = await api.getConfig();
                    break;
                case "config:set":
                    result = await api.setConfig(configKey!, configValue!);
                    break;
                case "stats":
                    result = await api.getStats();
                    break;
                case "trades":
                    result = await api.getTrades();
                    break;
            }
            console.log(JSON.stringify(result, null, 2));
        } catch (err) {
            console.error(String(err));
            process.exit(1);
        }
    }

    runRaw();
} else {
    // ── Interactive TUI mode ──
    render(
        <App
            command={command}
            apiUrl={apiUrl}
            token={token}
            configKey={configKey}
            configValue={configValue}
        />,
    );
}

/// <reference path="./.sst/platform/config.d.ts" />

export default $config({
    app(input) {
        return {
            name: "predictions",
            removal: input?.stage === "production" ? "retain" : "remove",
            home: "aws",
            providers: {
                aws: {
                    region: "us-east-2",
                },
                cloudflare: true,
            },
        };
    },
    async run() {
        const dashboardPassword = new sst.Secret("DashboardPassword");
        const kalshiApiKey = new sst.Secret("KalshiApiKey");
        const kalshiPrivateKey = new sst.Secret("KalshiPrivateKey");

        const vpc = new sst.aws.Vpc("Vpc", { nat: "ec2" });
        const cluster = new sst.aws.Cluster("Cluster", { vpc });

        // EFS for SQLite persistence
        const efs = new sst.aws.Efs("Efs", { vpc });

        // API + Scanner on single ECS service (saves ~$9/mo)
        const api = cluster.addService("Api", {
            image: {
                context: ".",
                dockerfile: "Dockerfile",
                buildArgs: { CACHE_BUST: Date.now().toString() },
            },
            cpu: "0.25 vCPU",
            memory: "0.5 GB",
            environment: {
                DATABASE_URL: $dev
                    ? "sqlite:///predictions.db"
                    : "sqlite:////data/predictions.db",
                KALSHI_API_KEY: kalshiApiKey.value,
                KALSHI_PRIVATE_KEY: kalshiPrivateKey.value,
                MIN_YES_PRICE: "92",
                MAX_BET_AMOUNT_CENTS: "500",
                POLL_INTERVAL_SECONDS: "10",
                DRY_RUN: "false",
            },
            volumes: [{ efs, path: "/data" }],
            public: {
                ports: [{ listen: "443/https", forward: "8000/http" }],
                domain: {
                    name: "getrich-api.rager.tech",
                    dns: sst.cloudflare.dns(),
                },
            },
            dev: {
                command: "pnpm dev:api",
                url: "http://localhost:8000",
            },
        });

        // Next.js dashboard via OpenNext (Lambda/CloudFront)
        const dashboard = new sst.aws.Nextjs("Dashboard", {
            path: "dashboard",
            domain: {
                name: "getrich.rager.tech",
                dns: sst.cloudflare.dns(),
            },
            environment: {
                NEXT_PUBLIC_API_URL: $interpolate`${api.url}`.apply((v) =>
                    v.replace(/\/+$/, ""),
                ),
                DASHBOARD_PASSWORD: dashboardPassword.value,
            },
        });

        return {
            api: api.url,
            dashboard: dashboard.url,
        };
    },
});

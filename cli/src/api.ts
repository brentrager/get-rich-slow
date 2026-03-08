/**
 * API client for the Get Rich Slow API.
 */

export interface ApiClientOptions {
    baseUrl: string;
    token: string;
}

export class ApiClient {
    private baseUrl: string;
    private token: string;

    constructor(opts: ApiClientOptions) {
        this.baseUrl = opts.baseUrl.replace(/\/+$/, "");
        this.token = opts.token;
    }

    private async request<T>(
        method: string,
        path: string,
        body?: unknown,
    ): Promise<T> {
        const url = `${this.baseUrl}${path}`;
        const headers: Record<string, string> = {
            "Content-Type": "application/json",
            Authorization: `Bearer ${this.token}`,
        };

        const res = await fetch(url, {
            method,
            headers,
            body: body ? JSON.stringify(body) : undefined,
        });

        if (!res.ok) {
            const text = await res.text().catch(() => "");
            throw new Error(
                `API ${method} ${path} failed (${res.status}): ${text}`,
            );
        }

        return (await res.json()) as T;
    }

    async getConfig(): Promise<Record<string, unknown>> {
        return this.request("GET", "/api/config");
    }

    async setConfig(key: string, value: string): Promise<{ ok: boolean }> {
        return this.request("PUT", "/api/config", { key, value });
    }

    async getStats(): Promise<Record<string, unknown>> {
        return this.request("GET", "/api/stats");
    }

    async getTrades(): Promise<{ trades: Record<string, unknown>[] }> {
        return this.request("GET", "/api/trades");
    }
}

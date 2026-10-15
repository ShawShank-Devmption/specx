/** Test helper: boots a seed app in-process on an ephemeral port and gives a tiny cookie-aware HTTP client. */
import type { Server } from "node:http";
import type { AddressInfo } from "node:net";
import path from "node:path";
import type { Express } from "express";
import { SEED_APPS_DIR } from "../../src/paths.js";

export interface RunningApp {
  base: string;
  close: () => Promise<void>;
}

export async function startSeedApp(app: string): Promise<RunningApp> {
  const modPath = path.join(SEED_APPS_DIR, app, "server.js");
  const mod = (await import(modPath)) as { createApp: () => Express };
  const server: Server = await new Promise((resolve) => {
    const s = mod.createApp().listen(0, "127.0.0.1", () => resolve(s));
  });
  const { port } = server.address() as AddressInfo;
  return {
    base: `http://127.0.0.1:${port}`,
    close: () => new Promise((resolve) => server.close(() => resolve())),
  };
}

export class Client {
  private cookies = new Map<string, string>();
  constructor(
    private readonly base: string,
    private readonly tenant: string,
  ) {}

  async req(method: string, url: string, body?: unknown): Promise<{ status: number; headers: Headers; json: unknown }> {
    const headers: Record<string, string> = { "x-specx-tenant": this.tenant };
    if (body !== undefined) headers["content-type"] = "application/json";
    const cookie = [...this.cookies].map(([k, v]) => `${k}=${v}`).join("; ");
    if (cookie) headers.cookie = cookie;
    const res = await fetch(this.base + url, { method, headers, body: body === undefined ? undefined : JSON.stringify(body), redirect: "manual" });
    for (const c of res.headers.getSetCookie()) {
      const [pair] = c.split(";");
      const [k, v] = (pair ?? "").split("=");
      if (k && v !== undefined) this.cookies.set(k.trim(), v.trim());
    }
    const text = await res.text();
    let json: unknown = text;
    try {
      json = text ? JSON.parse(text) : null;
    } catch {
      /* non-JSON body (HTML page) */
    }
    return { status: res.status, headers: res.headers, json };
  }

  login(username: string, password: string) {
    return this.req("POST", "/api/login", { username, password });
  }

  async db(): Promise<Record<string, { count: number; rows: Record<string, unknown>[] }>> {
    const r = await this.req("GET", "/__test/db");
    return (r.json as { tables: Record<string, { count: number; rows: Record<string, unknown>[] }> }).tables;
  }
}

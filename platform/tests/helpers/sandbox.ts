/** Integration helpers: real seed apps + real sandbox server, each on an ephemeral port. */
import fs from "node:fs";
import type { Server } from "node:http";
import type { AddressInfo } from "node:net";
import path from "node:path";
import type { AppManifest, ToolContract, ToolDefinition } from "../../src/contracts/types.js";
import { manifestPath, REPO_ROOT } from "../../src/paths.js";
import { createSandbox, type Sandbox } from "../../src/sandbox/server.js";
import { startSeedApp, type RunningApp } from "./seedapp.js";

export const integration = process.env.SANDBOX_INTEGRATION === "1";

export function withPort(manifest: AppManifest, base: string): AppManifest {
  const host = new URL(base).host;
  return { ...manifest, base_url: base, port: Number(new URL(base).port), approved_hosts: [host] };
}

export function fixtureToolset(): { tools: ToolDefinition[]; contracts: ToolContract[] } {
  const read = <T>(rel: string) => JSON.parse(fs.readFileSync(path.join(REPO_ROOT, "fixtures", rel), "utf8")) as T;
  const contracts = read<ToolContract[]>("contracts/shop.contracts.json");
  const tools = read<ToolDefinition[]>("tools/shop.tools.json").filter((t) => contracts.some((c) => c.tool_id === t.tool_id));
  return { tools, contracts };
}

export interface Harness {
  url: string;
  call: <T = Record<string, unknown>>(method: string, p: string, body?: unknown) => Promise<{ status: number; body: T }>;
  close: () => Promise<void>;
}

export async function startHarness(apps: string[] = ["shop"]): Promise<Harness> {
  const running: RunningApp[] = [];
  const manifests: AppManifest[] = [];
  for (const app of apps) {
    const r = await startSeedApp(app);
    running.push(r);
    manifests.push(withPort(JSON.parse(fs.readFileSync(manifestPath(app), "utf8")) as AppManifest, r.base));
  }
  const sandbox: Sandbox = createSandbox({ manifests });
  const server: Server = await new Promise((resolve) => {
    const s = sandbox.app.listen(0, "127.0.0.1", () => resolve(s));
  });
  const url = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
  return {
    url,
    async call(method, p, body) {
      const res = await fetch(url + p, { method, headers: body === undefined ? {} : { "content-type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });
      return { status: res.status, body: (await res.json()) as never };
    },
    async close() {
      await new Promise<void>((resolve) => server.close(() => resolve()));
      await sandbox.close();
      for (const r of running) await r.close();
    },
  };
}

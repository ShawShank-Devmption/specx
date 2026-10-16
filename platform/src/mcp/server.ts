/**
 * SpecX MCP server: exposes one app's *verified* tools to any MCP client (Claude Code, Claude Desktop, …).
 * Every call runs inside a sandbox session, so contracts, quarantine and leak detection still apply; the
 * client gets the tool's output plus the contract-check result. Quarantined tools are never listed.
 *
 *   claude mcp add specx-shop -- npx --prefix <repo>/platform tsx <repo>/platform/src/mcp/server.ts --app shop
 *
 * Needs the seed app running (`make apps`) and `make generate verify` (or the full pipeline) done first.
 * The low-level `Server` is used on purpose: tool schemas are JSON Schema generated at runtime, not zod.
 */
import fs from "node:fs";
import { pathToFileURL } from "node:url";
import { parseArgs } from "node:util";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { CallToolRequestSchema, ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";
import { chromium, type Browser } from "playwright";
import type { AppManifest, ToolContract, ToolDefinition } from "../contracts/types.js";
import { validate } from "../contracts/validate.js";
import { log } from "../log.js";
import { contractsPath, manifestPath, toolsPath } from "../paths.js";
import { Session } from "../sandbox/session.js";

export interface SpecxMcp {
  server: Server;
  session: Session;
  close: () => Promise<void>;
}

interface Options {
  manifest: AppManifest;
  tools: ToolDefinition[];
  contracts: ToolContract[];
  browser: Browser;
  postObserveMs?: number;
}

const text = (t: string) => ({ type: "text" as const, text: t });

export async function createMcpServer(o: Options): Promise<SpecxMcp> {
  const verified = o.tools.filter((t) => t.status === "verified");
  const byName = new Map(verified.map((t) => [t.name, t]));
  const session = await Session.create(o.browser, o.manifest);
  session.loadTools(
    verified,
    o.contracts.filter((c) => byName.has(c.tool_id.split(".").at(-1) ?? "")),
  );
  const server = new Server({ name: `specx-${o.manifest.app}`, version: "0.1.0" }, { capabilities: { tools: {} } });

  server.setRequestHandler(ListToolsRequestSchema, async () => ({
    tools: verified.map((t) => ({
      name: t.name,
      description: t.description,
      inputSchema: t.input_schema as { type: "object"; properties?: Record<string, object>; required?: string[] },
      annotations: { readOnlyHint: t.risk_level === "read", destructiveHint: t.risk_level === "delete" || t.risk_level === "payment" },
    })),
  }));

  server.setRequestHandler(CallToolRequestSchema, async (req) => {
    const tool = byName.get(req.params.name);
    if (!tool) {
      const quarantined = o.tools.some((t) => t.name === req.params.name && t.status === "quarantined");
      return { isError: true, content: [text(`"${req.params.name}" is not a verified tool for ${o.manifest.app}${quarantined ? " (it is quarantined: it failed contract verification)" : ""}.`)] };
    }
    const v = await session.invoke(tool.tool_id, (req.params.arguments ?? {}) as Record<string, unknown>, { source: "mcp", postObserveMs: o.postObserveMs ?? 500 });
    const issues = v.violations.map((x) => `${x.category ?? "violation"} ${x.clause_id} (${x.severity})`);
    const check = text(`SpecX contract check: ${v.status}${issues.length ? ` — ${issues.join("; ")}` : ""} [run ${v.run_id}]`);
    if (v.status === "error" || v.violations.some((x) => x.category === "precondition")) {
      const err = session.events(0).find((e) => e.run_id === v.run_id && e.kind === "tool_end")?.data.error;
      return { isError: true, content: [text(typeof err === "string" ? err : "the call violated a precondition"), check] };
    }
    return { isError: v.status === "fail", content: [text(JSON.stringify(v.output ?? null)), check] };
  });

  return {
    server,
    session,
    async close() {
      await server.close();
      await session.close();
    },
  };
}

async function main(): Promise<void> {
  const { values } = parseArgs({ options: { app: { type: "string" }, observe: { type: "string", default: "500" } } });
  if (!values.app) throw new Error("usage: specx-mcp --app <shop|admin>");
  const read = <T>(file: string): T => {
    if (!fs.existsSync(file)) throw new Error(`missing ${file}: run make generate verify first`);
    return JSON.parse(fs.readFileSync(file, "utf8")) as T;
  };
  const manifest = validate<AppManifest>("app_manifest", read(manifestPath(values.app)));
  const health = await fetch(`${manifest.base_url}/login`).catch(() => null);
  if (!health?.ok) throw new Error(`${manifest.app} is not reachable at ${manifest.base_url}: run make apps first`);
  const browser = await chromium.launch();
  const tools = read<ToolDefinition[]>(toolsPath(values.app));
  const mcp = await createMcpServer({ manifest, tools, contracts: read(contractsPath(values.app)), browser, postObserveMs: Number(values.observe) });
  await mcp.server.connect(new StdioServerTransport());
  log("mcp").info("serving", { app: manifest.app, verified_tools: tools.filter((t) => t.status === "verified").map((t) => t.name) });
  const stop = async () => {
    await mcp.close();
    await browser.close();
    process.exit(0);
  };
  process.on("SIGINT", () => void stop());
  process.on("SIGTERM", () => void stop());
  process.stdin.on("close", () => void stop());
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) {
  main().catch((err: unknown) => {
    process.stderr.write(`specx-mcp: ${(err as Error).message}\n`);
    process.exit(1);
  });
}

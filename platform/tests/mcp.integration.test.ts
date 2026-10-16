import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { chromium, type Browser } from "playwright";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import type { AppManifest, ToolContract, ToolDefinition, Verdict } from "../src/contracts/types.js";
import { createMcpServer, type SpecxMcp } from "../src/mcp/server.js";
import { manifestPath, REPO_ROOT, verdictsPath } from "../src/paths.js";
import { integration, withPort } from "./helpers/sandbox.js";
import { startSeedApp, type RunningApp } from "./helpers/seedapp.js";

type Text = { type: string; text: string };

describe.runIf(integration)("SpecX MCP server (integration)", () => {
  let app: RunningApp;
  let browser: Browser;
  let mcp: SpecxMcp;
  const client = new Client({ name: "test", version: "0.0.0" });

  beforeAll(async () => {
    process.env.SPECX_RESULTS_DIR = fs.mkdtempSync(path.join(os.tmpdir(), "specx-mcp-"));
    app = await startSeedApp("shop");
    browser = await chromium.launch();
    const manifest = withPort(JSON.parse(fs.readFileSync(manifestPath("shop"), "utf8")) as AppManifest, app.base);
    const read = <T>(rel: string) => JSON.parse(fs.readFileSync(path.join(REPO_ROOT, "fixtures", rel), "utf8")) as T;
    const tools = read<ToolDefinition[]>("tools/shop.tools.json").map((t) => (t.name === "place_order" ? { ...t, status: "quarantined" as const } : t));
    const listContract: ToolContract = {
      tool_id: "shop.list_products",
      preconditions: [],
      postconditions: [{ clause_id: "post_one_call", surface: "network", kind: "network_calls", params: { method: "GET", path: "/api/products" }, description: "one call", severity: "high" }],
      invariants: [],
    };
    const contracts = [...read<ToolContract[]>("contracts/shop.contracts.json"), listContract];
    mcp = await createMcpServer({ manifest, tools, contracts, browser, postObserveMs: 200 });
    const [a, b] = InMemoryTransport.createLinkedPair();
    await mcp.server.connect(a);
    await client.connect(b);
  });
  afterAll(async () => {
    await client?.close();
    await mcp?.close();
    await browser?.close();
    await app?.close();
  });

  it("lists only verified tools, with read-only and destructive hints", async () => {
    const { tools } = await client.listTools();
    expect(tools.map((t) => t.name)).toEqual(["list_products", "add_to_cart"]);
    expect(tools[0]?.annotations).toMatchObject({ readOnlyHint: true, destructiveHint: false });
    expect(tools[1]?.inputSchema).toMatchObject({ type: "object", required: ["product_id", "qty"] });
  });

  it("runs a call through the sandbox, returns the output and the verification result", async () => {
    const res = await client.callTool({ name: "add_to_cart", arguments: { product_id: 1, qty: 1 } });
    const [out, check] = res.content as Text[];
    expect(res.isError).toBeFalsy();
    expect(JSON.parse(out!.text)).toMatchObject({ cart_item_id: 1 });
    expect(check!.text).toMatch(/^SpecX contract check: pass/);
    const v = fs.readFileSync(verdictsPath("mcp"), "utf8").trim().split("\n").map((l) => JSON.parse(l) as Verdict);
    expect(v.at(-1)).toMatchObject({ tool_id: "shop.add_to_cart", source: "mcp", status: "pass" });
  });

  it("refuses quarantined or unknown tools", async () => {
    const res = await client.callTool({ name: "place_order", arguments: { confirm: true } });
    expect(res.isError).toBe(true);
    expect((res.content as Text[])[0]!.text).toContain("not a verified tool");
  });

  it("reports handler failures as tool errors", async () => {
    const res = await client.callTool({ name: "add_to_cart", arguments: { product_id: 99, qty: 1 } });
    expect(res.isError).toBe(true);
    expect((res.content as Text[]).map((c) => c.text).join(" ")).toMatch(/404|precondition/);
  });
});

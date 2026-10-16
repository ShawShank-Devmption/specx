import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { describe, expect, it } from "vitest";
import type { ToolContract, ToolDefinition } from "../src/contracts/types.js";
import { exportWebMCP } from "../src/export/webmcp.js";
import { REPO_ROOT } from "../src/paths.js";

const tools = JSON.parse(fs.readFileSync(path.join(REPO_ROOT, "fixtures/tools/shop.tools.json"), "utf8")) as ToolDefinition[];
const contracts = JSON.parse(fs.readFileSync(path.join(REPO_ROOT, "fixtures/contracts/shop.contracts.json"), "utf8")) as ToolContract[];

interface Registered {
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
  annotations?: Record<string, unknown>;
  execute: (input: Record<string, unknown>) => Promise<{ content: { type: string; text: string }[]; isError?: boolean }>;
}

/** Runs the exported script in a sandboxed context with a fake WebMCP host and a fake fetch. */
async function load(script: string, host: "document" | "navigator" | "none", fetchImpl: (url: string, init?: { method?: string; body?: string }) => Promise<unknown>, pathname = "/products") {
  const registered: Registered[] = [];
  const modelContext = { registerTool: async (t: Registered) => void registered.push(t) };
  const ctx: Record<string, unknown> = {
    document: host === "document" ? { modelContext } : {},
    navigator: host === "navigator" ? { modelContext } : {},
    fetch: fetchImpl,
    console: { info: () => undefined, warn: () => undefined, error: () => undefined },
    encodeURIComponent,
    JSON,
    location: { pathname, href: `http://127.0.0.1:5101${pathname}` },
  };
  ctx.window = ctx;
  await vm.runInNewContext(script, ctx);
  await new Promise((r) => setTimeout(r, 0));
  return { registered, ctx };
}

const ok = (body: unknown) => async () => ({ ok: true, status: 200, json: async () => body, text: async () => JSON.stringify(body) });

describe("exportWebMCP", () => {
  const { script, manifest } = exportWebMCP("shop", tools, contracts);

  it("exports only verified tools and lists the quarantined ones", () => {
    expect(manifest.tools.map((t) => t.name)).toEqual(["list_products", "add_to_cart"]);
    expect(manifest.quarantined).toEqual([]);
    expect(manifest.excluded).toEqual([{ name: "place_order", status: "generated" }]);
    expect(manifest.tools[1]).toMatchObject({ risk_level: "write", contract: { preconditions: 2, postconditions: 4, invariants: 4 } });
  });

  it("registers every exported tool on document.modelContext with the WebMCP tool shape", async () => {
    const { registered } = await load(script, "document", ok([]));
    expect(registered.map((t) => t.name)).toEqual(["list_products", "add_to_cart"]);
    expect(registered[1]).toMatchObject({ description: tools[1]?.description, inputSchema: tools[1]?.input_schema, annotations: { readOnlyHint: false } });
    expect(registered[0]?.annotations).toEqual({ readOnlyHint: true });
  });

  it("falls back to navigator.modelContext (older drafts, MCP-B polyfill)", async () => {
    expect((await load(script, "navigator", ok([]))).registered).toHaveLength(2);
  });

  it("exposes the tools on window when no WebMCP host exists", async () => {
    const { ctx } = await load(script, "none", ok([]));
    expect((ctx.__specxWebMCPTools as Registered[]).map((t) => t.name)).toEqual(["list_products", "add_to_cart"]);
  });

  it("executes the verified handler and returns WebMCP text content", async () => {
    const calls: { url: string; method?: string; body?: string }[] = [];
    const fetchImpl = async (url: string, init?: { method?: string; body?: string }) => {
      calls.push({ url, ...(init?.method ? { method: init.method } : {}), ...(init?.body ? { body: init.body } : {}) });
      const body = { cart_item_id: 9, cart_total_cents: 1299 };
      return { ok: true, status: 201, json: async () => body, text: async () => JSON.stringify(body) };
    };
    const { registered } = await load(script, "document", fetchImpl);
    const res = await registered[1]!.execute({ product_id: 1, qty: 1 });
    expect(calls).toEqual([{ url: "/api/cart", method: "POST", body: JSON.stringify({ product_id: 1, qty: 1 }) }]);
    expect(JSON.parse(res.content[0]!.text)).toEqual({ cart_item_id: 9, cart_total_cents: 1299 });
    expect(res.isError).toBeUndefined();
  });

  it("reports handler failures as WebMCP errors instead of throwing", async () => {
    const { registered } = await load(script, "document", async () => ({ ok: false, status: 404, text: async () => '{"error":"product not found"}' }));
    const res = await registered[1]!.execute({ product_id: 99, qty: 1 });
    expect(res.isError).toBe(true);
    expect(res.content[0]!.text).toContain("404");
  });

  const removeTool: ToolDefinition = {
    ...tools[1]!,
    tool_id: "shop.remove_from_cart",
    name: "remove_from_cart",
    risk_level: "delete",
    handler: { kind: "ui", code: "async (input) => ({ removed: input.product_id })", page: "/cart", page_example: "/cart", selectors: ["[data-testid=remove-from-cart]"] },
  };
  const scoped = exportWebMCP("shop", [...tools, removeTool], contracts);

  it("records each tool's kind, page and whether it asks the user", () => {
    expect(scoped.manifest.tools.map((t) => [t.name, t.kind, t.page, t.confirm])).toEqual([
      ["list_products", "api", "*", false],
      ["add_to_cart", "api", "*", false],
      ["remove_from_cart", "ui", "/cart", true],
    ]);
  });

  it("registers a page-scoped tool only on its own page", async () => {
    expect((await load(scoped.script, "document", ok([]), "/products/1")).registered.map((t) => t.name)).toEqual(["list_products", "add_to_cart"]);
    expect((await load(scoped.script, "document", ok([]), "/cart")).registered.map((t) => t.name)).toEqual(["list_products", "add_to_cart", "remove_from_cart"]);
  });
});

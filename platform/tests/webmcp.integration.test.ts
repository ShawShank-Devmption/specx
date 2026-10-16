import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { chromium, type Browser } from "playwright";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import type { ToolContract, ToolDefinition } from "../src/contracts/types.js";
import { exportWebMCP } from "../src/export/webmcp.js";
import { REPO_ROOT, resultsDir } from "../src/paths.js";
import { integration } from "./helpers/sandbox.js";
import { Client, startSeedApp, type RunningApp } from "./helpers/seedapp.js";

// Stand-in for a WebMCP-capable browser: collects registrations the way document.modelContext would.
const HOST = `Object.defineProperty(document, "modelContext", { value: { registerTool: async (t) => { (window.__registered ||= []).push(t); } } });`;

describe.runIf(integration)("WebMCP export served by the site (integration)", () => {
  let app: RunningApp;
  let browser: Browser;

  beforeAll(async () => {
    process.env.SPECX_RESULTS_DIR = fs.mkdtempSync(path.join(os.tmpdir(), "specx-webmcp-"));
    const read = <T>(rel: string) => JSON.parse(fs.readFileSync(path.join(REPO_ROOT, "fixtures", rel), "utf8")) as T;
    const { script } = exportWebMCP("shop", read<ToolDefinition[]>("tools/shop.tools.json"), read<ToolContract[]>("contracts/shop.contracts.json"));
    fs.mkdirSync(path.join(resultsDir(), "webmcp"), { recursive: true });
    fs.writeFileSync(path.join(resultsDir(), "webmcp", "shop.webmcp.js"), script);
    app = await startSeedApp("shop");
    browser = await chromium.launch();
  });
  afterAll(async () => {
    await browser?.close();
    await app?.close();
  });

  it("registers the verified tools in the page and runs them against the live app", async () => {
    const tenant = "webmcp-it";
    const http = new Client(app.base, tenant);
    await http.req("POST", "/__test/reset", {});
    const context = await browser.newContext({ baseURL: app.base });
    await context.addCookies([{ name: "specx_tenant", value: tenant, url: app.base }]);
    await context.addInitScript({ content: HOST });
    await context.request.post(`${app.base}/api/login`, { data: { username: "alice", password: "alice123" } });
    const page = await context.newPage();
    await page.goto("/products");
    await page.waitForFunction(() => (window as unknown as { __registered?: unknown[] }).__registered?.length === 2);
    const names = await page.evaluate(() => (window as unknown as { __registered: { name: string }[] }).__registered.map((t) => t.name));
    expect(names).toEqual(["list_products", "add_to_cart"]);
    const result = await page.evaluate(async () => {
      const tools = (window as unknown as { __registered: { name: string; execute: (i: unknown) => Promise<{ content: { text: string }[] }> }[] }).__registered;
      return (await tools.find((t) => t.name === "add_to_cart")!.execute({ product_id: 1, qty: 2 })).content[0]!.text;
    });
    expect(JSON.parse(result)).toMatchObject({ cart_item_id: 1 });
    expect((await http.db()).cart_items?.count).toBe(1);
    await context.close();
  });

  it("serves an inert script when nothing has been exported for the app", async () => {
    fs.rmSync(path.join(resultsDir(), "webmcp", "shop.webmcp.js"));
    const res = await fetch(`${app.base}/webmcp.js`);
    expect(res.headers.get("content-type")).toContain("javascript");
    expect(await res.text()).toContain("no SpecX WebMCP export");
  });
});

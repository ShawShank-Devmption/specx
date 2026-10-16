import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { chromium, type Browser, type Page } from "playwright";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import type { AppManifest, ToolDefinition } from "../src/contracts/types.js";
import { exportWebMCP } from "../src/export/webmcp.js";
import { templateNamer } from "../src/generator/emit.js";
import { generate, type GenerateResult } from "../src/generator/index.js";
import { manifestPath, resultsDir } from "../src/paths.js";
import { Session } from "../src/sandbox/session.js";
import { verifyTools, type ToolVerification } from "../src/verify/run.js";
import { integration, withPort } from "./helpers/sandbox.js";
import { Client, startSeedApp, type RunningApp } from "./helpers/seedapp.js";

// Stand-in for a WebMCP browser: records registrations the way document.modelContext does.
const HOST = `Object.defineProperty(document, "modelContext", { value: { registerTool: async (t) => { (window.__registered ||= []).push(t); } } });`;
type Result = { content: { text: string }[]; isError?: boolean };

describe.runIf(integration)("WebMCP-native tools: generate, verify, export, use in the page (integration)", () => {
  let app: RunningApp;
  let browser: Browser;
  let gen: GenerateResult;
  let verified: ToolVerification[];
  let tools: ToolDefinition[];

  beforeAll(async () => {
    process.env.SPECX_RESULTS_DIR = fs.mkdtempSync(path.join(os.tmpdir(), "specx-webmcp-ui-"));
    app = await startSeedApp("shop");
    browser = await chromium.launch();
    const manifest = withPort(JSON.parse(fs.readFileSync(manifestPath("shop"), "utf8")) as AppManifest, app.base);
    gen = await generate(manifest, browser, { namer: templateNamer });
    const session = await Session.create(browser, manifest);
    verified = await verifyTools(session, gen.webmcp.tools, gen.webmcp.contracts, { runs: 2, postObserveMs: 400 });
    await session.close();
    const status = new Map(verified.map((v) => [v.tool_id, v.decision.status]));
    tools = gen.webmcp.tools.map((t) => ({ ...t, status: status.get(t.tool_id) ?? "generated" }));
    const { script } = exportWebMCP("shop", tools, gen.webmcp.contracts);
    fs.mkdirSync(path.join(resultsDir(), "webmcp"), { recursive: true });
    fs.writeFileSync(path.join(resultsDir(), "webmcp", "shop.webmcp.js"), script);
  }, 300_000);
  afterAll(async () => {
    await browser?.close();
    await app?.close();
  });

  async function open(tenant: string, pathName: string): Promise<Page> {
    const context = await browser.newContext({ baseURL: app.base });
    await context.addCookies([{ name: "specx_tenant", value: tenant, url: app.base }]);
    await context.addInitScript({ content: HOST });
    await context.request.post(`${app.base}/api/login`, { data: { username: "alice", password: "alice123" } });
    const page = await context.newPage();
    await page.goto(pathName);
    await page.waitForFunction(() => Array.isArray((window as unknown as { __registered?: unknown[] }).__registered));
    return page;
  }
  const names = (page: Page) => page.evaluate(() => (window as unknown as { __registered: { name: string }[] }).__registered.map((t) => t.name));
  const run = (page: Page, name: string, input: object) =>
    page.evaluate(
      ([n, i]) => (window as unknown as { __registered: { name: string; execute: (x: unknown) => Promise<Result> }[] }).__registered.find((t) => t.name === n)!.execute(i),
      [name, input] as const,
    ) as Promise<Result>;

  it("generates write tools that act through the page, scoped to their page", () => {
    const byName = new Map(gen.webmcp.tools.map((t) => [t.name, t]));
    expect(byName.get("add_to_cart")?.handler).toMatchObject({ kind: "ui", page: "/products/:id" });
    expect(Object.keys(byName.get("add_to_cart")?.input_schema.properties as object)).toEqual(["qty"]);
    expect(byName.get("remove_from_cart")?.handler).toMatchObject({ kind: "ui", page: "/cart" });
    expect(byName.get("place_order")?.handler).toMatchObject({ kind: "ui", page: "/cart" });
    expect(byName.get("list_products")?.handler).toMatchObject({ kind: "api", page: "*" });
  });

  it("verifies the ui tools in the sandbox and still catches the checkout race", () => {
    const status = Object.fromEntries(verified.map((v) => [v.tool_id.split(".")[1], v.decision.status]));
    expect(status).toMatchObject({ add_to_cart: "verified", remove_from_cart: "verified", place_order: "quarantined" });
    expect(verified.find((v) => v.tool_id === "shop.place_order")?.decision.reasons.map((r) => (r.kind === "violation" ? r.category : r.kind))).toContain("race");
  });

  it("offers each tool only on its page and never the quarantined checkout", async () => {
    const product = await open("ui-scope", "/products/3");
    expect(await names(product)).toContain("add_to_cart");
    expect(await names(product)).not.toContain("remove_from_cart");
    const cart = await open("ui-scope", "/cart");
    expect(await names(cart)).not.toContain("add_to_cart");
    expect(await names(cart)).not.toContain("place_order");
  });

  it("adds to the cart through the page: the user sees it, the server has it", async () => {
    const http = new Client(app.base, "ui-add");
    await http.req("POST", "/__test/reset", {});
    const page = await open("ui-add", "/products/3");
    const res = await run(page, "add_to_cart", { qty: 2 });
    expect(res.isError).toBeFalsy();
    expect(JSON.parse(res.content[0]!.text)).toMatchObject({ cart_item_id: 1 });
    await expect.poll(() => page.locator("[role=status]").innerText()).toBe("Added to cart");
    expect((await http.db()).cart_items?.rows).toMatchObject([{ product_id: 3, qty: 2 }]);
  });

  it("asks the user before removing, and respects Deny then Allow", async () => {
    const http = new Client(app.base, "ui-remove");
    await http.req("POST", "/__test/reset", {});
    await http.req("POST", "/__test/apply", { state: { cart: [{ product_id: 3, qty: 1 }] } });
    const page = await open("ui-remove", "/cart");
    const denied = run(page, "remove_from_cart", { product_id: 3 });
    await page.locator('[data-specx-confirm="reject"]').click();
    expect((await denied).isError).toBe(true);
    expect((await http.db()).cart_items?.count).toBe(1);
    const allowed = run(page, "remove_from_cart", { product_id: 3 });
    await expect.poll(() => page.getByRole("alertdialog").innerText()).toContain("remove_from_cart");
    await page.locator('[data-specx-confirm="accept"]').click();
    expect(JSON.parse((await allowed).content[0]!.text)).toMatchObject({ removed_qty: 1 });
    expect((await http.db()).cart_items?.count).toBe(0);
  });
});

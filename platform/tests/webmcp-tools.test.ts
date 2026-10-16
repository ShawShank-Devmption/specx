import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import type { AppManifest, ToolDefinition } from "../src/contracts/types.js";
import { validate } from "../src/contracts/validate.js";
import { buildCandidates, type DomTrigger, type NetworkSample } from "../src/generator/candidates.js";
import { templateNamer } from "../src/generator/emit.js";
import { parseRoutes } from "../src/generator/repo.js";
import { buildWebmcpTools } from "../src/generator/webmcp.js";
import { manifestPath, SEED_APPS_DIR } from "../src/paths.js";

const manifest = JSON.parse(fs.readFileSync(manifestPath("shop"), "utf8")) as AppManifest;
const routes = parseRoutes(path.join(SEED_APPS_DIR, "shop", "server.js"));

// Shaped like what the crawler records for the real shop pages.
const triggers: DomTrigger[] = [
  {
    page: "/products/:id",
    pagePath: "/products/1",
    selector: "[data-testid=add-to-cart]",
    role: "button",
    name: "Add to cart",
    testid: "add-to-cart",
    data: { "data-product-id": "1" },
    inputs: [{ name: "qty", tag: "input", type: "number", min: 1, max: 10 }],
    requests: [{ method: "POST", path: "/api/cart", pattern: "/api/cart", body: { product_id: 1, qty: 1 } }],
    after: { url: "/products/1", status: "Added to cart" },
  },
  {
    page: "/cart",
    pagePath: "/cart",
    selector: "[data-testid=remove-from-cart]",
    role: "button",
    name: "Remove from cart",
    testid: "remove-from-cart",
    data: { "data-product-id": "1" },
    inputs: [],
    requests: [{ method: "DELETE", path: "/api/cart/1", pattern: "/api/cart/:product_id" }],
    after: { url: "/cart", status: "" },
  },
  {
    page: "/cart",
    pagePath: "/cart",
    selector: "[data-testid=checkout]",
    role: "button",
    name: "Place order",
    testid: "checkout",
    data: {},
    inputs: [],
    requests: [{ method: "POST", path: "/api/orders", pattern: "/api/orders", body: { confirm: true } }],
    after: { url: "/orders", status: "" },
  },
];
const samples: NetworkSample[] = [{ method: "GET", path: "/api/products", pattern: "/api/products", status: 200, response: [{ id: 1, name: "Blue Mug", price_cents: 1299, stock: 25 }] }];

const { candidates } = buildCandidates(routes, triggers, samples, manifest);
const built = await buildWebmcpTools(candidates, manifest, templateNamer);
const tool = (name: string) => built.tools.find((t) => t.name === name) as ToolDefinition;
const contract = (name: string) => built.contracts.find((c) => c.tool_id === `shop.${name}`)!;
const props = (name: string) => Object.keys((tool(name).input_schema.properties ?? {}) as object);

describe("buildWebmcpTools", () => {
  it("makes state-changing tools that drive the page's own controls, scoped to their page", () => {
    for (const t of built.tools) validate("tool_definition", t);
    expect(tool("add_to_cart").handler).toMatchObject({ kind: "ui", page: "/products/:id", page_example: "/products/1", selectors: ["[data-testid=add-to-cart]"] });
    expect(tool("add_to_cart").handler.code).toContain(".click()");
    expect(tool("add_to_cart").handler.code).not.toMatch(/fetch\(`?\/api/);
    expect(tool("place_order").handler).toMatchObject({ kind: "ui", page: "/cart" });
  });

  it("takes context from the page, not from arguments", () => {
    expect(props("add_to_cart")).toEqual(["qty"]);
    expect(tool("add_to_cart").input_schema).toMatchObject({ properties: { qty: { type: "integer", minimum: 1, maximum: 10 } }, required: ["qty"] });
    expect(props("place_order")).toEqual([]);
  });

  it("lets the agent pick which row a per-row button acts on", () => {
    expect(props("remove_from_cart")).toEqual(["product_id"]);
    expect(tool("remove_from_cart").handler.code).toContain('[data-product-id="');
  });

  it("keeps reads as page-independent API tools", () => {
    expect(tool("list_products").handler).toMatchObject({ kind: "api", page: "*" });
  });

  it("skips write routes no UI control performs", () => {
    expect(built.tools.map((t) => t.name)).not.toContain("delete_cart");
    expect(built.skipped.map((s) => s.ref)).toEqual([]);
  });

  it("adapts contracts: control must be present, page context replaces argument preconditions, UI effects are checked", () => {
    const add = contract("add_to_cart");
    validate("contract", add);
    expect(add.preconditions.map((p) => p.kind)).toEqual(["auth_state", "dom_exists"]);
    expect(add.preconditions[1]?.params).toEqual({ selector: "[data-testid=add-to-cart]" });
    expect(add.postconditions.find((p) => p.kind === "dom_text_contains")?.params).toEqual({ selector: "[role=status]", text: "Added to cart" });
    expect(add.postconditions.find((p) => p.clause_id === "post_db_cart_items")).toBeDefined();
    expect(contract("place_order").postconditions.find((p) => p.kind === "url_matches")?.params).toEqual({ pattern: "^https?://[^/]+/orders(?:[?#].*)?$" });
    expect(contract("remove_from_cart").preconditions.map((p) => p.params)).toContainEqual({ table: "cart_items", where: { user_id: "$user.id", product_id: "$args.product_id" } });
  });
});

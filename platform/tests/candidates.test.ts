import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import type { AppManifest, ToolDefinition } from "../src/contracts/types.js";
import { validate } from "../src/contracts/validate.js";
import { buildCandidates, type DomTrigger, type NetworkSample } from "../src/generator/candidates.js";
import { emitTool, templateNamer } from "../src/generator/emit.js";
import { parseRoutes } from "../src/generator/repo.js";
import { manifestPath, SEED_APPS_DIR } from "../src/paths.js";

const manifest = JSON.parse(fs.readFileSync(manifestPath("shop"), "utf8")) as AppManifest;
const routes = parseRoutes(path.join(SEED_APPS_DIR, "shop", "server.js"));

const addTrigger: DomTrigger = {
  page: "/products/:id",
  selector: "[data-testid=add-to-cart]",
  role: "button",
  name: "Add to cart",
  testid: "add-to-cart",
  inputs: [{ name: "qty", tag: "input", type: "number", min: 1, max: 10 }],
  requests: [{ method: "POST", path: "/api/cart", pattern: "/api/cart", body: { product_id: 1, qty: 1 } }],
};
const buyNow: DomTrigger = {
  ...addTrigger,
  selector: "[data-testid=buy-now]",
  name: "Buy now",
  testid: "buy-now",
  requests: [
    { method: "POST", path: "/api/cart", pattern: "/api/cart", body: { product_id: 1, qty: 1 } },
    { method: "POST", path: "/api/orders", pattern: "/api/orders", body: { confirm: true } },
  ],
};
const checkout: DomTrigger = {
  page: "/cart",
  selector: "[data-testid=checkout]",
  role: "button",
  name: "Place order",
  testid: "checkout",
  inputs: [],
  requests: [{ method: "POST", path: "/api/orders", pattern: "/api/orders", body: { confirm: true } }],
};
const samples: NetworkSample[] = [
  { method: "GET", path: "/api/products", pattern: "/api/products", status: 200, response: [{ id: 1, name: "Blue Mug", price_cents: 1299, stock: 25 }] },
  { method: "GET", path: "/api/products/1", pattern: "/api/products/:id", status: 200, response: { id: 1, name: "Blue Mug", price_cents: 1299, stock: 25 } },
  { method: "POST", path: "/api/cart", pattern: "/api/cart", status: 201, request: { product_id: 1, qty: 1 }, response: { cart_item_id: 1, cart_total_cents: 1299 } },
  { method: "POST", path: "/api/orders", pattern: "/api/orders", status: 201, request: { confirm: true }, response: { order_id: 1, total_cents: 1299 } },
];

const { candidates, rejected } = buildCandidates(routes, [addTrigger, buyNow, checkout], samples, manifest);
const cand = (m: string, p: string) => candidates.find((c) => c.route.method === m && c.route.path === p);

describe("buildCandidates", () => {
  it("makes one candidate per approved API route and skips login, pages and unapproved routes", () => {
    expect(candidates.map((c) => `${c.route.method} ${c.route.path}`)).toEqual([
      "GET /api/products",
      "GET /api/products/:id",
      "GET /api/cart",
      "POST /api/cart",
      "DELETE /api/cart/:product_id",
      "POST /api/orders",
      "GET /api/orders",
    ]);
    expect(rejected).toContainEqual({ ref: "POST /api/analytics", reason: "route is not an approved endpoint in the app manifest" });
  });

  it("rejects non-atomic UI triggers as evidence (emit_rejects_non_atomic)", () => {
    expect(rejected).toContainEqual({ ref: "[data-testid=buy-now]", reason: "trigger fires 2 state-changing endpoints; not atomic" });
    expect(cand("POST", "/api/cart")?.triggers.map((t) => t.name)).toEqual(["Add to cart"]);
  });

  it("fuses input types from samples, bounds from the DOM and constants from observed bodies", () => {
    expect(cand("POST", "/api/cart")?.inputs).toEqual([
      { name: "product_id", type: "integer", required: true, source: "body" },
      { name: "qty", type: "integer", required: true, source: "body", minimum: 1, maximum: 10 },
    ]);
    expect(cand("POST", "/api/orders")?.inputs).toEqual([{ name: "confirm", type: "boolean", required: true, source: "body", const: true }]);
    expect(cand("DELETE", "/api/cart/:product_id")?.inputs).toEqual([{ name: "product_id", type: "integer", required: true, source: "path" }]);
  });

  it("derives output schemas from observed responses, wrapping arrays in items", () => {
    expect(cand("GET", "/api/products")?.outputSchema).toEqual({
      type: "object",
      required: ["items"],
      properties: { items: { type: "array", items: { type: "object", properties: { id: { type: "integer" }, name: { type: "string" }, price_cents: { type: "integer" }, stock: { type: "integer" } } } } },
    });
    expect(cand("GET", "/api/cart")?.outputSchema).toBeUndefined();
  });
});

describe("emitTool + templateNamer", () => {
  const emit = async (m: string, p: string) => validate<ToolDefinition>("tool_definition", await emitTool(cand(m, p)!, manifest, templateNamer));

  it("names from the triggering button's accessible name, else from method and resource", async () => {
    expect((await emit("POST", "/api/cart")).name).toBe("add_to_cart");
    expect((await emit("POST", "/api/orders")).name).toBe("place_order");
    expect((await emit("GET", "/api/products")).name).toBe("list_products");
    expect((await emit("GET", "/api/products/:id")).name).toBe("get_product");
    expect((await emit("GET", "/api/cart")).name).toBe("view_cart");
    expect((await emit("DELETE", "/api/cart/:product_id")).name).toBe("delete_cart");
  });

  it("emits an api handler, schema, risk level and multi-surface provenance", async () => {
    const t = await emit("POST", "/api/cart");
    expect(t).toMatchObject({ tool_id: "shop.add_to_cart", risk_level: "write", atomic: true, version: 1, metadata_revision: 0, status: "generated", handler: { kind: "api", http: { method: "POST", path_template: "/api/cart" }, selectors: ["[data-testid=add-to-cart]"] } });
    expect(t.input_schema).toMatchObject({ type: "object", required: ["product_id", "qty"], additionalProperties: false, properties: { qty: { type: "integer", minimum: 1, maximum: 10 } } });
    expect(new Set(t.provenance.map((p) => p.surface))).toEqual(new Set(["code", "dom", "aria", "network"]));
    expect(t.description).toMatch(/product_id|product/);
  });

  it("puts path params in the URL and the rest in the JSON body", async () => {
    const t = await emit("DELETE", "/api/cart/:product_id");
    expect(t.handler.http?.path_template).toBe("/api/cart/{product_id}");
    expect(t.handler.code).toContain("encodeURIComponent(input.product_id)");
    expect(t.handler.code).not.toContain("body: JSON.stringify");
  });

  it("warns agents about payment actions", async () => {
    expect((await emit("POST", "/api/orders")).description.toLowerCase()).toContain("confirm");
  });
});

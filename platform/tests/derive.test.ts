import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { deriveContract } from "../src/contracts/derive.js";
import type { AppManifest, Clause, ToolContract, ToolDefinition } from "../src/contracts/types.js";
import { validate } from "../src/contracts/validate.js";
import { parseRoutes } from "../src/generator/repo.js";
import { manifestPath, SEED_APPS_DIR } from "../src/paths.js";

const load = (app: string) => ({
  manifest: JSON.parse(fs.readFileSync(manifestPath(app), "utf8")) as AppManifest,
  routes: parseRoutes(path.join(SEED_APPS_DIR, app, "server.js")),
});
const shop = load("shop");
const admin = load("admin");

function contractFor(app: typeof shop, method: string, p: string, risk: ToolDefinition["risk_level"], output?: Record<string, unknown>): ToolContract {
  const route = app.routes.find((r) => r.method === method && r.path === p);
  if (!route) throw new Error(`no route ${method} ${p}`);
  const tool = { tool_id: `${app.manifest.app}.t`, risk_level: risk, ...(output ? { output_schema: output } : {}) } as ToolDefinition;
  return validate<ToolContract>("contract", deriveContract(tool, route, app.manifest));
}
const byId = (cs: Clause[], id: string) => cs.find((c) => c.clause_id === id);

describe("deriveContract", () => {
  it("add_to_cart: login, FK precondition, exact deltas, frames, audit, stock invariant", () => {
    const c = contractFor(shop, "POST", "/api/cart", "write");
    expect(c.preconditions.map((x) => [x.kind, x.params])).toEqual([
      ["auth_state", { logged_in: true }],
      ["db_row_exists", { table: "products", where: { id: "$args.product_id" } }],
    ]);
    expect(byId(c.postconditions, "post_one_call")?.params).toEqual({ method: "POST", path: "/api/cart", min: 1, max: 1 });
    expect(byId(c.postconditions, "post_db_cart_items")?.params).toEqual({ table: "cart_items", inserted: 1, updated: 0, deleted: 0 });
    expect(byId(c.postconditions, "post_db_products")?.params).toEqual({ table: "products", inserted: 0, updated: { min: 0, max: 1 }, deleted: 0 });
    expect(c.postconditions.filter((x) => x.clause_id.startsWith("post_frame_")).map((x) => x.params.table)).toEqual(["users", "orders", "order_items"]);
    expect(byId(c.postconditions, "post_audit")?.params).toEqual({ event: "cart.add", count: 1 });
    expect(c.invariants.map((x) => x.clause_id)).toEqual(["inv_no_unapproved_endpoint", "inv_no_third_party", "inv_storage_untouched", "inv_stock_nonnegative"]);
  });

  it("place_order: cart must be non-empty, multi-row insert, at-most-once on orders", () => {
    const c = contractFor(shop, "POST", "/api/orders", "payment");
    expect(c.preconditions.map((x) => x.params)).toContainEqual({ table: "cart_items", where: { user_id: "$user.id" } });
    expect(byId(c.postconditions, "post_db_order_items")?.params).toMatchObject({ inserted: { min: 1 } });
    expect(byId(c.postconditions, "post_db_cart_items")?.params).toMatchObject({ deleted: { min: 1 } });
    expect(byId(c.invariants, "inv_at_most_once")?.params).toEqual({ table: "orders" });
  });

  it("remove_from_cart: the line to remove must exist for this user", () => {
    const c = contractFor(shop, "DELETE", "/api/cart/:product_id", "delete");
    expect(c.preconditions.map((x) => x.params)).toContainEqual({ table: "cart_items", where: { user_id: "$user.id", product_id: "$args.product_id" } });
  });

  it("get_product: id from the path must exist; read tools get no audit, frames or deltas", () => {
    const c = contractFor(shop, "GET", "/api/products/:id", "read", { type: "object", properties: { id: { type: "integer" } } });
    expect(c.preconditions.map((x) => x.params)).toContainEqual({ table: "products", where: { id: "$args.id" } });
    expect(byId(c.postconditions, "post_audit")).toBeUndefined();
    expect(byId(c.postconditions, "post_output")?.params).toEqual({ schema: { type: "object", properties: { id: { type: "integer" } } } });
  });

  it("admin delete_user: frame on notes catches the hidden trigger; admin invariant attached", () => {
    const c = contractFor(admin, "DELETE", "/api/users/:id", "delete");
    expect(byId(c.postconditions, "post_db_users")?.params).toEqual({ table: "users", inserted: 0, updated: 0, deleted: 1 });
    expect(byId(c.postconditions, "post_frame_notes")?.params).toEqual({ table: "notes", inserted: 0, updated: 0, deleted: 0 });
    expect(byId(c.invariants, "inv_active_admin")).toBeDefined();
  });

  it("admin set_role: expects an audit row for the entity even though the code writes none", () => {
    const c = contractFor(admin, "POST", "/api/users/:id/role", "write");
    expect(byId(c.postconditions, "post_audit")?.params).toEqual({ entity: "users", count: 1 });
  });
});

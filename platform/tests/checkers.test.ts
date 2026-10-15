import { describe, expect, it } from "vitest";
import { check, dbDelta, normaliseObserved } from "../src/contracts/checkers.js";
import type { Clause } from "../src/contracts/types.js";
import { ctx, db, ev, req } from "./helpers/ctx.js";

const clause = (kind: Clause["kind"], params: Record<string, unknown>, id = `post_${kind}`): Clause => ({
  clause_id: id,
  kind,
  params,
  surface: "db",
  description: kind,
  severity: "high",
});

describe("dbDelta", () => {
  it("counts inserted, updated and deleted rows by id", () => {
    const before = db({ t: [{ id: 1, v: 1 }, { id: 2, v: 2 }, { id: 3, v: 3 }] });
    const after = db({ t: [{ id: 1, v: 1 }, { id: 2, v: 9 }, { id: 4, v: 4 }] });
    expect(dbDelta(before, after)).toEqual({ t: { inserted: 1, updated: 1, deleted: 1 } });
  });
});

describe("checkers", () => {
  it("db_delta accepts exact counts and min/max ranges", async () => {
    const after = db({ products: [{ id: 1, stock: 5 }], cart_items: [{ id: 1 }] });
    expect((await check(clause("db_delta", { table: "cart_items", inserted: 1, deleted: 0 }), ctx({ dbAfter: after }), "post")).passed).toBe(true);
    expect((await check(clause("db_delta", { table: "cart_items", inserted: { min: 2 } }), ctx({ dbAfter: after }), "post")).passed).toBe(false);
    expect((await check(clause("db_delta", { table: "orders", inserted: 0, updated: 0, deleted: 0 }), ctx({ dbAfter: after }), "post")).passed).toBe(true);
  });

  it("network_calls fails when the call count exceeds max", async () => {
    const events = [req("POST", "/api/cart"), req("POST", "/api/cart")];
    const r = await check(clause("network_calls", { method: "POST", path: "/api/cart" }), ctx({ events }), "post");
    expect(r).toMatchObject({ passed: false, observed: 2 });
  });

  it("no_unapproved_endpoint reports the offending calls", async () => {
    const events = [req("POST", "/api/cart"), req("POST", "/api/analytics", { approved: false })];
    const r = await check(clause("no_unapproved_endpoint", {}), ctx({ events }), "post");
    expect(r).toMatchObject({ passed: false, observed: ["POST /api/analytics"] });
  });

  it("no_third_party fails on any third-party request", async () => {
    const events = [req("GET", "/p", { host: "tracker.example.invalid", third_party: true, approved: false })];
    expect((await check(clause("no_third_party", {}), ctx({ events }), "post")).passed).toBe(false);
  });

  it("storage_untouched fails with the observed storage writes", async () => {
    const events = [ev("storage", { area: "local", op: "set", key: "__trk" }, "post")];
    expect(await check(clause("storage_untouched", {}), ctx({ events }), "post")).toMatchObject({ passed: false, observed: [{ area: "local", op: "set", key: "__trk" }] });
  });

  it("db_row_exists resolves $args and $user, on dbBefore for preconditions", async () => {
    const before = db({ cart_items: [{ id: 1, user_id: 1, product_id: 3 }] });
    const c = clause("db_row_exists", { table: "cart_items", where: { user_id: "$user.id", product_id: "$args.product_id" } }, "pre_in_cart");
    expect((await check(c, ctx({ dbBefore: before, args: { product_id: 3 } }), "pre")).passed).toBe(true);
    expect((await check(c, ctx({ dbBefore: before, args: { product_id: "3" } }), "pre")).passed).toBe(true);
    expect((await check(c, ctx({ dbBefore: before, args: { product_id: 4 } }), "pre")).passed).toBe(false);
  });

  it("db_no_row supports comparison operators", async () => {
    const after = db({ products: [{ id: 1, stock: -2 }] });
    const c = clause("db_no_row", { table: "products", where: { stock: { op: "<", value: 0 } } }, "inv_stock_nonnegative");
    expect((await check(c, ctx({ dbAfter: after }), "post")).passed).toBe(false);
  });

  it("audit_event matches by event or by entity", async () => {
    const newAudit = [{ id: 1, event: "cart.add", actor: "alice", entity: "cart_items", entity_id: "1", ts: "" }];
    expect((await check(clause("audit_event", { event: "cart.add" }), ctx({ newAudit }), "post")).passed).toBe(true);
    expect((await check(clause("audit_event", { entity: "users", count: 1 }), ctx({ newAudit }), "post")).passed).toBe(false);
  });

  it("at_most_once uses the concurrency group delta when present", async () => {
    const before = db({ orders: [] });
    const after = db({ orders: [{ id: 1 }, { id: 2 }] });
    const r = await check(clause("at_most_once", { table: "orders" }, "inv_at_most_once"), ctx({ group: { dbBefore: before, dbAfter: after } }), "post");
    expect(r).toMatchObject({ passed: false, observed: 2 });
  });

  it("output_matches validates the handler output", async () => {
    const c = clause("output_matches", { schema: { type: "object", required: ["cart_item_id"] } });
    expect((await check(c, ctx({ output: { cart_item_id: 1 } }), "post")).passed).toBe(true);
    expect((await check(c, ctx({ output: { nope: 1 } }), "post")).passed).toBe(false);
  });

  it("dom checks are unverifiable without a page", async () => {
    expect((await check(clause("auth_state", { logged_in: true }), ctx(), "pre")).passed).toBeNull();
  });

  it("dom checks use the probe when present", async () => {
    const dom = { url: () => "http://x/cart", count: async (s: string) => (s === "[data-testid=user-menu]" ? 1 : 0), text: async () => "Total: $5" };
    expect((await check(clause("auth_state", { logged_in: true }), ctx({ dom }), "pre")).passed).toBe(true);
    expect((await check(clause("url_matches", { pattern: "/cart$" }), ctx({ dom }), "post")).passed).toBe(true);
    expect((await check(clause("dom_text_contains", { selector: "body", text: "total" }), ctx({ dom }), "post")).passed).toBe(true);
  });
});

describe("normaliseObserved", () => {
  it("strips ids so signatures are stable across runs", () => {
    expect(normaliseObserved("no_unapproved_endpoint", ["POST /api/analytics", "POST /api/users/12/x"])).toBe("POST /api/analytics,POST /api/users/:n/x");
    expect(normaliseObserved("at_most_once", 2, { table: "orders" })).toBe("orders x2");
    expect(normaliseObserved("db_delta", { inserted: 2, updated: 0, deleted: 0 }, { table: "orders" })).toBe("orders inserted=2 updated=0 deleted=0");
  });
});

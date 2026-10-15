import { describe, expect, it } from "vitest";
import { buildEffectDiff, evaluateRun } from "../src/sandbox/effects.js";
import type { ToolContract } from "../src/contracts/types.js";
import { ctx, db, ev, req } from "./helpers/ctx.js";

const contract: ToolContract = {
  tool_id: "shop.add_to_cart",
  preconditions: [{ clause_id: "pre_product", surface: "db", kind: "db_row_exists", params: { table: "products", where: { id: "$args.product_id" } }, description: "", severity: "medium" }],
  postconditions: [{ clause_id: "post_cart_row", surface: "db", kind: "db_delta", params: { table: "cart_items", inserted: 1 }, description: "", severity: "high" }],
  invariants: [{ clause_id: "inv_no_unapproved_endpoint", surface: "network", kind: "no_unapproved_endpoint", params: {}, description: "", severity: "high" }],
};
const before = db({ products: [{ id: 1, stock: 5 }], cart_items: [] });
const after = db({ products: [{ id: 1, stock: 4 }], cart_items: [{ id: 1 }] });

describe("evaluateRun", () => {
  it("passes when every clause holds", async () => {
    const r = await evaluateRun(contract, ctx({ args: { product_id: 1 }, dbBefore: before, dbAfter: after, events: [req("POST", "/api/cart")] }), { mode: "single", handlerError: null });
    expect(r.status).toBe("pass");
    expect(r.clause_results.map((c) => c.clause_id)).toEqual(["pre_product", "post_cart_row", "inv_no_unapproved_endpoint"]);
  });

  it("skips postconditions when a precondition fails, but still checks invariants", async () => {
    const r = await evaluateRun(contract, ctx({ args: { product_id: 99 }, dbBefore: before, dbAfter: before }), { mode: "single", handlerError: "404" });
    expect(r.status).toBe("fail");
    expect(r.clause_results.map((c) => c.clause_id)).toEqual(["pre_product", "inv_no_unapproved_endpoint"]);
    expect(r.violations).toEqual([{ clause_id: "pre_product", severity: "medium", category: "precondition", signature: "shop.add_to_cart|pre_product|db_row_exists|products where id" }]);
  });

  it("reports error when the handler threw and no evaluated clause failed", async () => {
    const r = await evaluateRun(contract, ctx({ args: { product_id: 1 }, dbBefore: before, dbAfter: before }), { mode: "single", handlerError: "boom" });
    expect(r.status).toBe("error");
    expect(r.violations).toEqual([]);
  });

  it("evaluates only preconditions and invariants in concurrent mode", async () => {
    const r = await evaluateRun(contract, ctx({ args: { product_id: 1 }, dbBefore: before, dbAfter: after }), { mode: "concurrent", handlerError: null });
    expect(r.clause_results.map((c) => c.clause_id)).toEqual(["pre_product", "inv_no_unapproved_endpoint"]);
  });

  it("categorises invariant breaches", async () => {
    const events = [req("POST", "/api/cart"), req("POST", "/api/analytics", { approved: false })];
    const r = await evaluateRun(contract, ctx({ args: { product_id: 1 }, dbBefore: before, dbAfter: after, events }), { mode: "single", handlerError: null });
    expect(r.violations[0]).toMatchObject({ category: "unapproved_endpoint", signature: "shop.add_to_cart|inv_no_unapproved_endpoint|no_unapproved_endpoint|POST /api/analytics" });
  });

  it("is unverifiable when a clause cannot be evaluated", async () => {
    const domContract: ToolContract = { ...contract, preconditions: [{ clause_id: "pre_logged_in", surface: "aria", kind: "auth_state", params: { logged_in: true }, description: "", severity: "high" }] };
    const r = await evaluateRun(domContract, ctx({ args: { product_id: 1 }, dbBefore: before, dbAfter: after, events: [req("POST", "/api/cart")] }), { mode: "single", handlerError: null });
    expect(r.status).toBe("unverifiable");
  });
});

describe("buildEffectDiff", () => {
  it("summarises db, network, dom, storage and audit effects", () => {
    const events = [
      req("POST", "/api/cart", { request_id: "q1" }),
      ev("network_response", { request_id: "q1", status: 201 }),
      ev("dom_mutation", { added: 2, removed: 0, attr_changed: 1, text_changed: 0, target_selector: "[data-testid=status]" }),
      ev("storage", { area: "local", op: "set", key: "__trk" }, "post"),
    ];
    const audit = [{ id: 1, event: "cart.add", actor: "alice", entity: "cart_items", entity_id: "1", ts: "" }];
    const diff = buildEffectDiff({ events, dbBefore: before, dbAfter: after, newAudit: audit, urlBefore: "http://x/a", urlAfter: "http://x/a" });
    expect(diff).toEqual({
      db: { products: { inserted: 0, updated: 1, deleted: 0 }, cart_items: { inserted: 1, updated: 0, deleted: 0 } },
      network: [{ method: "POST", url: "http://127.0.0.1:5101/api/cart", status: 201, approved: true, third_party: false, phase: "during" }],
      dom: { mutations: 3, added_selectors: ["[data-testid=status]"], removed_selectors: [], url_before: "http://x/a", url_after: "http://x/a" },
      storage: [{ area: "local", op: "set", key: "__trk" }],
      audit: [{ event: "cart.add", count: 1 }],
    });
  });
});

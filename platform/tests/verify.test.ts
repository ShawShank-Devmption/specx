import { describe, expect, it } from "vitest";
import type { ToolContract, Verdict, Violation } from "../src/contracts/types.js";
import { decideStatus, foldQuarantine, producerFor } from "../src/verify/decide.js";

let n = 0;
function verdict(over: Partial<Verdict> = {}): Verdict {
  return {
    run_id: `r${++n}`,
    session_id: "s",
    app: "shop",
    tool_id: "shop.t",
    args: {},
    mode: "single",
    started_at: "2026-10-15T00:00:00Z",
    duration_ms: 1,
    status: "pass",
    clause_results: [{ clause_id: "post_x", kind: "db_delta", surface: "db", passed: true }],
    effect_diff: { db: { t: { inserted: 1, updated: 0, deleted: 0 } }, network: [], dom: { mutations: 0, added_selectors: [], removed_selectors: [] }, storage: [], audit: [] },
    violations: [],
    anomaly: null,
    source: "f1",
    ...over,
  };
}
const v = (clause_id: string, severity: Violation["severity"], category: Violation["category"]): Violation => ({ clause_id, severity, category, signature: `shop.t|${clause_id}` });

describe("decideStatus", () => {
  it("verifies a tool whose runs all pass and whose replay matches", () => {
    const run = verdict();
    expect(decideStatus([verdict(), run], { original: run, replay: verdict({ mode: "replay" }) })).toEqual({ status: "verified", reasons: [] });
  });

  it("quarantines on any failed postcondition or invariant, of any severity", () => {
    const failed = verdict({ status: "fail", violations: [v("post_audit", "medium", "postcondition")] });
    expect(decideStatus([verdict(), failed], null)).toMatchObject({ status: "quarantined", reasons: [{ kind: "violation", signature: "shop.t|post_audit", run_id: failed.run_id }] });
  });

  it("quarantines when the handler errors on valid arguments", () => {
    expect(decideStatus([verdict({ status: "error" })], null).reasons).toMatchObject([{ kind: "handler_error" }]);
  });

  it("quarantines a non-deterministic tool (replay differs)", () => {
    const run = verdict();
    const replay = verdict({ mode: "replay", effect_diff: { ...run.effect_diff, db: { t: { inserted: 2, updated: 0, deleted: 0 } } } });
    expect(decideStatus([run], { original: run, replay }).reasons).toMatchObject([{ kind: "nondeterministic" }]);
  });

  it("ignores handler errors and precondition-only failures in concurrent runs, but not races", () => {
    const ok = decideStatus([verdict(), verdict({ mode: "concurrent", status: "error" })], null);
    expect(ok.status).toBe("verified");
    const race = verdict({ mode: "concurrent", status: "fail", violations: [v("inv_at_most_once", "high", "race")] });
    expect(decideStatus([verdict(), race], null).reasons).toMatchObject([{ kind: "violation", category: "race" }]);
  });

  it("treats a precondition failure on generated example args as unverifiable", () => {
    const pre = verdict({ status: "fail", violations: [v("pre_exists_cart_items", "high", "precondition")] });
    expect(decideStatus([pre], null).reasons).toMatchObject([{ kind: "unverifiable" }]);
  });
});

describe("producerFor", () => {
  const contract = (tool_id: string, table: string, inserted: unknown): ToolContract => ({
    tool_id,
    preconditions: [],
    postconditions: [{ clause_id: `post_db_${table}`, surface: "db", kind: "db_delta", params: { table, inserted }, description: "", severity: "high" }],
    invariants: [],
  });
  it("finds another tool that inserts into the needed table", () => {
    const cs = [contract("shop.remove_from_cart", "cart_items", 0), contract("shop.add_to_cart", "cart_items", 1), contract("shop.place_order", "orders", 1)];
    expect(producerFor("cart_items", cs, "shop.remove_from_cart")).toBe("shop.add_to_cart");
    expect(producerFor("notes", cs, "x")).toBeNull();
  });
});

describe("foldQuarantine", () => {
  it("quarantines verified tools with high-severity, non-precondition violations from later stages", () => {
    const tools = [
      { tool_id: "shop.a", status: "verified" },
      { tool_id: "shop.b", status: "verified" },
      { tool_id: "shop.c", status: "quarantined" },
    ];
    const verdicts = [
      verdict({ tool_id: "shop.a", source: "s1", violations: [v("inv_stock_nonnegative", "high", "side_effect")] }),
      verdict({ tool_id: "shop.b", source: "s1", violations: [v("pre_x", "high", "precondition"), v("inv_storage_untouched", "medium", "storage")] }),
    ];
    const r = foldQuarantine(tools, verdicts);
    expect(r.tools.map((t) => t.status)).toEqual(["quarantined", "verified", "quarantined"]);
    expect(r.changed).toEqual([{ tool_id: "shop.a", signatures: ["shop.t|inv_stock_nonnegative"] }]);
  });
});

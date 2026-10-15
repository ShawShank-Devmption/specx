import os from "node:os";
import path from "node:path";
import fs from "node:fs";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import type { Verdict } from "../src/contracts/types.js";
import { validate } from "../src/contracts/validate.js";
import { fixtureToolset, integration, startHarness, type Harness } from "./helpers/sandbox.js";

describe.runIf(integration)("sandbox server (integration)", () => {
  let h: Harness;
  const add = { tool_id: "shop.add_to_cart", args: { product_id: 1, qty: 1 }, source: "fixture", post_observe_ms: 300 };

  beforeAll(async () => {
    process.env.SPECX_RESULTS_DIR = fs.mkdtempSync(path.join(os.tmpdir(), "specx-it-"));
    h = await startHarness(["shop"]);
  });
  afterAll(() => h?.close());

  async function session(): Promise<string> {
    const s = await h.call<{ session_id: string }>("POST", "/sessions", { app: "shop" });
    expect(s.status).toBe(200);
    expect((await h.call("PUT", `/sessions/${s.body.session_id}/tools`, fixtureToolset())).status).toBe(200);
    return s.body.session_id;
  }

  it("reports health", async () => {
    expect((await h.call("GET", "/health")).body).toMatchObject({ ok: true, apps: ["shop"] });
  });

  it("invokes a tool and returns a schema-valid passing verdict", async () => {
    const id = await session();
    const v = (await h.call<Verdict>("POST", `/sessions/${id}/invoke`, add)).body;
    validate("verdict", v);
    expect(v.status).toBe("pass");
    expect(v.effect_diff.db.cart_items?.inserted).toBe(1);
  });

  it("replays a run deterministically (replay_identical)", async () => {
    const id = await session();
    await h.call("POST", `/sessions/${id}/invoke`, { ...add, tool_id: "shop.add_to_cart", args: { product_id: 2, qty: 1 } });
    const v = (await h.call<Verdict>("POST", `/sessions/${id}/invoke`, add)).body;
    const r = (await h.call<Verdict>("POST", `/sessions/${id}/replay`, { run_id: v.run_id })).body;
    expect(r.mode).toBe("replay");
    expect(r.sequence_prefix).toEqual(v.sequence_prefix);
    expect(r.clause_results.map((c) => [c.clause_id, c.passed])).toEqual(v.clause_results.map((c) => [c.clause_id, c.passed]));
    expect(r.effect_diff.db).toEqual(v.effect_diff.db);
  });

  it("attributes a delayed leak to the finished run in the post phase (post_phase_attribution)", async () => {
    const id = await session();
    await h.call("POST", `/sessions/${id}/inject_leak`, { kind: "delayed_post", delay_ms: 200 });
    const v = (await h.call<Verdict>("POST", `/sessions/${id}/invoke`, { ...add, post_observe_ms: 800 })).body;
    expect(v.status).toBe("fail");
    expect(v.violations.map((x) => x.category)).toContain("unapproved_endpoint");
    const events = (await h.call<{ events: { run_id: string; phase: string; kind: string; data: { path?: string } }[] }>("GET", `/sessions/${id}/events?since_seq=0`)).body.events;
    const leak = events.find((e) => e.kind === "network_request" && e.data.path === "/api/analytics");
    expect(leak).toMatchObject({ run_id: v.run_id, phase: "post" });
  });

  it("blocks and records third-party requests", async () => {
    const id = await session();
    await h.call("POST", `/sessions/${id}/inject_leak`, { kind: "third_party_fetch", delay_ms: 100 });
    const v = (await h.call<Verdict>("POST", `/sessions/${id}/invoke`, { ...add, post_observe_ms: 700 })).body;
    expect(v.violations.map((x) => x.category)).toContain("third_party");
    const tp = v.effect_diff.network.find((n) => n.third_party);
    expect(tp?.status).toBeUndefined();
  });

  it("catches silent storage writes", async () => {
    const id = await session();
    await h.call("POST", `/sessions/${id}/inject_leak`, { kind: "storage_write", delay_ms: 100 });
    const v = (await h.call<Verdict>("POST", `/sessions/${id}/invoke`, { ...add, post_observe_ms: 600 })).body;
    expect(v.violations.find((x) => x.category === "storage")?.signature).toBe("shop.add_to_cart|inv_storage_untouched|storage_untouched|local:set:__trk");
  });

  it("isolates sessions from each other", async () => {
    const a = await session();
    const b = await session();
    await h.call("POST", `/sessions/${a}/invoke`, add);
    const sb = (await h.call<{ db: Record<string, { count: number }> }>("GET", `/sessions/${b}/state`)).body;
    expect(sb.db.cart_items?.count).toBe(0);
  });

  it("drives the raw DOM through refs from the ARIA observation", async () => {
    const id = await session();
    const nav = (await h.call<{ aria: string }>("POST", `/sessions/${id}/dom_action`, { action: "navigate", url: "/products/1" })).body;
    const ref = /button "Add to cart" \[ref=(e\d+)\]/.exec(nav.aria)?.[1];
    expect(ref).toBeDefined();
    expect((await h.call("POST", `/sessions/${id}/dom_action`, { action: "click", ref })).status).toBe(200);
    const st = (await h.call<{ db: Record<string, { count: number }> }>("GET", `/sessions/${id}/state`)).body;
    expect(st.db.cart_items?.count).toBe(1);
  });

  it("refuses navigation to another origin", async () => {
    const id = await session();
    const r = await h.call<{ error: { code: string } }>("POST", `/sessions/${id}/dom_action`, { action: "navigate", url: "https://example.com/" });
    expect(r.status).toBe(400);
    expect(r.body.error.code).toBe("scope_exceeded");
  });

  it("derives example args from preconditions", async () => {
    const id = await session();
    const r = (await h.call<{ args: Record<string, unknown>; unsatisfied: string[] }>("GET", `/sessions/${id}/example_args?tool_id=shop.add_to_cart`)).body;
    expect(r).toEqual({ args: { product_id: 5, qty: 1 }, unsatisfied: [] });
  });

  it("detects the checkout race under concurrent invocation (concurrent_race_detected)", async () => {
    const id = await session();
    await h.call("POST", `/sessions/${id}/invoke`, add);
    const g = (await h.call<{ concurrency_group: string; verdicts: Verdict[] }>("POST", `/sessions/${id}/invoke_concurrent`, {
      calls: [{ tool_id: "shop.place_order", args: { confirm: true } }, { tool_id: "shop.place_order", args: { confirm: true } }],
      source: "fixture",
      post_observe_ms: 300,
    })).body;
    expect(g.verdicts).toHaveLength(2);
    for (const v of g.verdicts) {
      validate("verdict", v);
      expect(v.mode).toBe("concurrent");
      expect(v.concurrency_group).toBe(g.concurrency_group);
      expect(v.violations.find((x) => x.category === "race")?.signature).toBe("shop.place_order|inv_at_most_once|at_most_once|orders x2");
      expect(v.effect_diff.db.orders?.inserted).toBe(2);
    }
  });

  it("rejects unknown tools and malformed bodies", async () => {
    const id = await session();
    expect((await h.call("POST", `/sessions/${id}/invoke`, { tool_id: "shop.nope", args: {}, source: "fixture" })).status).toBe(404);
    expect((await h.call("POST", `/sessions/${id}/invoke`, { args: {} })).status).toBe(400);
    expect((await h.call("POST", `/sessions/nope/reset`, {})).status).toBe(404);
  });

  it("keeps invoke latency under 400 ms p50 excluding the observe window", async () => {
    const id = await session();
    const durations: number[] = [];
    for (let i = 0; i < 30; i++) durations.push((await h.call<Verdict>("POST", `/sessions/${id}/invoke`, { ...add, post_observe_ms: 0 })).body.duration_ms);
    durations.sort((a, b) => a - b);
    expect(durations[15]).toBeLessThan(400);
  });

  it("runs 8 sessions in parallel without interference", async () => {
    const ids = await Promise.all(Array.from({ length: 8 }, () => session()));
    const verdicts = await Promise.all(ids.map((id) => h.call<Verdict>("POST", `/sessions/${id}/invoke`, add)));
    expect(verdicts.map((v) => [v.body.status, v.body.effect_diff.db.cart_items?.inserted])).toEqual(Array(8).fill(["pass", 1]));
  });

  it("replays a run whose prefix contains a concurrent group", async () => {
    const id = await session();
    await h.call("POST", `/sessions/${id}/invoke_concurrent`, { calls: [{ tool_id: "shop.add_to_cart", args: { product_id: 1, qty: 1 } }, { tool_id: "shop.add_to_cart", args: { product_id: 2, qty: 1 } }], source: "fixture", post_observe_ms: 200 });
    const v = (await h.call<Verdict>("POST", `/sessions/${id}/invoke`, { tool_id: "shop.place_order", args: { confirm: true }, source: "fixture", post_observe_ms: 200 })).body;
    expect(v.status).toBe("pass");
    const r = (await h.call<Verdict>("POST", `/sessions/${id}/replay`, { run_id: v.run_id })).body;
    expect(r.status).toBe("pass");
    expect(r.effect_diff.db).toEqual(v.effect_diff.db);
  });

  it("replays a run whose pre-state came from apply", async () => {
    const id = await session();
    await h.call("POST", `/sessions/${id}/apply`, { state: { cart: [{ product_id: 3, qty: 1 }] } });
    const v = (await h.call<Verdict>("POST", `/sessions/${id}/invoke`, { tool_id: "shop.place_order", args: { confirm: true }, source: "fixture", post_observe_ms: 200 })).body;
    expect(v.status).toBe("pass");
    const r = (await h.call<Verdict>("POST", `/sessions/${id}/replay`, { run_id: v.run_id })).body;
    expect(r.status).toBe("pass");
  });

  it("labels everything after tool_end as post phase", async () => {
    const id = await session();
    const v = (await h.call<Verdict>("POST", `/sessions/${id}/invoke`, add)).body;
    const events = (await h.call<{ events: { run_id: string; phase: string; kind: string }[] }>("GET", `/sessions/${id}/events?since_seq=0`)).body.events.filter((e) => e.run_id === v.run_id);
    const end = events.findIndex((e) => e.kind === "tool_end");
    expect(events.slice(end + 1).map((e) => e.phase)).toEqual(events.slice(end + 1).map(() => "post"));
    expect(events.slice(end + 1).some((e) => e.kind === "audit")).toBe(true);
  });

  it("records the network events of raw DOM actions", async () => {
    const id = await session();
    const nav = (await h.call<{ aria: string }>("POST", `/sessions/${id}/dom_action`, { action: "navigate", url: "/products/1" })).body;
    const ref = /button "Add to cart" \[ref=(e\d+)\]/.exec(nav.aria)?.[1];
    const click = (await h.call<{ run_id: string }>("POST", `/sessions/${id}/dom_action`, { action: "click", ref })).body;
    const events = (await h.call<{ events: { run_id: string; kind: string; data: { method?: string; path?: string } }[] }>("GET", `/sessions/${id}/events?since_seq=0`)).body.events;
    expect(events.some((e) => e.run_id === click.run_id && e.kind === "network_request" && e.data.method === "POST" && e.data.path === "/api/cart")).toBe(true);
  });

  it("answers malformed JSON and unknown routes with the JSON error envelope", async () => {
    const bad = await fetch(`${h.url}/sessions`, { method: "POST", headers: { "content-type": "application/json" }, body: "{nope" });
    expect(bad.status).toBe(400);
    expect(((await bad.json()) as { error: { code: string } }).error.code).toBe("bad_request");
    const missing = await h.call<{ error: { code: string } }>("GET", "/nope");
    expect(missing.status).toBe(404);
    expect(missing.body.error.code).toBe("not_found");
  });
});

import { describe, expect, it } from "vitest";
import { EventRecorder } from "../src/sandbox/recorder.js";

function clock(start = 0) {
  let t = start;
  return { now: () => t, advance: (ms: number) => (t += ms) };
}

describe("EventRecorder (post_phase_attribution)", () => {
  it("drops events while no run is active (after reset)", () => {
    const r = new EventRecorder("s1");
    expect(r.record("navigation", { url: "/x" })).toBeNull();
    expect(r.since(0)).toEqual([]);
  });

  it("keeps attributing events to the finished run, in the post phase, until the next run starts", () => {
    const c = clock();
    const r = new EventRecorder("s1", { now: c.now });
    r.begin(["r1"]);
    r.setPhase("during");
    r.record("tool_start", { tool_id: "t" });
    c.advance(50);
    r.record("tool_end", { status: "ok" });
    r.setPhase("post");
    c.advance(700);
    const leak = r.record("network_request", { method: "POST", path: "/api/analytics" });
    expect(leak).toMatchObject({ run_id: "r1", phase: "post", t_ms: 750, session_id: "s1" });
    r.begin(["r2"]);
    expect(r.record("console", { text: "hi" })).toMatchObject({ run_id: "r2", phase: "pre", t_ms: 0 });
    expect(r.eventsFor("r1").map((e) => e.kind)).toEqual(["tool_start", "tool_end", "network_request"]);
  });

  it("numbers events monotonically per session and serves them by seq", () => {
    const r = new EventRecorder("s1");
    r.begin(["r1"]);
    r.record("console", { n: 1 });
    r.record("console", { n: 2 });
    expect(r.since(1).map((e) => e.seq)).toEqual([1]);
  });

  it("attributes events to a named run of a concurrent group", () => {
    const r = new EventRecorder("s1");
    r.begin(["a", "b"]);
    expect(r.record("console", {}, "b")?.run_id).toBe("b");
    expect(r.record("console", {})?.run_id).toBe("a");
  });

  it("forwards every recorded event to the sink", () => {
    const seen: string[] = [];
    const r = new EventRecorder("s1", { sink: (e) => seen.push(e.kind) });
    r.begin(["r1"]);
    r.record("console", {});
    r.clear();
    r.record("console", {});
    expect(seen).toEqual(["console"]);
  });
});

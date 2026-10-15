import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { validate } from "../src/contracts/validate.js";
import { REPO_ROOT } from "../src/paths.js";

const fixture = (rel: string) => path.join(REPO_ROOT, "fixtures", rel);
const jsonl = (rel: string) => fs.readFileSync(fixture(rel), "utf8").trim().split("\n").map((l) => JSON.parse(l) as unknown);

describe("validate", () => {
  it("accepts every fixture", () => {
    validate("app_manifest", JSON.parse(fs.readFileSync(fixture("apps/shop.app.json"), "utf8")));
    for (const t of JSON.parse(fs.readFileSync(fixture("tools/shop.tools.json"), "utf8")) as unknown[]) validate("tool_definition", t);
    for (const v of jsonl("verdicts/sample.verdicts.jsonl")) validate("verdict", v);
    for (const e of jsonl("events/leaked_trace.jsonl")) validate("event_record", e);
    validate("workflow_graph", JSON.parse(fs.readFileSync(fixture("graphs/shop.graph.json"), "utf8")));
  });

  it("throws with the JSON pointer of the first error", () => {
    const [v] = jsonl("verdicts/sample.verdicts.jsonl") as Record<string, unknown>[];
    expect(() => validate("verdict", { ...v, status: "maybe" })).toThrow(/^verdict\/status: /);
  });
});

/**
 * `specx verify --app <app> [--runs 3] [--observe 1000]` — F1 verification; writes verdicts to
 * results/verdicts/f1.jsonl and sets each tool's status in results/tools/<app>.tools.json.
 * `specx quarantine --app <app> [--from s1,s1_random,s1_coverage,s6_inject]` — folds later evidence in.
 */
import fs from "node:fs";
import { chromium } from "playwright";
import type { ToolContract, ToolDefinition, Verdict } from "../contracts/types.js";
import { contractsPath, repoRelative, toolsPath, verdictsPath } from "../paths.js";
import { Session } from "../sandbox/session.js";
import { foldQuarantine, type Reason } from "../verify/decide.js";
import { verifyTools } from "../verify/run.js";
import { loadManifest, readJson, readJsonl, table, writeRecords } from "./common.js";

const describeReason = (r: Reason) => {
  switch (r.kind) {
    case "violation":
      return `${r.category ?? "violation"}: ${r.signature.split("|").slice(1).join(" | ")}${r.mode === "concurrent" ? " (concurrent)" : ""}`;
    case "handler_error":
      return "handler error on valid arguments";
    default:
      return `${r.kind}: ${r.detail}`;
  }
};

export async function verifyCommand(app: string, runs: number, postObserveMs: number): Promise<void> {
  const manifest = loadManifest(app);
  const tools = readJson<ToolDefinition[]>(toolsPath(app));
  const contracts = readJson<ToolContract[]>(contractsPath(app));
  const browser = await chromium.launch();
  try {
    const session = await Session.create(browser, manifest);
    const results = await verifyTools(session, tools, contracts, { runs, postObserveMs, onProgress: (m) => process.stderr.write(`  ${m}\n`) });
    await session.close();
    const status = new Map(results.map((r) => [r.tool_id, r.decision.status]));
    writeRecords(
      toolsPath(app),
      "tool_definition",
      tools.map((t) => ({ ...t, status: status.get(t.tool_id) ?? t.status })),
    );
    const replays = results.flatMap((r) => r.verdicts.filter((v) => v.mode === "replay"));
    const deterministic = results.filter((r) => !r.decision.reasons.some((x) => x.kind === "nondeterministic")).length;
    console.log(`\n${app}: ${results.filter((r) => r.decision.status === "verified").length} verified, ${results.filter((r) => r.decision.status === "quarantined").length} quarantined; replay-deterministic ${deterministic}/${replays.length}\n`);
    console.log(
      table(
        ["tool", "status", "runs", "reasons"],
        results.map((r) => [r.tool_id, r.decision.status, r.verdicts.length, [...new Set(r.decision.reasons.map(describeReason))].join("; ") || "-"]),
      ),
    );
    console.log(`\nwrote ${repoRelative(toolsPath(app))}; verdicts appended to ${repoRelative(verdictsPath("f1"))}`);
  } finally {
    await browser.close();
  }
}

export function quarantineCommand(app: string, sources: string[]): void {
  const tools = readJson<ToolDefinition[]>(toolsPath(app));
  const verdicts = sources.flatMap((s) => readJsonl<Verdict>(verdictsPath(s))).filter((v) => v.app === app);
  const missing = sources.filter((s) => !fs.existsSync(verdictsPath(s)));
  const { tools: updated, changed } = foldQuarantine(tools, verdicts);
  writeRecords(toolsPath(app), "tool_definition", updated);
  console.log(`${app}: read ${verdicts.length} verdicts from ${sources.length - missing.length}/${sources.length} sources${missing.length ? ` (missing: ${missing.join(", ")})` : ""}`);
  console.log(changed.length ? table(["newly quarantined", "signatures"], changed.map((c) => [c.tool_id, c.signatures.join("; ")])) : "no verified tool changed status");
}

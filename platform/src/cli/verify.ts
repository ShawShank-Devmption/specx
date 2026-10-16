/**
 * `specx verify --app <app> [--runs 3] [--observe 1000]` — F1 verification; writes verdicts to
 * results/verdicts/f1.jsonl and sets each tool's status in results/tools/<app>.tools.json.
 * `specx quarantine --app <app> [--from s1,s1_random,s1_coverage]` — folds fuzzing violations and S6's
 * anomaly flags on the tool's own F1 runs into tool status. Never pass s6_inject: those leaks are injected.
 */
import fs from "node:fs";
import { chromium } from "playwright";
import type { ToolContract, ToolDefinition, Verdict } from "../contracts/types.js";
import { contractsPath, repoRelative, toolsPath, verdictsPath, webmcpContractsPath, webmcpToolsPath } from "../paths.js";
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

export async function verifyCommand(app: string, runs: number, postObserveMs: number, set: "api" | "webmcp" = "api"): Promise<void> {
  const manifest = loadManifest(app);
  const file = set === "webmcp" ? webmcpToolsPath(app) : toolsPath(app);
  const tools = readJson<ToolDefinition[]>(file);
  const contracts = readJson<ToolContract[]>(set === "webmcp" ? webmcpContractsPath(app) : contractsPath(app));
  const browser = await chromium.launch();
  try {
    const session = await Session.create(browser, manifest);
    const results = await verifyTools(session, tools, contracts, { runs, postObserveMs, onProgress: (m) => process.stderr.write(`  ${m}\n`) });
    await session.close();
    const status = new Map(results.map((r) => [r.tool_id, r.decision.status]));
    writeRecords(
      file,
      "tool_definition",
      tools.map((t) => ({ ...t, status: status.get(t.tool_id) ?? t.status })),
    );
    const replays = results.flatMap((r) => r.verdicts.filter((v) => v.mode === "replay"));
    const deterministic = results.filter((r) => !r.decision.reasons.some((x) => x.kind === "nondeterministic")).length;
    console.log(`\n${app}${set === "webmcp" ? " (WebMCP set)" : ""}: ${results.filter((r) => r.decision.status === "verified").length} verified, ${results.filter((r) => r.decision.status === "quarantined").length} quarantined; replay-deterministic ${deterministic}/${replays.length}\n`);
    console.log(
      table(
        ["tool", "status", "runs", "reasons"],
        results.map((r) => [r.tool_id, r.decision.status, r.verdicts.length, [...new Set(r.decision.reasons.map(describeReason))].join("; ") || "-"]),
      ),
    );
    console.log(`\nwrote ${repoRelative(file)}; verdicts appended to ${repoRelative(verdictsPath("f1"))}`);
  } finally {
    await browser.close();
  }
}

export function quarantineCommand(app: string, sources: string[]): void {
  const tools = readJson<ToolDefinition[]>(toolsPath(app));
  if (sources.includes("s6_inject")) throw new Error("s6_inject violations are caused by injected leaks, not by the tools; S6 counts through anomaly flags on f1 runs instead");
  const verdicts = sources.flatMap((s) => readJsonl<Verdict>(verdictsPath(s))).filter((v) => v.app === app);
  const f1 = readJsonl<Verdict>(verdictsPath("f1")).filter((v) => v.app === app);
  const missing = sources.filter((s) => !fs.existsSync(verdictsPath(s)));
  const { tools: updated, changed } = foldQuarantine(tools, { violations: verdicts, anomaly: f1 });
  writeRecords(toolsPath(app), "tool_definition", updated);
  const scored = f1.filter((v) => v.anomaly).length;
  console.log(`${app}: read ${verdicts.length} fuzzing verdicts from ${sources.length - missing.length}/${sources.length} sources${missing.length ? ` (missing: ${missing.join(", ")})` : ""}; ${scored}/${f1.length} f1 verdicts carry S6 scores`);
  console.log(changed.length ? table(["newly quarantined", "signatures"], changed.map((c) => [c.tool_id, c.signatures.join("; ")])) : "no verified tool changed status");
}

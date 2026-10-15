/**
 * Verification decisions, kept pure so they are unit-testable: when a tool is verified or quarantined
 * (with machine-readable reasons), which tool can produce the state another tool needs, and how later
 * evidence (S1 fuzzing, S6 leak runs) folds into tool status.
 */
import type { Severity, ToolContract, Verdict, ViolationCategory } from "../contracts/types.js";

export type Reason =
  | { kind: "violation"; run_id: string; clause_id: string; signature: string; severity: Severity; category?: ViolationCategory; mode: Verdict["mode"] }
  | { kind: "handler_error"; run_id: string }
  | { kind: "unverifiable"; run_id: string; detail: string }
  | { kind: "nondeterministic"; run_id: string; detail: string };

export interface Decision {
  status: "verified" | "quarantined";
  reasons: Reason[];
}

const passedVector = (v: Verdict) => JSON.stringify(v.clause_results.map((c) => [c.clause_id, c.passed]));

/**
 * Verified iff every run on valid arguments passes and the replay reproduces the original run.
 * Concurrent runs only count for invariant breaches (races, leaks); an idempotent second call failing
 * with 404 is not a defect.
 */
export function decideStatus(verdicts: Verdict[], replay: { original: Verdict; replay: Verdict } | null): Decision {
  const reasons: Reason[] = [];
  for (const v of verdicts) {
    for (const x of v.violations) {
      if (x.category === "precondition") {
        if (v.mode !== "concurrent") reasons.push({ kind: "unverifiable", run_id: v.run_id, detail: `precondition ${x.clause_id} failed on generated example arguments` });
        continue;
      }
      reasons.push({ kind: "violation", run_id: v.run_id, clause_id: x.clause_id, signature: x.signature, severity: x.severity, ...(x.category ? { category: x.category } : {}), mode: v.mode });
    }
    if (v.mode === "concurrent") continue;
    if (v.status === "error") reasons.push({ kind: "handler_error", run_id: v.run_id });
    if (v.status === "unverifiable") reasons.push({ kind: "unverifiable", run_id: v.run_id, detail: "a clause could not be evaluated" });
  }
  if (replay) {
    const same = passedVector(replay.original) === passedVector(replay.replay) && JSON.stringify(replay.original.effect_diff.db) === JSON.stringify(replay.replay.effect_diff.db);
    if (!same) reasons.push({ kind: "nondeterministic", run_id: replay.replay.run_id, detail: `replay of ${replay.original.run_id} produced different clause results or db effects` });
  }
  return { status: reasons.length ? "quarantined" : "verified", reasons };
}

const insertsAtLeastOne = (v: unknown) => (typeof v === "number" ? v >= 1 : v !== null && typeof v === "object" && ((v as { min?: number }).min ?? 0) >= 1);

/** A tool (other than `exclude`) whose contract inserts rows into `table`. */
export function producerFor(table: string, contracts: ToolContract[], exclude: string): string | null {
  const c = contracts.find((k) => k.tool_id !== exclude && k.postconditions.some((p) => p.kind === "db_delta" && p.params.table === table && insertsAtLeastOne(p.params.inserted)));
  return c?.tool_id ?? null;
}

/** Quarantine verified tools that later stages showed to have high-severity, non-precondition violations. */
export function foldQuarantine<T extends { tool_id: string; status?: string }>(tools: T[], verdicts: Verdict[]): { tools: T[]; changed: { tool_id: string; signatures: string[] }[] } {
  const changed: { tool_id: string; signatures: string[] }[] = [];
  const out = tools.map((t) => {
    if (t.status !== "verified") return t;
    const sigs = [...new Set(verdicts.filter((v) => v.tool_id === t.tool_id).flatMap((v) => v.violations.filter((x) => x.severity === "high" && x.category !== "precondition").map((x) => x.signature)))];
    if (!sigs.length) return t;
    changed.push({ tool_id: t.tool_id, signatures: sigs });
    return { ...t, status: "quarantined" };
  });
  return { tools: out, changed };
}

/**
 * F1 verification of one app's tool set inside a sandbox session: for each tool, N single runs on valid
 * example arguments (running a producer tool first when a precondition needs state, e.g. a non-empty cart),
 * one replay for determinism, and one doubled concurrent call for state-changing tools.
 */
import type { ToolContract, ToolDefinition, Verdict } from "../contracts/types.js";
import type { Session } from "../sandbox/session.js";
import { decideStatus, producerFor, type Decision, type Reason } from "./decide.js";

export interface ToolVerification {
  tool_id: string;
  decision: Decision;
  verdicts: Verdict[];
}

export interface VerifyOptions {
  runs: number;
  postObserveMs: number;
  onProgress?: (msg: string) => void;
}

async function argsFor(session: Session, tool: ToolDefinition, contracts: ToolContract[], postObserveMs: number): Promise<Record<string, unknown> | null> {
  const contract = contracts.find((c) => c.tool_id === tool.tool_id);
  let ea = await session.exampleArgs(tool.tool_id);
  for (let attempt = 0; attempt < 3 && ea.unsatisfied.length > 0; attempt++) {
    for (const clauseId of ea.unsatisfied) {
      const table = String(contract?.preconditions.find((p) => p.clause_id === clauseId)?.params.table ?? "");
      const producer = producerFor(table, contracts, tool.tool_id);
      if (!producer) return null;
      await session.invoke(producer, (await session.exampleArgs(producer)).args, { source: "f1", postObserveMs });
    }
    ea = await session.exampleArgs(tool.tool_id);
  }
  return ea.unsatisfied.length ? null : ea.args;
}

export async function verifyTools(session: Session, tools: ToolDefinition[], contracts: ToolContract[], opts: VerifyOptions): Promise<ToolVerification[]> {
  session.loadTools(tools, contracts);
  const out: ToolVerification[] = [];
  for (const tool of tools) {
    const verdicts: Verdict[] = [];
    const setup: Reason[] = [];
    let last: Verdict | null = null;
    for (let i = 0; i < opts.runs; i++) {
      await session.reset(0);
      const args = await argsFor(session, tool, contracts, opts.postObserveMs);
      if (!args) {
        setup.push({ kind: "unverifiable", run_id: "none", detail: "no producer tool can create the state this tool's preconditions need" });
        break;
      }
      last = await session.invoke(tool.tool_id, args, { source: "f1", postObserveMs: opts.postObserveMs });
      verdicts.push(last);
    }
    const replay = last ? { original: last, replay: await session.replay(last.run_id) } : null;
    if (tool.risk_level !== "read" && last) {
      await session.reset(0);
      const args = await argsFor(session, tool, contracts, opts.postObserveMs);
      if (args) {
        const g = await session.invokeConcurrent(
          [
            { tool_id: tool.tool_id, args },
            { tool_id: tool.tool_id, args },
          ],
          { source: "f1", postObserveMs: opts.postObserveMs },
        );
        verdicts.push(...g.verdicts);
      }
    }
    const d = decideStatus(verdicts, replay);
    const decision: Decision = setup.length ? { status: "quarantined", reasons: [...setup, ...d.reasons] } : d;
    opts.onProgress?.(`${tool.tool_id}: ${decision.status}`);
    out.push({ tool_id: tool.tool_id, decision, verdicts: replay ? [...verdicts, replay.replay] : verdicts });
  }
  return out;
}

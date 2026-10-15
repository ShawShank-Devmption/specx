/**
 * `specx graph --app <app>` — builds results/graphs/<app>.graph.json from tools, contracts and every
 * verdict file. Edges S2 already added (evidence "gnn") are kept across rebuilds.
 */
import fs from "node:fs";
import path from "node:path";
import type { ToolContract, ToolDefinition, Verdict, WorkflowGraph } from "../contracts/types.js";
import { buildGraph } from "../graph/build.js";
import { contractsPath, graphPath, repoRelative, toolsPath, verdictsDir } from "../paths.js";
import { readJson, readJsonl, table, writeRecords } from "./common.js";

export function graphCommand(app: string): void {
  const tools = readJson<ToolDefinition[]>(toolsPath(app));
  const contracts = readJson<ToolContract[]>(contractsPath(app));
  const files = fs.existsSync(verdictsDir()) ? fs.readdirSync(verdictsDir()).filter((f) => f.endsWith(".jsonl")) : [];
  const verdicts = files.flatMap((f) => readJsonl<Verdict>(path.join(verdictsDir(), f))).filter((v) => v.app === app);
  const graph = buildGraph(app, tools, contracts, verdicts);
  if (fs.existsSync(graphPath(app))) {
    const gnn = readJson<WorkflowGraph>(graphPath(app)).edges.filter((e) => e.evidence === "gnn");
    graph.edges.push(...gnn.filter((e) => !graph.edges.some((x) => x.src === e.src && x.dst === e.dst && x.type === e.type && x.field === e.field)));
  }
  writeRecords(graphPath(app), "workflow_graph", graph);
  const count = (pred: (e: WorkflowGraph["edges"][number]) => boolean) => graph.edges.filter(pred).length;
  console.log(`${app}: ${graph.nodes.length} nodes, ${graph.edges.length} edges from ${verdicts.length} verdicts (${files.join(", ") || "none"})\n`);
  console.log(
    table(
      ["edge type", "trace", "contract", "rule", "gnn"],
      (["order", "state", "data"] as const).map((t) => [t, count((e) => e.type === t && e.evidence === "trace"), count((e) => e.type === t && e.evidence === "contract"), count((e) => e.type === t && e.evidence === "rule"), count((e) => e.type === t && e.evidence === "gnn")]),
    ),
  );
  console.log(`\n${graph.invariants.length} invariants; wrote ${repoRelative(graphPath(app))}`);
}

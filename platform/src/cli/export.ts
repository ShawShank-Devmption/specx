/**
 * `specx export --app <app>` — writes results/webmcp/<app>.webmcp.js (served by the seed app at /webmcp.js)
 * and results/webmcp/<app>.webmcp.json from the app's verified tools. Run after verify/quarantine.
 */
import fs from "node:fs";
import path from "node:path";
import type { ToolContract, ToolDefinition } from "../contracts/types.js";
import { exportWebMCP } from "../export/webmcp.js";
import { ensureParent, repoRelative, resultsDir, webmcpContractsPath, webmcpToolsPath } from "../paths.js";
import { readJson, table } from "./common.js";

export function exportCommand(app: string): void {
  const tools = readJson<ToolDefinition[]>(webmcpToolsPath(app));
  const contracts = readJson<ToolContract[]>(webmcpContractsPath(app));
  const { script, manifest } = exportWebMCP(app, tools, contracts);
  const js = ensureParent(path.join(resultsDir(), "webmcp", `${app}.webmcp.js`));
  const json = path.join(resultsDir(), "webmcp", `${app}.webmcp.json`);
  fs.writeFileSync(js, script);
  fs.writeFileSync(json, `${JSON.stringify(manifest, null, 2)}\n`);
  console.log(`${app}: exported ${manifest.tools.length} verified WebMCP tools; withheld ${manifest.quarantined.length} quarantined${manifest.excluded.length ? ` and ${manifest.excluded.length} unverified` : ""}\n`);
  console.log(table(["tool", "kind", "page", "asks user", "contract clauses"], manifest.tools.map((t) => [t.name, t.kind, t.page, t.confirm ? "yes" : "-", t.contract ? t.contract.preconditions + t.contract.postconditions + t.contract.invariants : 0])));
  if (manifest.quarantined.length) console.log(`\nquarantined (not exported): ${manifest.quarantined.join(", ")}`);
  console.log(`\nwrote ${repoRelative(js)} (served by the app at /webmcp.js) and ${repoRelative(json)}`);
}

/**
 * F3 pipeline for one app: code evidence → crawl (DOM/ARIA/network evidence) → candidates → tools,
 * then F1's contract deriver for each tool. Returns validated records; the CLI writes them to results/.
 */
import path from "node:path";
import type { Browser } from "playwright";
import { deriveContract } from "../contracts/derive.js";
import type { AppManifest, ToolContract, ToolDefinition } from "../contracts/types.js";
import { validate } from "../contracts/validate.js";
import { SEED_APPS_DIR } from "../paths.js";
import { Session } from "../sandbox/session.js";
import { buildCandidates, type Rejection } from "./candidates.js";
import { crawl } from "./dom.js";
import { emitTool, type Namer } from "./emit.js";
import { parseRoutes } from "./repo.js";

export interface GenerateResult {
  tools: ToolDefinition[];
  contracts: ToolContract[];
  rejected: Rejection[];
  pages: string[];
}

export async function generate(manifest: AppManifest, browser: Browser, opts: { namer: Namer }): Promise<GenerateResult> {
  const routes = parseRoutes(path.join(SEED_APPS_DIR, manifest.app, "server.js"));
  const session = await Session.create(browser, manifest);
  let found;
  try {
    found = await crawl(session);
  } finally {
    await session.close();
  }
  const { candidates, rejected } = buildCandidates(routes, found.triggers, found.samples, manifest);
  const tools: ToolDefinition[] = [];
  const contracts: ToolContract[] = [];
  for (const c of candidates) {
    let tool = await emitTool(c, manifest, opts.namer);
    for (let n = 2; tools.some((t) => t.tool_id === tool.tool_id); n++) tool = { ...tool, name: `${tool.name}_${n}`, tool_id: `${manifest.app}.${tool.name}_${n}` };
    tools.push(validate<ToolDefinition>("tool_definition", tool));
    contracts.push(validate<ToolContract>("contract", deriveContract(tool, c.route, manifest)));
  }
  return { tools, contracts, rejected, pages: found.pages };
}

/** `specx generate --app <app> [--namer template|llm]` — F3 generation + F1 contract derivation. */
import Anthropic from "@anthropic-ai/sdk";
import { chromium } from "playwright";
import { templateNamer, type Namer } from "../generator/emit.js";
import { generate } from "../generator/index.js";
import { llmNamer, type NamerClient } from "../generator/llm.js";
import { contractsPath, repoRelative, toolsPath, webmcpContractsPath, webmcpToolsPath } from "../paths.js";
import { loadManifest, table, writeRecords } from "./common.js";

export async function generateCommand(app: string, namerKind: string): Promise<void> {
  const manifest = loadManifest(app);
  let namer: Namer = templateNamer;
  if (namerKind === "llm") {
    if (!process.env.ANTHROPIC_API_KEY) throw new Error("--namer llm needs ANTHROPIC_API_KEY (see .env.example)");
    namer = llmNamer(new Anthropic() as unknown as NamerClient, process.env.SPECX_GEN_MODEL ?? "claude-opus-5-5");
  } else if (namerKind !== "template") throw new Error(`unknown namer "${namerKind}"`);

  const browser = await chromium.launch();
  try {
    const r = await generate(manifest, browser, { namer });
    writeRecords(toolsPath(app), "tool_definition", r.tools);
    writeRecords(contractsPath(app), "contract", r.contracts);
    writeRecords(webmcpToolsPath(app), "tool_definition", r.webmcp.tools);
    writeRecords(webmcpContractsPath(app), "contract", r.webmcp.contracts);
    console.log(`\n${app}: ${r.tools.length} tools from ${r.pages.length} pages (${r.pages.join(", ")})\n`);
    console.log(
      table(
        ["tool", "risk", "surfaces", "pre", "post", "inv"],
        r.tools.map((t, i) => {
          const c = r.contracts[i];
          return [t.tool_id, t.risk_level, [...new Set(t.provenance.map((p) => p.surface))].join(","), c?.preconditions.length ?? 0, c?.postconditions.length ?? 0, c?.invariants.length ?? 0];
        }),
      ),
    );
    if (r.rejected.length) console.log(`\nrejected:\n${r.rejected.map((x) => `  ${x.ref}: ${x.reason}`).join("\n")}`);
    console.log(`\nWebMCP set (page-scoped):\n${table(["tool", "kind", "page", "inputs"], r.webmcp.tools.map((t) => [t.name, t.handler.kind, t.handler.page ?? "*", Object.keys((t.input_schema.properties ?? {}) as object).join(", ") || "-"]))}`);
    if (r.webmcp.skipped.length) console.log(`no page control (not WebMCP-reachable):\n${r.webmcp.skipped.map((x) => `  ${x.ref}`).join("\n")}`);
    console.log(`\nwrote ${repoRelative(toolsPath(app))}, ${repoRelative(contractsPath(app))} and the WebMCP set in ${repoRelative(webmcpToolsPath(app))}`);
  } finally {
    await browser.close();
  }
}

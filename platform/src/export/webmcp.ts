/**
 * WebMCP export: turns an app's *verified* tools into (a) a script the site includes so WebMCP-aware agents
 * can call the tools in the page, and (b) a manifest recording what was exported, each tool's evidence and
 * contract size, and what was withheld. Quarantined and unverified tools are never exported.
 *
 * Registration follows the W3C WebMCP draft (`document.modelContext.registerTool`), falling back to
 * `navigator.modelContext` (earlier drafts, MCP-B polyfill), else exposing the tools on
 * `window.__specxWebMCPTools` for in-page agents and tests.
 */
import type { JsonSchema, Provenance, RiskLevel, ToolContract, ToolDefinition } from "../contracts/types.js";

export interface WebMCPManifest {
  app: string;
  generated_at: string;
  spec: string;
  tools: {
    name: string;
    tool_id: string;
    description: string;
    inputSchema: JsonSchema;
    risk_level: RiskLevel;
    version: number;
    metadata_revision: number;
    provenance: Provenance[];
    contract: { preconditions: number; postconditions: number; invariants: number } | null;
  }[];
  quarantined: string[];
  excluded: { name: string; status: string }[];
}

export function exportWebMCP(app: string, tools: ToolDefinition[], contracts: ToolContract[]): { script: string; manifest: WebMCPManifest } {
  const verified = tools.filter((t) => t.status === "verified");
  const contractOf = new Map(contracts.map((c) => [c.tool_id, c]));
  const manifest: WebMCPManifest = {
    app,
    generated_at: new Date().toISOString(),
    spec: "W3C WebMCP draft: document.modelContext.registerTool (fallback navigator.modelContext)",
    tools: verified.map((t) => {
      const c = contractOf.get(t.tool_id);
      return {
        name: t.name,
        tool_id: t.tool_id,
        description: t.description,
        inputSchema: t.input_schema,
        risk_level: t.risk_level,
        version: t.version,
        metadata_revision: t.metadata_revision,
        provenance: t.provenance,
        contract: c ? { preconditions: c.preconditions.length, postconditions: c.postconditions.length, invariants: c.invariants.length } : null,
      };
    }),
    quarantined: tools.filter((t) => t.status === "quarantined").map((t) => t.name),
    excluded: tools.filter((t) => t.status !== "verified" && t.status !== "quarantined").map((t) => ({ name: t.name, status: t.status ?? "generated" })),
  };

  const entries = verified
    .map(
      (t) => `  {
    name: ${JSON.stringify(t.name)},
    description: ${JSON.stringify(t.description)},
    inputSchema: ${JSON.stringify(t.input_schema)},
    annotations: { readOnlyHint: ${t.risk_level === "read"} },
    handler: ${t.handler.code.split("\n").join("\n    ")},
  }`,
    )
    .join(",\n");

  const script = `/* SpecX WebMCP tools for "${app}" — generated ${manifest.generated_at}.
 * Only tools that passed contract verification in the SpecX sandbox are included
 * (${manifest.tools.length} exported; quarantined: ${manifest.quarantined.join(", ") || "none"}). Do not edit by hand. */
(async () => {
  const definitions = [
${entries}
  ];
  const tools = definitions.map(({ handler, ...tool }) => ({
    ...tool,
    async execute(input) {
      try {
        const output = await handler(input ?? {});
        return { content: [{ type: "text", text: JSON.stringify(output) }] };
      } catch (err) {
        return { content: [{ type: "text", text: "Error: " + (err && err.message ? err.message : String(err)) }], isError: true };
      }
    },
  }));
  const host = (typeof document !== "undefined" && document.modelContext) || (typeof navigator !== "undefined" && navigator.modelContext);
  if (!host || typeof host.registerTool !== "function") {
    window.__specxWebMCPTools = tools;
    return;
  }
  for (const tool of tools) await host.registerTool(tool);
  console.info("[specx] registered " + tools.length + " WebMCP tools");
})();
`;
  return { script, manifest };
}

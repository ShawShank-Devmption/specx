/**
 * WebMCP export: turns an app's *verified* tools into (a) a script the site includes so WebMCP-aware agents
 * can call the tools in the page, and (b) a manifest recording what was exported, each tool's evidence and
 * contract size, and what was withheld. Quarantined and unverified tools are never exported.
 *
 * Registration follows the W3C WebMCP draft (`document.modelContext.registerTool`), falling back to
 * `navigator.modelContext` (Chrome's early preview, MCP-B polyfill), else exposing the tools on
 * `window.__specxWebMCPTools` so they can be called from DevTools or by in-page agents.
 *
 * Each tool is registered only on the page it belongs to (`handler.page`, "*" = every page). Payment and
 * delete tools ask the user in the page before running: the WebMCP draft has no confirmation API, so the
 * site shows its own dialog and the tool waits for the user's answer.
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
    kind: "api" | "ui";
    page: string;
    confirm: boolean;
    version: number;
    metadata_revision: number;
    provenance: Provenance[];
    contract: { preconditions: number; postconditions: number; invariants: number } | null;
  }[];
  quarantined: string[];
  excluded: { name: string; status: string }[];
}

const needsConfirmation = (t: ToolDefinition) => t.risk_level === "payment" || t.risk_level === "delete";
const pageRegex = (page: string) =>
  page === "*" ? null : `^${page.split("/").map((s) => (s.startsWith(":") ? "[^/]+" : s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))).join("/")}/?$`;

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
        kind: t.handler.kind,
        page: t.handler.page ?? "*",
        confirm: needsConfirmation(t),
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
    page: ${JSON.stringify(pageRegex(t.handler.page ?? "*"))},
    confirm: ${needsConfirmation(t)},
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
  // The site asks its user before an agent spends money or deletes data. Resolves true on "Allow".
  const askUser = (tool, input, signal) =>
    new Promise((resolve) => {
      const box = document.createElement("div");
      box.setAttribute("role", "alertdialog");
      box.setAttribute("aria-modal", "true");
      box.setAttribute("aria-label", "An AI agent is asking for permission");
      box.setAttribute("data-specx-confirm", "dialog");
      box.style.cssText = "position:fixed;right:16px;bottom:16px;max-width:380px;z-index:2147483647;background:#fff;color:#111;border:2px solid #111;border-radius:8px;padding:14px;font:14px/1.4 system-ui,sans-serif;box-shadow:0 6px 24px rgba(0,0,0,.35)";
      box.innerHTML = '<strong>An AI agent wants to run:</strong> <code></code><pre style="white-space:pre-wrap;margin:8px 0"></pre><p style="margin:0 0 10px"></p><button type="button" data-specx-confirm="accept">Allow</button> <button type="button" data-specx-confirm="reject">Deny</button>';
      box.querySelector("code").textContent = tool.name;
      box.querySelector("pre").textContent = JSON.stringify(input, null, 1);
      box.querySelector("p").textContent = tool.description;
      const done = (answer) => { box.remove(); resolve(answer); };
      box.querySelector('[data-specx-confirm="accept"]').addEventListener("click", () => done(true));
      box.querySelector('[data-specx-confirm="reject"]').addEventListener("click", () => done(false));
      if (signal) signal.addEventListener("abort", () => done(false), { once: true });
      document.body.appendChild(box);
      box.querySelector('[data-specx-confirm="reject"]').focus();
    });
  const here = (typeof location !== "undefined" && location.pathname) || "/";
  const tools = definitions.filter((d) => d.page === null || new RegExp(d.page).test(here)).map(({ handler, page, confirm, ...tool }) => ({
    ...tool,
    async execute(input, options) {
      if (confirm && !(await askUser(tool, input ?? {}, options && options.signal))) {
        return { content: [{ type: "text", text: "The user declined " + tool.name + "; nothing was changed." }], isError: true };
      }
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

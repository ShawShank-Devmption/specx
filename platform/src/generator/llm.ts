/**
 * Optional LLM namer for F3 (`--namer llm`): asks Claude for an agent-facing tool name, description and
 * parameter descriptions from the candidate's evidence, using structured output. Any refusal, missing
 * output or invalid name falls back to the deterministic template namer, so generation never fails on it.
 */
import { zodOutputFormat } from "@anthropic-ai/sdk/helpers/zod";
import { z } from "zod/v4";
import type { Candidate } from "./candidates.js";
import { templateNamer, type Namer } from "./emit.js";

/** The slice of the Anthropic client the namer uses (an `Anthropic` instance satisfies it). */
export interface NamerClient {
  messages: { parse(params: unknown): Promise<{ stop_reason: string | null; parsed_output: unknown }> };
}

const Naming = z.object({
  name: z.string(),
  description: z.string(),
  param_descriptions: z.array(z.object({ param: z.string(), description: z.string() })),
});

const SYSTEM = `You name WebMCP tools that AI agents will call on a website.
Each tool performs exactly one action against one HTTP endpoint. Given the evidence (route code, UI button labels, request and response samples), return:
- name: snake_case verb_noun, 3-64 chars, matching ^[a-z][a-z0-9_]{2,63}$, named after what the user achieves (e.g. add_to_cart, not create_cart_item).
- description: at most 300 characters. Say what the tool does and what it does not do. If a parameter is an id, say which tool returns it. If the action spends money, says so and that the user must confirm first. If it deletes data, say so.
- param_descriptions: one short description for every parameter listed.`;

function evidence(c: Candidate): string {
  const lines = [
    `Route: ${c.route.method} ${c.route.path} (risk: ${c.risk_level})`,
    `Code: ${c.route.snippet}`,
    `SQL: ${c.route.statements.map((s) => s.sql).join(" | ") || "none"}`,
    `Parameters: ${c.inputs.map((f) => `${f.name}:${f.type}${f.enum ? ` one of ${f.enum.join("/")}` : ""}`).join(", ") || "none"}`,
    `UI triggers: ${c.triggers.map((t) => `${t.role} "${t.name}" on ${t.page}`).join("; ") || "none"}`,
    `Response sample: ${JSON.stringify(c.samples[0]?.response ?? null).slice(0, 600)}`,
  ];
  return lines.join("\n");
}

export function llmNamer(client: NamerClient, model: string): Namer {
  return async (c: Candidate) => {
    const fallback = await templateNamer(c);
    const res = await client.messages.parse({
      model,
      max_tokens: 4096,
      output_config: { effort: "high", format: zodOutputFormat(Naming) },
      system: [{ type: "text", text: SYSTEM, cache_control: { type: "ephemeral" } }],
      messages: [{ role: "user", content: evidence(c) }],
    });
    const parsed = Naming.safeParse(res.parsed_output);
    if (res.stop_reason === "refusal" || !parsed.success || !/^[a-z][a-z0-9_]{2,63}$/.test(parsed.data.name)) return fallback;
    const description = parsed.data.description.length >= 10 && parsed.data.description.length <= 1000 ? parsed.data.description : fallback.description;
    const given = Object.fromEntries(parsed.data.param_descriptions.map((p) => [p.param, p.description]));
    return {
      name: parsed.data.name,
      description,
      paramDescriptions: Object.fromEntries(c.inputs.map((f) => [f.name, given[f.name] ?? fallback.paramDescriptions[f.name] ?? f.name])),
    };
  };
}

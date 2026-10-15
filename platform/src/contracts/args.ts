/**
 * Derives valid example arguments for a tool from its contract's db_row_exists preconditions and the
 * current DB state, then fills the remaining parameters from the input schema. Used by F1 verification
 * and by S1 (through the sandbox's example_args endpoint) as the starting point for mutations.
 */
import type { DbSnapshot, ToolContract, ToolDefinition } from "./types.js";
import { argRef, rowMatches, type RefScope } from "./where.js";

export interface ExampleArgs {
  args: Record<string, unknown>;
  /** clause_ids of preconditions no current row can satisfy (run a producer tool first). */
  unsatisfied: string[];
}

/** mulberry32: tiny deterministic PRNG so a seed always picks the same rows. */
function rng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

type PropSchema = { type?: string; enum?: unknown[]; const?: unknown; minimum?: number; format?: string };

function fromSchema(name: string, s: PropSchema, n: number): unknown {
  if (s.const !== undefined) return s.const;
  if (s.enum?.length) return s.enum[0];
  switch (s.type) {
    case "integer":
    case "number":
      return s.minimum ?? 1;
    case "boolean":
      return true;
    case "string":
      return s.format === "email" || name.includes("email") ? `new_${n}@example.com` : `new_${n}`;
    default:
      return null;
  }
}

export function exampleArgs(
  tool: ToolDefinition,
  contract: ToolContract,
  db: DbSnapshot,
  user: RefScope["user"],
  opts: { seed?: number } = {},
): ExampleArgs {
  const args: Record<string, unknown> = {};
  const unsatisfied: string[] = [];
  const random = opts.seed === undefined ? null : rng(opts.seed);

  for (const clause of contract.preconditions) {
    if (clause.kind !== "db_row_exists") continue;
    const where = (clause.params.where ?? {}) as Record<string, unknown>;
    const argCols = Object.entries(where).filter(([, v]) => argRef(v) !== null);
    const fixed = Object.fromEntries(Object.entries(where).filter(([, v]) => {
      const a = argRef(v);
      return a === null || a in args;
    }));
    const rows = (db[String(clause.params.table)]?.rows ?? []).filter((r) => rowMatches(r, fixed, { args, user }));
    const row = random ? rows[Math.floor(random() * rows.length)] : rows.at(-1);
    if (!row) {
      unsatisfied.push(clause.clause_id);
      continue;
    }
    for (const [col, ref] of argCols) args[argRef(ref) as string] ??= row[col];
  }

  const n = 1 + Object.values(db).reduce((sum, t) => sum + t.count, 0);
  const props = (tool.input_schema.properties ?? {}) as Record<string, PropSchema>;
  for (const [name, schema] of Object.entries(props)) if (!(name in args)) args[name] = fromSchema(name, schema, n);
  return { args, unsatisfied };
}

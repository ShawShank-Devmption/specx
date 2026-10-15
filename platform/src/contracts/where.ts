/**
 * Value references and `where` filters shared by checkers and example-argument derivation.
 * Equality compares as strings (SQLite affinity makes 1 and "1" the same id); ops compare numerically
 * when both sides are numbers.
 */
import type { Row, Where } from "./types.js";

export interface RefScope {
  args: Record<string, unknown>;
  user: { id: unknown } | null;
}

export const argRef = (v: unknown): string | null => (typeof v === "string" && v.startsWith("$args.") ? v.slice(6) : null);

export function resolveRef(v: unknown, scope: RefScope): unknown {
  const arg = argRef(v);
  if (arg !== null) return scope.args[arg];
  if (v === "$user.id") return scope.user?.id;
  return v;
}

const OPS: Record<string, (a: number | string, b: number | string) => boolean> = {
  "<": (a, b) => a < b,
  "<=": (a, b) => a <= b,
  ">": (a, b) => a > b,
  ">=": (a, b) => a >= b,
  "!=": (a, b) => a !== b,
};

export function conditionHolds(actual: unknown, cond: unknown, scope: RefScope): boolean {
  if (cond !== null && typeof cond === "object" && "op" in cond) {
    const { op, value } = cond as { op: string; value: unknown };
    const cmp = OPS[op];
    if (!cmp || actual === null || actual === undefined) return false;
    const bothNumeric = typeof actual === "number" && typeof value === "number";
    return bothNumeric ? cmp(actual, value) : cmp(String(actual), String(value));
  }
  const expected = resolveRef(cond, scope);
  return expected !== undefined && expected !== null && String(actual) === String(expected);
}

export function rowMatches(row: Row, where: Where, scope: RefScope): boolean {
  return Object.entries(where).every(([col, cond]) => conditionHolds(row[col], cond, scope));
}

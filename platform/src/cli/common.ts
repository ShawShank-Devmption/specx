/** Shared CLI helpers: manifest loading, JSON file IO under results/, and a plain-text table printer. */
import fs from "node:fs";
import type { AppManifest } from "../contracts/types.js";
import { validate, type SchemaName } from "../contracts/validate.js";
import { ensureParent, manifestPath } from "../paths.js";

export function loadManifest(app: string): AppManifest {
  const file = manifestPath(app);
  if (!fs.existsSync(file)) throw new Error(`unknown app "${app}" (no ${file})`);
  return validate<AppManifest>("app_manifest", JSON.parse(fs.readFileSync(file, "utf8")));
}

export function readJson<T>(file: string): T {
  if (!fs.existsSync(file)) throw new Error(`missing ${file} — run the earlier pipeline stage first`);
  return JSON.parse(fs.readFileSync(file, "utf8")) as T;
}

/** Validates every element against `schema`, then writes pretty JSON. */
export function writeRecords(file: string, schema: SchemaName, records: unknown[] | unknown): void {
  for (const r of Array.isArray(records) ? records : [records]) validate(schema, r);
  fs.writeFileSync(ensureParent(file), `${JSON.stringify(records, null, 2)}\n`);
}

export function readJsonl<T>(file: string): T[] {
  if (!fs.existsSync(file)) return [];
  return fs
    .readFileSync(file, "utf8")
    .split("\n")
    .filter((l) => l.trim())
    .map((l) => JSON.parse(l) as T);
}

export function table(headers: string[], rows: (string | number)[][]): string {
  const cells = [headers, ...rows.map((r) => r.map(String))];
  const widths = headers.map((_, i) => Math.max(...cells.map((r) => (r[i] ?? "").length)));
  const line = (r: string[]) => r.map((c, i) => c.padEnd(widths[i] ?? 0)).join("  ");
  return [line(headers), widths.map((w) => "-".repeat(w)).join("  "), ...cells.slice(1).map(line)].join("\n");
}

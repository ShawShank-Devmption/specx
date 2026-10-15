/**
 * Single owner of every filesystem location the platform reads or writes.
 * Results live under <repo>/results unless SPECX_RESULTS_DIR overrides it (absolute or repo-relative).
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
export const PLATFORM_ROOT = path.join(REPO_ROOT, "platform");
export const CONTRACTS_DIR = path.join(REPO_ROOT, "contracts");
export const SEED_APPS_DIR = path.join(PLATFORM_ROOT, "seed-apps");

export function resultsDir(): string {
  const override = process.env.SPECX_RESULTS_DIR;
  if (!override) return path.join(REPO_ROOT, "results");
  return path.isAbsolute(override) ? override : path.join(REPO_ROOT, override);
}

const inResults = (...parts: string[]): string => path.join(resultsDir(), ...parts);

export const toolsPath = (app: string): string => inResults("tools", `${app}.tools.json`);
export const contractsPath = (app: string): string => inResults("contracts", `${app}.contracts.json`);
export const verdictsDir = (): string => inResults("verdicts");
export const verdictsPath = (source: string): string => inResults("verdicts", `${source}.jsonl`);
export const eventsPath = (sessionId: string): string => inResults("events", `${sessionId}.jsonl`);
export const screenshotPath = (runId: string): string => inResults("screenshots", `${runId}.png`);
export const graphPath = (app: string): string => inResults("graphs", `${app}.graph.json`);
export const manifestPath = (app: string): string => path.join(SEED_APPS_DIR, app, "app.json");

/** Path relative to the repo root, used inside records so they stay portable between machines. */
export const repoRelative = (p: string): string => path.relative(REPO_ROOT, p);

export function ensureParent(file: string): string {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  return file;
}

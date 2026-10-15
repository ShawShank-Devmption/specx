#!/usr/bin/env node
// Starts every seed app listed in seed-apps/*/app.json as a child process and keeps them in the foreground.
// Ctrl-C stops all of them. Exits non-zero if any app dies.
import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const appsDir = path.join(root, "seed-apps");
const only = process.argv.slice(2);
const manifests = fs
  .readdirSync(appsDir)
  .filter((d) => fs.existsSync(path.join(appsDir, d, "app.json")))
  .map((d) => JSON.parse(fs.readFileSync(path.join(appsDir, d, "app.json"), "utf8")))
  .filter((m) => only.length === 0 || only.includes(m.app));

const children = manifests.map((m) => {
  const child = spawn(process.execPath, [path.join(appsDir, m.app, "server.js")], {
    cwd: root,
    env: { ...process.env, PORT: String(m.port) },
    stdio: ["ignore", "inherit", "inherit"],
  });
  child.on("exit", (code) => {
    console.error(`[start-apps] ${m.app} exited with code ${code}`);
    stopAll(code ?? 1);
  });
  console.log(`[start-apps] ${m.app} -> ${m.base_url}`);
  return child;
});

function stopAll(code) {
  for (const c of children) if (c.exitCode === null) c.kill("SIGTERM");
  process.exit(code);
}
process.on("SIGINT", () => stopAll(0));
process.on("SIGTERM", () => stopAll(0));
if (children.length === 0) console.error("[start-apps] no seed apps found");

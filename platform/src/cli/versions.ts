/** `specx versions` — pins the runtime the results were produced with (reproducibility package). */
import fs from "node:fs";
import path from "node:path";
import { chromium } from "playwright";
import { ensureParent, PLATFORM_ROOT, repoRelative, resultsDir } from "../paths.js";

export async function versionsCommand(): Promise<void> {
  const browser = await chromium.launch();
  const pkg = (name: string) => (JSON.parse(fs.readFileSync(path.join(PLATFORM_ROOT, "node_modules", name, "package.json"), "utf8")) as { version: string }).version;
  const out = {
    recorded_at: new Date().toISOString(),
    node: process.version,
    playwright: pkg("playwright"),
    chromium: browser.version(),
    anthropic_sdk: pkg("@anthropic-ai/sdk"),
    express: pkg("express"),
  };
  await browser.close();
  const file = ensureParent(path.join(resultsDir(), "final", "platform_versions.json"));
  fs.writeFileSync(file, `${JSON.stringify(out, null, 2)}\n`);
  console.log(JSON.stringify(out, null, 2));
  console.log(`wrote ${repoRelative(file)}`);
}

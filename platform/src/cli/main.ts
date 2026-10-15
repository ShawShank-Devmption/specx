/**
 * specx CLI (Dev A stages). Run from platform/: `npm run cli -- <command> [options]`.
 *   generate   --app <app> [--namer template|llm]
 *   verify     --app <app> [--runs 3]
 *   graph      --app <app>
 *   quarantine --app <app> [--from s1,s1_random,s1_coverage]
 *   versions
 */
import { pathToFileURL } from "node:url";
import { parseArgs } from "node:util";
import { generateCommand } from "./generate.js";
import { graphCommand } from "./graph.js";
import { versionsCommand } from "./versions.js";
import { quarantineCommand, verifyCommand } from "./verify.js";

const USAGE = `usage: specx <command> --app <app> [options]

commands:
  generate    F3: crawl + code evidence -> results/tools/<app>.tools.json, results/contracts/<app>.contracts.json
              --namer template|llm   (default template; llm needs ANTHROPIC_API_KEY)
  verify      F1: run every tool in the sandbox -> results/verdicts/f1.jsonl, tool status verified|quarantined
              --runs N (default 3)  --observe MS post-observe window (default 1000)
  graph       typed workflow graph -> results/graphs/<app>.graph.json (keeps S2's gnn edges)
  versions    record node, playwright and chromium versions -> results/final/platform_versions.json (no --app)
  quarantine  fold later evidence into tool status
              --from s1,s1_random,s1_coverage (default); S6 counts via anomaly flags on f1 runs
`;

export async function main(argv: string[]): Promise<number> {
  const [command, ...rest] = argv;
  const { values } = parseArgs({
    args: rest,
    options: {
      app: { type: "string" },
      namer: { type: "string", default: "template" },
      runs: { type: "string", default: "3" },
      observe: { type: "string", default: "1000" },
      from: { type: "string", default: "s1,s1_random,s1_coverage" },
      help: { type: "boolean", short: "h", default: false },
    },
    strict: true,
  });
  if (!command || values.help || command === "help") {
    console.log(USAGE);
    return command ? 0 : 1;
  }
  if (command === "versions") {
    await versionsCommand();
    return 0;
  }
  if (!values.app) throw new Error("--app is required");
  switch (command) {
    case "generate":
      await generateCommand(values.app, values.namer ?? "template");
      return 0;
    case "verify":
      await verifyCommand(values.app, Number(values.runs), Number(values.observe));
      return 0;
    case "graph":
      graphCommand(values.app);
      return 0;
    case "quarantine":
      quarantineCommand(values.app, (values.from ?? "").split(",").filter(Boolean));
      return 0;
    default:
      console.error(`unknown command "${command}"\n${USAGE}`);
      return 1;
  }
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) {
  main(process.argv.slice(2)).then(
    (code) => process.exit(code),
    (err: unknown) => {
      console.error(`error: ${(err as Error).message}`);
      process.exit(1);
    },
  );
}

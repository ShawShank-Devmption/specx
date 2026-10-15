/**
 * specx CLI (Dev A stages). Run from platform/: `npm run cli -- <command> [options]`.
 *   generate   --app <app> [--namer template|llm]
 *   verify     --app <app> [--runs 3]
 *   graph      --app <app>
 *   quarantine --app <app> [--from s1,s1_random,s1_coverage,s6_inject]
 */
import { parseArgs } from "node:util";
import { generateCommand } from "./generate.js";

const USAGE = `usage: specx <command> --app <app> [options]

commands:
  generate    F3: crawl + code evidence -> results/tools/<app>.tools.json, results/contracts/<app>.contracts.json
              --namer template|llm   (default template; llm needs ANTHROPIC_API_KEY)
`;

export async function main(argv: string[]): Promise<number> {
  const [command, ...rest] = argv;
  const { values } = parseArgs({
    args: rest,
    options: {
      app: { type: "string" },
      namer: { type: "string", default: "template" },
      help: { type: "boolean", short: "h", default: false },
    },
    strict: true,
  });
  if (!command || values.help || command === "help") {
    console.log(USAGE);
    return command ? 0 : 1;
  }
  if (!values.app) throw new Error("--app is required");
  switch (command) {
    case "generate":
      await generateCommand(values.app, values.namer ?? "template");
      return 0;
    default:
      console.error(`unknown command "${command}"\n${USAGE}`);
      return 1;
  }
}

main(process.argv.slice(2)).then(
  (code) => process.exit(code),
  (err: unknown) => {
    console.error(`error: ${(err as Error).message}`);
    process.exit(1);
  },
);

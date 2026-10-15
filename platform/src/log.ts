/**
 * Structured JSON-lines logging to stderr. Library code logs through this, never console.log,
 * so stdout stays free for CLI tables and machine-readable output.
 */
type Level = "debug" | "info" | "warn" | "error";
type Fields = Record<string, unknown>;

const quiet = (): boolean => process.env.SPECX_LOG === "silent";

function write(level: Level, mod: string, msg: string, fields: Fields): void {
  if (quiet() || (level === "debug" && process.env.SPECX_LOG !== "debug")) return;
  process.stderr.write(`${JSON.stringify({ ts: new Date().toISOString(), level, mod, msg, ...fields })}\n`);
}

export function log(mod: string) {
  return {
    debug: (msg: string, fields: Fields = {}) => write("debug", mod, msg, fields),
    info: (msg: string, fields: Fields = {}) => write("info", mod, msg, fields),
    warn: (msg: string, fields: Fields = {}) => write("warn", mod, msg, fields),
    error: (msg: string, fields: Fields = {}) => write("error", mod, msg, fields),
  };
}

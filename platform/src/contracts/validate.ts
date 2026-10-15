/**
 * Validates records against contracts/*.schema.json (draft 2020-12). Every record the platform emits
 * passes through here before it is written or returned, so a schema drift fails loudly at the producer.
 */
import fs from "node:fs";
import path from "node:path";
import { Ajv2020, type ValidateFunction } from "ajv/dist/2020.js";
import addFormatsModule from "ajv-formats";
import { CONTRACTS_DIR } from "../paths.js";

export type SchemaName =
  | "app_manifest"
  | "tool_definition"
  | "contract"
  | "event_record"
  | "verdict"
  | "workflow_graph"
  | "task"
  | "trial_result"
  | "patch";

// ajv-formats is CommonJS; under NodeNext its default import is the module object.
const addFormats = addFormatsModule as unknown as (ajv: Ajv2020) => Ajv2020;

const ajv = new Ajv2020({ allErrors: true, strict: false });
addFormats(ajv);
const compiled = new Map<SchemaName, ValidateFunction>();

function validator(name: SchemaName): ValidateFunction {
  let fn = compiled.get(name);
  if (!fn) {
    const schema = JSON.parse(fs.readFileSync(path.join(CONTRACTS_DIR, `${name}.schema.json`), "utf8")) as object;
    fn = ajv.compile(schema);
    compiled.set(name, fn);
  }
  return fn;
}

/** Returns `obj` typed as T when valid; throws `Error("<name><pointer>: <message>")` otherwise. */
export function validate<T = unknown>(name: SchemaName, obj: unknown): T {
  const fn = validator(name);
  if (!fn(obj)) {
    const e = fn.errors?.[0];
    throw new Error(`${name}${e?.instancePath ?? ""}: ${e?.message ?? "invalid"}`);
  }
  return obj as T;
}

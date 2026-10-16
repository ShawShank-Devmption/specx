/**
 * TypeScript mirrors of contracts/*.schema.json. Hand-written and kept to what the platform uses;
 * the JSON Schemas stay authoritative and every record is validated against them before it is written.
 */
export type RiskLevel = "read" | "write" | "delete" | "payment";
export type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
export type Severity = "low" | "medium" | "high";
export type Row = Record<string, unknown>;
export type JsonSchema = Record<string, unknown>;

/** `{column: scalar | "$args.x" | "$user.id" | {op, value}}` — see contracts/README.md. */
export type Where = Record<string, unknown>;

export interface ApprovedEndpoint {
  method: string;
  path: string;
  risk_level?: RiskLevel;
}

export interface ManifestInvariant {
  id: string;
  kind: "db_row_exists" | "db_no_row";
  table: string;
  where: Where;
  severity: Severity;
  description: string;
}

export interface AppManifest {
  app: string;
  port: number;
  base_url: string;
  start_cmd: string;
  home_path?: string;
  approved_hosts: string[];
  approved_endpoints: ApprovedEndpoint[];
  auth: { login_path: string; username: string; password: string };
  tables: string[];
  audit_table: string;
  invariants?: ManifestInvariant[];
}

export interface Provenance {
  surface: "code" | "dom" | "aria" | "network" | "test";
  ref: string;
  snippet?: string;
}

export interface ToolDefinition {
  tool_id: string;
  app: string;
  name: string;
  description: string;
  input_schema: JsonSchema;
  output_schema?: JsonSchema;
  handler: {
    kind: "api" | "ui";
    code: string;
    http?: { method: HttpMethod; path_template: string };
    selectors?: string[];
  };
  risk_level: RiskLevel;
  atomic: true;
  provenance: Provenance[];
  version: number;
  metadata_revision: number;
  status?: "generated" | "verified" | "quarantined";
}

export type ClauseKind =
  | "dom_exists"
  | "dom_absent"
  | "dom_text_contains"
  | "url_matches"
  | "auth_state"
  | "network_calls"
  | "no_unapproved_endpoint"
  | "no_third_party"
  | "db_delta"
  | "db_row_exists"
  | "db_no_row"
  | "audit_event"
  | "storage_untouched"
  | "at_most_once"
  | "output_matches";

export interface Clause {
  clause_id: string;
  surface: "code" | "dom" | "aria" | "network" | "audit" | "db";
  kind: ClauseKind;
  params: Record<string, unknown>;
  description: string;
  severity: Severity;
}

export interface ToolContract {
  tool_id: string;
  preconditions: Clause[];
  postconditions: Clause[];
  invariants: Clause[];
  derived_from?: { surface: string; ref: string }[];
}

export type Phase = "pre" | "during" | "post";
export type EventKind =
  | "tool_start"
  | "tool_end"
  | "network_request"
  | "network_response"
  | "dom_mutation"
  | "storage"
  | "console"
  | "navigation"
  | "audit";

export interface EventRecord {
  session_id: string;
  run_id: string;
  seq: number;
  t_ms: number;
  phase: Phase;
  kind: EventKind;
  data: Record<string, unknown>;
}

export interface DbTable {
  count: number;
  rows: Row[];
}
export type DbSnapshot = Record<string, DbTable>;

export interface AuditRow {
  id: number;
  event: string;
  actor: string;
  entity: string;
  entity_id: string;
  ts: string;
}

export interface ClauseResult {
  clause_id: string;
  kind: ClauseKind;
  surface: Clause["surface"];
  passed: boolean | null;
  observed?: unknown;
  expected?: unknown;
  message?: string;
}

export interface RowDelta {
  inserted: number;
  updated: number;
  deleted: number;
}

export interface EffectDiff {
  db: Record<string, RowDelta>;
  network: { method: string; url: string; status?: number; approved: boolean; third_party: boolean; phase: Phase }[];
  dom: { mutations: number; added_selectors: string[]; removed_selectors: string[]; url_before?: string; url_after?: string };
  storage: { area: string; op: string; key: string }[];
  audit: { event: string; count: number }[];
}

export type ViolationCategory =
  | "precondition"
  | "postcondition"
  | "side_effect"
  | "race"
  | "unapproved_endpoint"
  | "third_party"
  | "storage"
  | "anomaly";

export interface Violation {
  clause_id: string;
  severity: Severity;
  signature: string;
  category?: ViolationCategory;
}

export type VerdictStatus = "pass" | "fail" | "error" | "unverifiable";
export type Mode = "single" | "concurrent" | "replay";
export type Source = "f1" | "s1" | "s1_random" | "s1_coverage" | "s6_approved" | "s6_inject" | "f2" | "f4" | "fixture" | "mcp";

export interface Verdict {
  run_id: string;
  session_id: string;
  app: string;
  tool_id: string;
  tool_version?: number;
  metadata_revision?: number;
  args: Record<string, unknown>;
  mode: Mode;
  concurrency_group?: string;
  sequence_prefix?: string[];
  started_at: string;
  duration_ms: number;
  status: VerdictStatus;
  output?: unknown;
  clause_results: ClauseResult[];
  effect_diff: EffectDiff;
  violations: Violation[];
  anomaly: null | { iforest_score: number | null; lstm_error: number | null; flagged: boolean; flagged_windows?: number[] };
  source: Source;
  artifacts?: { screenshot_path?: string; events_path?: string; dom_diff_path?: string };
}

export type EdgeType = "order" | "state" | "data";
export type Evidence = "trace" | "contract" | "rule" | "gnn" | "manual";

export interface GraphNode {
  id: string;
  risk_level: RiskLevel;
  input_fields: string[];
  output_fields: string[];
  state_reads: string[];
  state_writes: string[];
  status?: "generated" | "verified" | "quarantined";
  violation_rate?: number;
}

export interface GraphEdge {
  src: string;
  dst: string;
  type: EdgeType;
  field?: string;
  evidence: Evidence;
  confidence: number;
  label?: boolean | null;
}

export interface GraphInvariant {
  id: string;
  kind: "requires" | "never_before" | "at_most_once" | "never_concurrent";
  tools: string[];
  description: string;
}

export interface WorkflowGraph {
  app: string;
  version: number;
  generated_at?: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  invariants: GraphInvariant[];
}

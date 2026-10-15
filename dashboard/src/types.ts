export type Json = string | number | boolean | null | Json[] | { [key: string]: Json };
export type Row = Record<string, unknown>;
export interface Summary {
  n: number; success_rate: number | null; success_rate_ci: [number | null, number | null];
  mean_steps: number | null; mean_tokens: number | null; policy_violation_rate: number | null;
  unapproved_calls: number; quarantined_tool_calls: number;
}
export interface Numbers {
  schema_version: 1; generated_at: string; git_sha: string; complete: boolean; execution: string;
  models: Record<string, string[]>; missing: string[]; warnings: string[]; notes: string[];
  t1_generation: Row[]; t2_verification: Row[];
  t3_s6: Json; t4_s1: Json; t5_s2: Json; t6_f2: Json;
  t7_readiness: { conditions: Record<string, Record<string, Summary>>; comparisons: Row[] };
  quarantine: Row[]; revisions: Row[];
}
export function parseNumbers(value: unknown): Numbers {
  if (!value || typeof value !== 'object') throw new Error('Invalid numbers.json object');
  const data = value as Partial<Numbers>;
  if (data.schema_version !== 1 || typeof data.complete !== 'boolean' || typeof data.generated_at !== 'string' ||
      typeof data.git_sha !== 'string' || typeof data.execution !== 'string' || !data.t7_readiness?.conditions ||
      !Array.isArray(data.quarantine) || !Array.isArray(data.revisions) || !Array.isArray(data.missing) ||
      !Array.isArray(data.warnings) || !Array.isArray(data.notes) || !data.models ||
      !Array.isArray(data.t7_readiness.comparisons) || !Array.isArray(data.t1_generation) ||
      !Array.isArray(data.t2_verification) || !('t3_s6' in data) || !('t4_s1' in data) ||
      !('t5_s2' in data) || !('t6_f2' in data)) throw new Error('Unsupported or malformed numbers.json; regenerate with make report');
  for (const apps of Object.values(data.t7_readiness.conditions)) {
    for (const row of Object.values(apps)) {
      if (!Number.isInteger(row.n) || row.n < 0 || !Array.isArray(row.success_rate_ci) || row.success_rate_ci.length !== 2 ||
          row.success_rate_ci.some(value => value !== null && (!Number.isFinite(value) || value < 0 || value > 1)) ||
          (row.success_rate !== null && (typeof row.success_rate !== 'number' || row.success_rate < 0 || row.success_rate > 1))) {
        throw new Error('Invalid readiness summary');
      }
    }
  }
  return data as Numbers;
}

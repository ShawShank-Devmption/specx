/**
 * Stamps raw observations into EventRecords: session_id, run_id, monotonic seq, t_ms since the run's
 * start, and phase. Events keep belonging to the last run (phase "post") until the next run begins, which
 * is where slow leaks show up. After a reset no run is active and observations are dropped.
 */
import type { EventKind, EventRecord, Phase } from "../contracts/types.js";

interface Options {
  now?: () => number;
  sink?: (e: EventRecord) => void;
}

export class EventRecorder {
  private readonly now: () => number;
  private readonly sink: ((e: EventRecord) => void) | undefined;
  private readonly all: EventRecord[] = [];
  private active = new Map<string, number>(); // run_id -> t0
  private defaultRun: string | null = null;
  private phases = new Map<string, Phase>();
  private seq = 0;

  constructor(
    readonly sessionId: string,
    opts: Options = {},
  ) {
    this.now = opts.now ?? (() => performance.now());
    this.sink = opts.sink;
  }

  /** Starts one run (or a concurrent group); all share t0. */
  begin(runIds: string[]): void {
    const t0 = this.now();
    this.active = new Map(runIds.map((id) => [id, t0]));
    this.defaultRun = runIds[0] ?? null;
    this.phases = new Map(runIds.map((id) => [id, "pre" as Phase]));
  }

  /** Sets the phase of one run of the active group, or of every active run when `runId` is omitted. */
  setPhase(phase: Phase, runId?: string): void {
    for (const id of runId === undefined ? this.active.keys() : [runId]) if (this.active.has(id)) this.phases.set(id, phase);
  }

  /** Stops attribution (used on reset): later observations are dropped until the next begin(). */
  clear(): void {
    this.active.clear();
    this.defaultRun = null;
  }

  record(kind: EventKind, data: Record<string, unknown>, runId?: string): EventRecord | null {
    const id = runId !== undefined && this.active.has(runId) ? runId : this.defaultRun;
    const t0 = id === null ? undefined : this.active.get(id);
    if (id === null || t0 === undefined) return null;
    const e: EventRecord = { session_id: this.sessionId, run_id: id, seq: this.seq++, t_ms: Math.round((this.now() - t0) * 10) / 10, phase: this.phases.get(id) ?? "pre", kind, data };
    this.all.push(e);
    this.sink?.(e);
    return e;
  }

  eventsFor(runId: string): EventRecord[] {
    return this.all.filter((e) => e.run_id === runId);
  }

  since(seq: number): EventRecord[] {
    return this.all.filter((e) => e.seq >= seq);
  }
}

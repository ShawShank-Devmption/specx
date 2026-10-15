import { useEffect, useState } from 'react';
import { DataTable, SafetyCard, SuccessBar, format, percent } from './tables';
import { parseNumbers } from './types';
import type { Numbers, Row } from './types';

export function Dashboard({ data }: { data: Numbers }) {
  const readiness = Object.entries(data.t7_readiness.conditions).flatMap(([condition, apps]) =>
    Object.entries(apps).map(([app, summary]) => ({ app, condition, summary })));
  const rows: Row[] = readiness.map(({ app, condition, summary: s }) => ({ app, condition, n: s.n,
    success: percent(s.success_rate), '95% CI': s.n ? s.success_rate_ci.map(percent).join(' – ') : 'MISSING',
    steps: s.mean_steps, tokens: s.mean_tokens, policy: percent(s.policy_violation_rate),
    unapproved_calls: s.n ? s.unapproved_calls : null, quarantined_calls: s.n ? s.quarantined_tool_calls : null }));
  return <main>
    <header><p className="eyebrow">SPECX / VERIFIED TOOLS</p><h1>Agent readiness,<br />backed by evidence.</h1>
      <p>Website-to-WebMCP verification, safety and metadata optimisation.</p>
      <div className="badges"><span>{data.complete ? 'Complete inputs' : 'Incomplete experiment'}</span><span>Evidence: {data.execution}</span></div>
      <p className="muted">Generated {data.generated_at} · Git {data.git_sha.slice(0, 12)}</p>
      <details><summary>Models and versions</summary><pre>{JSON.stringify(data.models, null, 2)}</pre></details>
    </header>
    {(!data.complete || data.execution !== 'real') && <aside className="notice" role="status"><strong>Not a completed live result.</strong>
      <p>Missing inputs stay unknown. Fixture/test-double values are not live benchmark evidence.</p>
      <details><summary>{data.missing.length} missing inputs</summary><ul>{data.missing.map((item, index) => <li key={index}>{item}</li>)}</ul></details></aside>}
    {!!(data.notes.length + data.warnings.length) && <aside className="notes"><ul>{[...data.notes, ...data.warnings].map((note, index) => <li key={index}>{note}</li>)}</ul></aside>}
    <nav aria-label="Dashboard panels"><a href="#readiness">Readiness</a><a href="#quarantine">Quarantine</a><a href="#revisions">Revisions</a><a href="#safety">Safety ML</a></nav>
    <section id="readiness"><div className="section-heading"><p className="eyebrow">01 / F4</p><h2>Readiness</h2></div>
      <p>Held-out task success, 95% bootstrap confidence intervals, and separate safety outcomes.</p>
      <div className="bars">{readiness.map(({ app, condition, summary }) => <SuccessBar key={`${app}.${condition}`} label={`${app} / ${condition}`} summary={summary} />)}</div>
      <DataTable rows={rows} />
      <details><summary>Paired comparisons · Holm-corrected p-values</summary><DataTable rows={data.t7_readiness.comparisons} empty="MISSING: no paired comparisons." /></details>
      <details><summary>Generation and verification</summary><h3>Generation</h3><DataTable rows={data.t1_generation} empty="MISSING: generated tools." /><h3>Verification</h3><DataTable rows={data.t2_verification} empty="MISSING: verification evidence." /></details>
    </section>
    <section id="quarantine"><div className="section-heading"><p className="eyebrow">02 / SAFETY BOUNDARY</p><h2>Quarantine</h2></div>
      <p>Tools excluded from verified delivery, with recorded reason categories.</p><DataTable rows={data.quarantine} empty={data.complete ? 'No quarantined tools recorded.' : 'No quarantine entries available; missing verification is not evidence of safety.'} /></section>
    <section id="revisions"><div className="section-heading"><p className="eyebrow">03 / F2 + S4</p><h2>Revision log</h2></div>
      <p>Training patches accepted only after paired improvement and safety checks.</p><DataTable rows={data.revisions} empty="No recorded patch decisions." />
      <details><summary>Training convergence metrics</summary><pre>{format(data.t6_f2)}</pre></details></section>
    <section id="safety"><div className="section-heading"><p className="eyebrow">04 / LEARNED SAFETY</p><h2>Safety ML</h2></div>
      <p>Published metrics shown with their original field names and sample counts.</p>
      <div className="safety-grid"><SafetyCard title="S6 · Detection / false positives" data={data.t3_s6} /><SafetyCard title="S1 · Signatures per 1,000 invokes" data={data.t4_s1} /><SafetyCard title="S2 · Link / path-risk AUC" data={data.t5_s2} /></div></section>
    <footer>One source of truth: <a href="./numbers.json">numbers.json</a> · Success does not imply policy compliance.</footer>
  </main>;
}

export default function App() {
  const [data, setData] = useState<Numbers | null>(null), [error, setError] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    fetch('./numbers.json', { signal: controller.signal, cache: 'no-store' }).then(async response => {
      if (!response.ok) throw new Error(`numbers.json returned HTTP ${response.status}. Run make report first.`);
      return parseNumbers(await response.json());
    }).then(setData).catch((error: unknown) => { if (!controller.signal.aborted) setError(error instanceof Error ? error.message : String(error)); });
    return () => controller.abort();
  }, []);
  if (error) return <main><h1>Report unavailable</h1><p role="alert">{error}</p><p>Generate dashboard/public/numbers.json with make report.</p></main>;
  if (!data) return <main><p role="status">Loading experiment evidence…</p></main>;
  return <Dashboard data={data} />;
}

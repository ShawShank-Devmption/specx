import { useEffect, useState } from 'react';
import { DataTable, SafetyCard, SuccessBar, format, percent } from './tables';
import { parseNumbers } from './types';
import type { Numbers, Row } from './types';

export function Dashboard({ data }: { data: Numbers }) {
  const conditionOrder = ['raw_dom', 'generated', 'verified', 'optimised'];
  const readiness = Object.entries(data.t7_readiness.conditions)
    .sort(([left], [right]) => conditionOrder.indexOf(left) - conditionOrder.indexOf(right))
    .flatMap(([condition, apps]) =>
    Object.entries(apps).map(([app, summary]) => ({ app, condition, summary })));
  const rows: Row[] = readiness.map(({ app, condition, summary: s }) => ({ app, condition, n: s.n,
    success: percent(s.success_rate), '95% CI': s.n ? s.success_rate_ci.map(percent).join(' – ') : 'MISSING',
    steps: s.mean_steps, tokens: s.mean_tokens, policy: percent(s.policy_violation_rate),
    unapproved_calls: s.n ? s.unapproved_calls : null, quarantined_calls: s.n ? s.quarantined_tool_calls : null }));
  return <main className="dashboard-shell" data-theme="dark">
    <a className="skip-link" href="#readiness">Skip to benchmark evidence</a>
    <div className="topbar"><div className="topbar-inner">
      <a className="brand" href="#overview" aria-label="SpecX overview">Spec<span className="brand-accent">X</span></a>
      <nav className="top-nav" aria-label="Dashboard panels"><a href="#readiness">Readiness</a><a href="#quarantine">Quarantine</a><a href="#revisions">Revisions</a><a href="#safety">Safety ML</a></nav>
    </div></div>
    <header className="hero" id="overview"><div className="hero-inner">
      <div className="hero-copy"><p className="eyebrow">SPECX / EXPERIMENT RESULTS</p>
        <h1>Evaluation dashboard</h1>
        <p className="hero-description">Readiness, quarantined tools, revision decisions, and safety metrics from the project report.</p>
        <div className="hero-actions"><a className="primary-link" href="#readiness">Explore benchmark <span aria-hidden="true">↗</span></a><a className="secondary-link" href="#quarantine">Review quarantine <span aria-hidden="true">→</span></a></div>
      </div>
    </div></header>
    <div className="report-meta"><div className="badges"><span className={data.complete && data.execution === 'real' ? 'badge-live' : 'badge-pending'}><span className="status-dot" />{data.complete ? 'Complete inputs' : 'Incomplete experiment'}</span><span>Evidence / {data.execution}</span></div>
      <span className="muted">Updated {data.generated_at} <span className="meta-divider">/</span> Git {data.git_sha.slice(0, 12)}</span>
      <details><summary>Models &amp; versions</summary><pre>{JSON.stringify(data.models, null, 2)}</pre></details></div>
    {(!data.complete || data.execution !== 'real') && <aside className="notice" role="status"><div className="notice-icon" aria-hidden="true">!</div><div><strong>Not a completed live result.</strong>
      <p>Missing inputs stay unknown. Fixture/test-double values are not live benchmark evidence.</p>
      <details><summary>{data.missing.length} missing inputs <span aria-hidden="true">↗</span></summary><ul>{data.missing.map((item, index) => <li key={index}>{item}</li>)}</ul></details></div></aside>}
    {!!(data.notes.length + data.warnings.length) && <aside className="notes"><ul>{[...data.notes, ...data.warnings].map((note, index) => <li key={index}>{note}</li>)}</ul></aside>}
    <section id="readiness"><div className="section-heading"><div><p className="eyebrow">01 / F4 BENCHMARK</p><h2>Readiness</h2></div></div>
      <p className="section-description">Held-out task success, 95% bootstrap confidence intervals, and separate safety outcomes.</p>
      <div className="bars">{readiness.map(({ app, condition, summary }) => <SuccessBar key={`${app}.${condition}`} label={`${app} / ${condition}`} summary={summary} />)}</div>
      <DataTable rows={rows} />
      <details><summary>Paired comparisons · Holm-corrected p-values</summary><DataTable rows={data.t7_readiness.comparisons} empty="MISSING: no paired comparisons." /></details>
      <details><summary>Generation and verification</summary><h3>Generation</h3><DataTable rows={data.t1_generation} empty="MISSING: generated tools." /><h3>Verification</h3><DataTable rows={data.t2_verification} empty="MISSING: verification evidence." /></details>
    </section>
    <section id="quarantine"><div className="section-heading"><div><p className="eyebrow">02 / SAFETY BOUNDARY</p><h2>Quarantine</h2></div></div>
      <p className="section-description">Tools excluded from verified delivery, with recorded reason categories.</p><DataTable rows={data.quarantine} empty={data.complete ? 'No quarantined tools recorded.' : 'No quarantine entries available; missing verification is not evidence of safety.'} /></section>
    <section id="revisions"><div className="section-heading"><div><p className="eyebrow">03 / F2 + S4 OPTIMISATION</p><h2>Revision log</h2></div></div>
      <p className="section-description">Training patches accepted only after paired improvement and safety checks.</p><DataTable rows={data.revisions} empty="No recorded patch decisions." />
      <details><summary>Training convergence metrics</summary><pre>{format(data.t6_f2)}</pre></details></section>
    <section id="safety"><div className="section-heading"><div><p className="eyebrow">04 / LEARNED SAFETY</p><h2>Safety ML</h2></div></div>
      <p className="section-description">Published metrics shown with their original field names and sample counts.</p>
      <div className="safety-grid"><SafetyCard title="S6 · Detection / false positives" data={data.t3_s6} /><SafetyCard title="S1 · Signatures per 1,000 invokes" data={data.t4_s1} /><SafetyCard title="S2 · Link / path-risk AUC" data={data.t5_s2} /></div></section>
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

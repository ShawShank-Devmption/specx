import type { Json, Row, Summary } from './types';

export const format = (value: unknown): string => value == null ? '—' : typeof value === 'number'
  ? Number.isInteger(value) ? String(value) : value.toFixed(4) : typeof value === 'object' ? JSON.stringify(value) : String(value);
export const percent = (value: number | null): string => value == null ? 'MISSING' : `${(value * 100).toFixed(1)}%`;

export function DataTable({ rows, empty = 'No recorded entries.' }: { rows: Row[]; empty?: string }) {
  if (!rows.length) return <p className="muted">{empty}</p>;
  const columns = [...new Set(rows.flatMap(Object.keys))];
  return <div className="table-scroll"><table><thead><tr>{columns.map(key => <th key={key} scope="col">{key.replaceAll('_', ' ')}</th>)}</tr></thead>
    <tbody>{rows.map((row, index) => <tr key={index}>{columns.map(key => <td key={key}>{format(row[key])}</td>)}</tr>)}</tbody></table></div>;
}

export function SuccessBar({ label, summary }: { label: string; summary: Summary }) {
  const rate = summary.success_rate, [low, high] = summary.success_rate_ci;
  if (rate === null || !summary.n) return <div className="bar-missing">{label}: MISSING (n=0)</div>;
  const x = (value: number) => 8 + value * 300;
  return <figure className="success-bar"><figcaption>{label} <span>{percent(rate)} · n={summary.n}</span></figcaption>
    <svg viewBox="0 0 316 34" role="img" aria-label={`${label}: success ${percent(rate)}, 95% CI ${percent(low)} to ${percent(high)}, n=${summary.n}`}>
      <rect x="8" y="8" width="300" height="18" rx="3" className="track" />
      <rect x="8" y="8" width={rate * 300} height="18" rx="3" className="bar" />
      {low !== null && high !== null && <g className="whisker"><line x1={x(low)} x2={x(high)} y1="17" y2="17" /><line x1={x(low)} x2={x(low)} y1="4" y2="30" /><line x1={x(high)} x2={x(high)} y1="4" y2="30" /></g>}
    </svg></figure>;
}

export function metricRows(value: Json, path = ''): Row[] {
  if (value === null) return [];
  if (Array.isArray(value)) return value.length ? value.flatMap((item, index) => metricRows(item, `${path}[${index}]`)) : [{ metric: path, value: '[]' }];
  if (typeof value === 'object') return Object.entries(value).flatMap(([key, item]) => metricRows(item, path ? `${path}.${key}` : key));
  return [{ metric: path, value }];
}

export function SafetyCard({ title, data }: { title: string; data: Json }) {
  return <article className="safety-card"><h3>{title}</h3><DataTable rows={metricRows(data)} empty="MISSING: safety metrics have not been produced." /></article>;
}

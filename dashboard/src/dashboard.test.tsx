import assert from 'node:assert/strict';
import React from 'react';
import test from 'node:test';
import { renderToStaticMarkup } from 'react-dom/server';
import { Dashboard } from './App';
import { DataTable, SuccessBar } from './tables';
import { parseNumbers } from './types';
import type { Summary } from './types';

const summary: Summary = { n: 10, success_rate: 0.6, success_rate_ci: [0.3, 0.9], mean_steps: 3,
  mean_tokens: 20, policy_violation_rate: 0, unapproved_calls: 0, quarantined_tool_calls: 0 };

test('success bars expose n and CI with actual SVG whiskers', () => {
  const html = renderToStaticMarkup(<SuccessBar label="shop / verified" summary={summary} />);
  assert.match(html, /n=10/);
  assert.match(html, /95% CI 30.0% to 90.0%/);
  assert.equal((html.match(/<line /g) || []).length, 3);
});
test('missing samples never become zero-percent success bars', () => {
  const html = renderToStaticMarkup(<SuccessBar label="shop" summary={{ ...summary, n: 0, success_rate: null }} />);
  assert.match(html, /MISSING/);
  assert.doesNotMatch(html, /<svg/);
});
test('tables escape untrusted evidence', () => {
  const html = renderToStaticMarkup(<DataTable rows={[{ reason: '<script>alert(1)</script>' }]} />);
  assert.doesNotMatch(html, /<script>/);
  assert.match(html, /&lt;script&gt;/);
});
test('dashboard renders all four panels and explicit incomplete/test-double warning', () => {
  const data = parseNumbers({ schema_version: 1, generated_at: 'test', git_sha: 'abc123', complete: false,
    execution: 'test_double', models: {}, missing: ['MISSING: s6/metrics.json'], warnings: [],
    notes: ['optimised == verified'], t1_generation: [], t2_verification: [],
    t3_s6: null, t4_s1: null, t5_s2: null, t6_f2: null,
    t7_readiness: { conditions: { verified: { shop: summary } }, comparisons: [] }, quarantine: [], revisions: [] });
  const html = renderToStaticMarkup(<Dashboard data={data} />);
  for (const panel of ['readiness', 'quarantine', 'revisions', 'safety']) assert.match(html, new RegExp(`id="${panel}"`));
  assert.match(html, /Not a completed live result/);
  assert.match(html, /optimised == verified/);
  assert.match(html, /missing verification is not evidence of safety/);
});
test('invalid numbers.json fails clearly', () => {
  assert.throws(() => parseNumbers({ schema_version: 42 }), /malformed/);
  assert.throws(() => parseNumbers(null), /Invalid/);
});

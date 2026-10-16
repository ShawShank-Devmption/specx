#!/usr/bin/env node
// Narrated live demo of SpecX (no API key needed). Needs `make apps` + `make sandbox` running and a
// completed pipeline in results/. Run from the repo root:  node platform/scripts/live-demo.mjs
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const R = (...p) => path.join(ROOT, "results", ...p);
const SANDBOX = process.env.SPECX_SANDBOX_URL ?? "http://127.0.0.1:4000";
const B = (s) => `\x1b[1m${s}\x1b[0m`;
const G = (s) => `\x1b[32m${s}\x1b[0m`;
const RED = (s) => `\x1b[31m${s}\x1b[0m`;
const DIM = (s) => `\x1b[2m${s}\x1b[0m`;
const act = (n, title) => console.log(`\n${B(`━━ ${n}. ${title}`)}\n`);
const json = (f) => JSON.parse(fs.readFileSync(f, "utf8"));
const jsonl = (f) => (fs.existsSync(f) ? fs.readFileSync(f, "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l)) : []);
const short = (v, n = 96) => { const s = typeof v === "string" ? v : JSON.stringify(v); return s.length > n ? `${s.slice(0, n)}…` : s; };

async function api(method, p, body) {
  const res = await fetch(SANDBOX + p, { method, headers: body ? { "content-type": "application/json" } : {}, body: body ? JSON.stringify(body) : undefined });
  const data = await res.json();
  if (!res.ok) throw new Error(`${method} ${p}: ${data.error?.message ?? res.status}`);
  return data;
}
const verdictLine = (v) => {
  const bad = v.violations.filter((x) => x.category !== "precondition");
  return bad.length ? RED(`✗ ${v.status}: ${bad.map((x) => `${x.category} — ${x.signature.split("|").slice(1).join(" | ")}`).join("; ")}`) : G(`✓ ${v.status}`);
};

// ─────────────────────────────────────────────────────────────── 1
act(1, "What SpecX built from the two websites");
const verdicts = ["f1", "s1", "s1_random", "s1_coverage"].flatMap((s) => jsonl(R("verdicts", `${s}.jsonl`)));
for (const app of ["shop", "admin"]) {
  const tools = json(R("tools", `${app}.tools.json`));
  const contracts = json(R("contracts", `${app}.contracts.json`));
  const clauses = contracts.reduce((n, c) => n + c.preconditions.length + c.postconditions.length + c.invariants.length, 0);
  console.log(`${B(app)}: ${tools.length} atomic tools, ${clauses} executable contract clauses, evidence from code, DOM, ARIA and network`);
  for (const t of tools) {
    const reasons = [...new Set(verdicts.filter((v) => v.tool_id === t.tool_id).flatMap((v) => v.violations.filter((x) => x.category !== "precondition").map((x) => `${x.category}: ${x.clause_id}`)))];
    const mark = t.status === "verified" ? G("verified   ") : RED("quarantined");
    console.log(`  ${mark}  ${t.name.padEnd(16)} ${DIM(t.risk_level.padEnd(7))} ${reasons.length ? RED(reasons.slice(0, 2).join(", ")) : ""}`);
  }
}

// ─────────────────────────────────────────────────────────────── 2
act(2, "A Claude agent connects over MCP and works with the verified tools only");
async function mcp(app) {
  const transport = new StdioClientTransport({
    command: path.join(ROOT, "platform/node_modules/.bin/tsx"),
    args: [path.join(ROOT, "platform/src/mcp/server.ts"), "--app", app, "--observe", "300"],
    env: { ...process.env, SPECX_LOG: "silent" },
  });
  const client = new Client({ name: "live-demo-agent", version: "1" });
  await client.connect(transport);
  return client;
}
async function call(client, name, args) {
  const res = await client.callTool({ name, arguments: args });
  const [out, check] = res.content;
  const label = `${name}(${short(args, 60)})`;
  if (res.isError && !check) console.log(`  ${RED("✗")} ${label}\n      ${RED(out.text)}`);
  else console.log(`  ${res.isError ? RED("✗") : G("→")} ${label}\n      ${DIM(short(out.text))}\n      ${check?.text.startsWith("SpecX contract check: pass") ? G(check.text) : RED(check?.text ?? "")}`);
  try { return JSON.parse(out.text); } catch { return null; }
}

const shop = await mcp("shop");
console.log(`${B("specx-shop")} offers: ${(await shop.listTools()).tools.map((t) => t.name).join(", ")}`);
const products = await call(shop, "list_products", {});
const cheapest = [...products.items].sort((a, b) => a.price_cents - b.price_cents)[0];
await call(shop, "get_product", { id: cheapest.id });
await call(shop, "view_cart", {});
console.log(DIM("  The agent now tries the actions that failed verification:"));
await call(shop, "add_to_cart", { product_id: cheapest.id, qty: 1 });
await call(shop, "place_order", { confirm: true });
await shop.close();

const admin = await mcp("admin");
console.log(`\n${B("specx-admin")} offers: ${(await admin.listTools()).tools.map((t) => t.name).join(", ")}`);
const dana = await call(admin, "create_user", { username: "dana", email: "dana@example.com", role: "viewer" });
await call(admin, "update_user", { id: dana.id, username: "dana", email: "dana@corp.example" });
await call(admin, "deactivate_user", { id: dana.id });
console.log(DIM("  The agent now tries the actions that failed verification:"));
await call(admin, "set_role", { id: dana.id, role: "editor" });
await call(admin, "delete_user", { id: dana.id });
await admin.close();

// ─────────────────────────────────────────────────────────────── 3
act(3, "Why those tools were withheld: each defect reproduced live in the sandbox");
async function session(app) {
  const s = await api("POST", "/sessions", { app });
  await api("PUT", `/sessions/${s.session_id}/tools`, { tools: json(R("tools", `${app}.tools.json`)), contracts: json(R("contracts", `${app}.contracts.json`)) });
  return s.session_id;
}
const inv = (id, tool, args, observe = 400) => api("POST", `/sessions/${id}/invoke`, { tool_id: tool, args, source: "fixture", post_observe_ms: observe });
let s = await session("shop");
await inv(s, "shop.add_to_cart", { product_id: 2, qty: 1 });
const race = await api("POST", `/sessions/${s}/invoke_concurrent`, { calls: [{ tool_id: "shop.place_order", args: { confirm: true } }, { tool_id: "shop.place_order", args: { confirm: true } }], source: "fixture", post_observe_ms: 400 });
console.log(`  ${B("Checkout race")}  two place_order calls at once → orders inserted: ${race.verdicts[0].effect_diff.db.orders?.inserted}\n      ${verdictLine(race.verdicts[0])}`);
await api("POST", `/sessions/${s}/reset`, {});
const stock = await inv(s, "shop.add_to_cart", { product_id: 5, qty: 10 });
console.log(`  ${B("Stock boundary")} add_to_cart(White Chair, qty 10) with 2 in stock\n      ${verdictLine(stock)}`);
await api("POST", `/sessions/${s}/reset`, {});
await api("POST", `/sessions/${s}/inject_leak`, { kind: "delayed_post", delay_ms: 500 });
const leak = await inv(s, "shop.add_to_cart", { product_id: 1, qty: 1 }, 1200);
const late = leak.effect_diff.network.find((n) => !n.approved && n.phase === "post");
console.log(`  ${B("Slow leak")}     analytics beacon ${late ? `${late.method} ${new URL(late.url).pathname} fired after the tool returned (phase: post)` : ""}\n      ${verdictLine(leak)}`);
await api("DELETE", `/sessions/${s}`);
s = await session("admin");
const del = await inv(s, "admin.delete_user", { id: 6 });
console.log(`  ${B("Hidden cascade")} delete_user(ivy) also deleted ${del.effect_diff.db.notes?.deleted ?? 0} notes via a legacy DB trigger\n      ${verdictLine(del)}`);
const role = await inv(s, "admin.set_role", { id: 3, role: "editor" });
console.log(`  ${B("Missing audit")}  set_role(carol, editor) changed the role but wrote no audit row\n      ${verdictLine(role)}`);
await api("DELETE", `/sessions/${s}`);

// ─────────────────────────────────────────────────────────────── 4
act(4, "Learned safety layers (from this run's results)");
const s6 = fs.existsSync(R("s6", "metrics.json")) ? json(R("s6", "metrics.json")) : null;
if (s6) {
  console.log(`  ${B("S6 anomaly detection")} trained on ${s6.n_train} clean runs`);
  for (const [k, v] of Object.entries(s6.per_kind)) console.log(`      ${k.padEnd(18)} caught ${Math.round(v.det_both * 100)}%  (contracts alone: ${Math.round((s6.contract_only_detection?.[k] ?? 0) * 100)}%)`);
  console.log(`      false alarms on clean runs: LSTM ${Math.round(s6.benign.fpr_lstm * 100)}%, isolation forest ${Math.round(s6.benign.fpr_if * 100)}%`);
}
const s1 = fs.existsSync(R("s1", "metrics.json")) ? json(R("s1", "metrics.json")) : null;
if (s1?.by_app_method) {
  console.log(`  ${B("S1 adversarial fuzzing")} unique violations per 1,000 calls`);
  for (const [app, methods] of Object.entries(s1.by_app_method)) console.log(`      ${app.padEnd(6)} ${Object.entries(methods).map(([m, v]) => `${m} ${v.unique_signatures_per_1000.mean}`).join("   ")}`);
}
const s2 = fs.existsSync(R("s2", "metrics.json")) ? json(R("s2", "metrics.json")) : null;
if (s2) console.log(`  ${B("S2 graph risk model")} path-risk AUC: GCN ${s2.path.gcn.auc.toFixed(2)}, MLP baseline ${s2.path.mlp.auc.toFixed(2)}; dependency edges recovered that name-matching missed: ${(s2.recovered_edges ?? []).length}`);

act(5, "Dashboard");
console.log(`  http://127.0.0.1:5173  ${DIM("(readiness, quarantine list, revision log, safety ML)")}\n`);

import { describe, expect, it } from "vitest";
import { buildGraph, nameMatchEdges, orderEdges, stateEdges, valueFlowEdges } from "../src/graph/build.js";
import type { Clause, ToolContract, ToolDefinition, Verdict } from "../src/contracts/types.js";
import { validate } from "../src/contracts/validate.js";

const obj = (props: Record<string, unknown>) => ({ type: "object", properties: props });
function tool(name: string, inputs: string[], output?: Record<string, unknown>, risk: ToolDefinition["risk_level"] = "read"): ToolDefinition {
  return {
    tool_id: `shop.${name}`,
    app: "shop",
    name,
    description: "a tool for tests",
    input_schema: { type: "object", properties: Object.fromEntries(inputs.map((i) => [i, { type: "integer" }])), required: inputs, additionalProperties: false },
    ...(output ? { output_schema: output } : {}),
    handler: { kind: "api", code: "async () => null" },
    risk_level: risk,
    atomic: true,
    provenance: [{ surface: "code", ref: "x:1" }],
    version: 1,
    metadata_revision: 0,
    status: "verified",
  };
}
const tools = [
  tool("list_products", [], obj({ items: { type: "array", items: obj({ id: { type: "integer" }, name: { type: "string" } }) } })),
  tool("get_product", ["id"], obj({ id: { type: "integer" }, name: { type: "string" } })),
  tool("view_cart", [], obj({ items: { type: "array", items: obj({ product_id: { type: "integer" } }) } })),
  tool("add_to_cart", ["product_id", "qty"], obj({ cart_item_id: { type: "integer" } }), "write"),
  tool("remove_from_cart", ["product_id"], undefined, "delete"),
  tool("place_order", [], obj({ order_id: { type: "integer" } }), "payment"),
];
const c = (id: string, kind: Clause["kind"], params: Record<string, unknown>): Clause => ({ clause_id: id, surface: "db", kind, params, description: "", severity: "high" });
const contracts: ToolContract[] = tools.map((t) => ({ tool_id: t.tool_id, preconditions: [], postconditions: [c("post_one_call", "network_calls", {})], invariants: [] }));
const contractOf = (id: string) => contracts.find((k) => k.tool_id === `shop.${id}`) as ToolContract;
contractOf("add_to_cart").postconditions.push(c("post_db_cart_items", "db_delta", { table: "cart_items", inserted: 1 }), c("post_frame_orders", "db_delta", { table: "orders", inserted: 0, updated: 0, deleted: 0 }));
contractOf("place_order").preconditions.push(c("pre_exists_cart_items", "db_row_exists", { table: "cart_items", where: { user_id: "$user.id" } }));
contractOf("place_order").postconditions.push(c("post_db_orders", "db_delta", { table: "orders", inserted: 1 }));
contractOf("place_order").invariants.push(c("inv_at_most_once", "at_most_once", { table: "orders" }));

let n = 0;
function run(toolName: string, args: Record<string, unknown>, output: unknown, prefix: string[], session = "s1", violations: Verdict["violations"] = []): Verdict {
  n++;
  return {
    run_id: `${session}_r${n}`,
    session_id: session,
    app: "shop",
    tool_id: `shop.${toolName}`,
    args,
    mode: "single",
    sequence_prefix: prefix.map((p) => `shop.${p}`),
    started_at: new Date(Date.UTC(2026, 9, 15, 0, 0, n)).toISOString(),
    duration_ms: 1,
    status: violations.length ? "fail" : "pass",
    output,
    clause_results: [],
    effect_diff: { db: {}, network: [], dom: { mutations: 0, added_selectors: [], removed_selectors: [] }, storage: [], audit: [] },
    violations,
    anomaly: null,
    source: "s1",
  };
}
const verdicts = [
  run("get_product", { id: 3 }, { id: 3, name: "Green Pen" }, []),
  run("add_to_cart", { product_id: 3, qty: 1 }, { cart_item_id: 1 }, ["get_product"]),
  run("place_order", {}, { order_id: 1 }, ["get_product", "add_to_cart"], "s1", [{ clause_id: "inv_at_most_once", severity: "high", signature: "x", category: "race" }]),
  run("list_products", {}, { items: [{ id: 5, name: "White Chair" }] }, []),
  run("add_to_cart", { product_id: 4, qty: 1 }, { cart_item_id: 2 }, ["list_products"]),
];

describe("valueFlowEdges", () => {
  it("links an id a tool returned to a later call's argument in the same reset epoch", () => {
    expect(valueFlowEdges(verdicts)).toEqual([{ src: "shop.get_product", dst: "shop.add_to_cart", type: "data", field: "product_id", evidence: "trace", confidence: 1, label: true }]);
  });
  it("does not link values across reset epochs", () => {
    expect(valueFlowEdges([run("get_product", { id: 2 }, { id: 2 }, [], "s2"), run("add_to_cart", { product_id: 2, qty: 1 }, {}, [], "s2")])).toEqual([]);
  });
});

describe("nameMatchEdges", () => {
  it("links output fields to same-named inputs and misses differently named ones", () => {
    const edges = nameMatchEdges(tools).map((e) => `${e.src}>${e.dst}:${e.field}`);
    expect(edges).toContain("shop.view_cart>shop.remove_from_cart:product_id");
    expect(edges).toContain("shop.view_cart>shop.add_to_cart:product_id");
    expect(edges).not.toContain("shop.get_product>shop.add_to_cart:product_id");
  });
});

describe("stateEdges and orderEdges", () => {
  it("links producers of a table to tools that require rows in it", () => {
    expect(stateEdges(contracts)).toEqual([{ src: "shop.add_to_cart", dst: "shop.place_order", type: "state", field: "cart_items", evidence: "contract", confidence: 0.9, label: true }]);
  });
  it("links consecutive calls seen in traces", () => {
    const edges = orderEdges(verdicts).map((e) => `${e.src}>${e.dst}`);
    expect(edges).toEqual(["shop.get_product>shop.add_to_cart", "shop.add_to_cart>shop.place_order", "shop.list_products>shop.add_to_cart"]);
  });
});

describe("buildGraph", () => {
  it("builds a schema-valid typed graph with node state, violation rates and invariants", () => {
    const g = validate("workflow_graph", buildGraph("shop", tools, contracts, verdicts)) as ReturnType<typeof buildGraph>;
    const node = (id: string) => g.nodes.find((x) => x.id === `shop.${id}`);
    expect(node("list_products")?.output_fields).toEqual(["items.id", "items.name"]);
    expect(node("add_to_cart")).toMatchObject({ state_writes: ["cart_items"], input_fields: ["product_id", "qty"] });
    expect(node("place_order")).toMatchObject({ state_reads: ["cart_items"], violation_rate: 1 });
    expect(g.invariants).toContainEqual({ id: "inv_requires_shop_place_order_shop_add_to_cart", kind: "requires", tools: ["shop.add_to_cart", "shop.place_order"], description: "shop.place_order needs cart_items rows that shop.add_to_cart creates" });
    expect(g.invariants.filter((i) => i.tools[0] === "shop.place_order").map((i) => i.kind)).toEqual(["at_most_once", "never_concurrent"]);
  });

  it("dedupes edges, keeping the highest confidence and a true label over unknown", () => {
    const g = buildGraph("shop", tools, contracts, verdicts);
    const dup = g.edges.filter((e) => e.src === "shop.view_cart" && e.dst === "shop.remove_from_cart" && e.type === "data");
    expect(dup).toHaveLength(1);
  });
});

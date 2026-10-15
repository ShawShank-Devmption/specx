import fs from "node:fs";
import path from "node:path";
import { Ajv2020 } from "ajv/dist/2020.js";
import { describe, expect, it } from "vitest";
import { exampleArgs } from "../src/contracts/args.js";
import type { ToolContract, ToolDefinition } from "../src/contracts/types.js";
import { REPO_ROOT } from "../src/paths.js";
import { db } from "./helpers/ctx.js";

const tools = JSON.parse(fs.readFileSync(path.join(REPO_ROOT, "fixtures/tools/shop.tools.json"), "utf8")) as ToolDefinition[];
const contracts = JSON.parse(fs.readFileSync(path.join(REPO_ROOT, "fixtures/contracts/shop.contracts.json"), "utf8")) as ToolContract[];
const tool = (id: string) => tools.find((t) => t.tool_id === id)!;
const contract = (id: string) => contracts.find((c) => c.tool_id === id) ?? { tool_id: id, preconditions: [], postconditions: [], invariants: [] };

const state = db({
  products: [1, 2, 3, 4, 5].map((id) => ({ id, stock: 10 })),
  users: [{ id: 1, username: "alice" }],
  cart_items: [],
});

const removeTool: ToolDefinition = {
  ...tool("shop.add_to_cart"),
  tool_id: "shop.remove_from_cart",
  name: "remove_from_cart",
  input_schema: { type: "object", properties: { product_id: { type: "integer" } }, required: ["product_id"], additionalProperties: false },
};
const removeContract: ToolContract = {
  tool_id: "shop.remove_from_cart",
  preconditions: [
    { clause_id: "pre_exists_cart_items", surface: "db", kind: "db_row_exists", params: { table: "cart_items", where: { user_id: "$user.id", product_id: "$args.product_id" } }, description: "", severity: "high" },
  ],
  postconditions: [],
  invariants: [],
};

describe("exampleArgs", () => {
  it("produces args that validate against every fixture tool's input schema", () => {
    const ajv = new Ajv2020({ strict: false });
    for (const t of tools) {
      const { args } = exampleArgs(t, contract(t.tool_id), state, { id: 1 });
      expect(ajv.validate(t.input_schema, args), `${t.tool_id}: ${ajv.errorsText()}`).toBe(true);
    }
  });

  it("takes ids from precondition rows, defaulting to the last row", () => {
    expect(exampleArgs(tool("shop.add_to_cart"), contract("shop.add_to_cart"), state, { id: 1 }).args).toEqual({ product_id: 5, qty: 1 });
  });

  it("picks a seeded-random row when a seed is given, deterministically", () => {
    const picks = [1, 2, 3, 4, 5, 6, 7, 8].map((seed) => exampleArgs(tool("shop.add_to_cart"), contract("shop.add_to_cart"), state, { id: 1 }, { seed }).args.product_id);
    expect(new Set(picks).size).toBeGreaterThan(1);
    expect(exampleArgs(tool("shop.add_to_cart"), contract("shop.add_to_cart"), state, { id: 1 }, { seed: 3 }).args.product_id).toBe(picks[2]);
  });

  it("reports preconditions no current row satisfies", () => {
    const r = exampleArgs(removeTool, removeContract, state, { id: 1 });
    expect(r.unsatisfied).toEqual(["pre_exists_cart_items"]);
  });

  it("scopes $user rows to the logged-in user", () => {
    const withCart = db({ ...Object.fromEntries(Object.entries(state).map(([k, v]) => [k, v.rows])), cart_items: [{ id: 1, user_id: 2, product_id: 4 }, { id: 2, user_id: 1, product_id: 3 }] });
    expect(exampleArgs(removeTool, removeContract, withCart, { id: 1 }).args).toEqual({ product_id: 3 });
  });
});

import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import type { AppManifest } from "../src/contracts/types.js";
import { buildCandidates } from "../src/generator/candidates.js";
import { llmNamer, type NamerClient } from "../src/generator/llm.js";
import { parseRoutes } from "../src/generator/repo.js";
import { manifestPath, SEED_APPS_DIR } from "../src/paths.js";

const manifest = JSON.parse(fs.readFileSync(manifestPath("shop"), "utf8")) as AppManifest;
const { candidates } = buildCandidates(parseRoutes(path.join(SEED_APPS_DIR, "shop", "server.js")), [], [], manifest);
const addToCart = candidates.find((c) => c.route.method === "POST" && c.route.path === "/api/cart")!;

function fake(reply: { stop_reason: string; parsed_output: unknown }): NamerClient & { calls: unknown[] } {
  const calls: unknown[] = [];
  return { calls, messages: { parse: async (p: unknown) => (calls.push(p), reply) } };
}

describe("llmNamer", () => {
  it("uses the model's structured naming", async () => {
    const client = fake({ stop_reason: "end_turn", parsed_output: { name: "add_to_cart", description: "Add a quantity of one product to the cart.", param_descriptions: [{ param: "qty", description: "Units to add" }] } });
    const n = await llmNamer(client, "claude-opus-5-5")(addToCart);
    expect(n).toMatchObject({ name: "add_to_cart", description: "Add a quantity of one product to the cart." });
    expect(n.paramDescriptions.qty).toBe("Units to add");
    expect(n.paramDescriptions.product_id).toMatch(/id of the product/);
    expect(client.calls[0]).toMatchObject({ model: "claude-opus-5-5", output_config: { effort: "high" } });
  });

  it("falls back to the template namer on refusal or an invalid name", async () => {
    expect((await llmNamer(fake({ stop_reason: "refusal", parsed_output: null }), "m")(addToCart)).name).toBe("create_cart");
    expect((await llmNamer(fake({ stop_reason: "end_turn", parsed_output: { name: "Add To Cart!", description: "x", param_descriptions: [] } }), "m")(addToCart)).name).toBe("create_cart");
  });
});

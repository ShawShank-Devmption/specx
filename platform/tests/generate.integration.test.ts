import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { chromium, type Browser } from "playwright";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import type { AppManifest } from "../src/contracts/types.js";
import { validate } from "../src/contracts/validate.js";
import { templateNamer } from "../src/generator/emit.js";
import { generate, type GenerateResult } from "../src/generator/index.js";
import { manifestPath } from "../src/paths.js";
import { integration, withPort } from "./helpers/sandbox.js";
import { startSeedApp, type RunningApp } from "./helpers/seedapp.js";

describe.runIf(integration)("generate (integration)", () => {
  let browser: Browser;
  const running: RunningApp[] = [];
  const out: Record<string, GenerateResult> = {};

  beforeAll(async () => {
    process.env.SPECX_RESULTS_DIR = fs.mkdtempSync(path.join(os.tmpdir(), "specx-gen-"));
    browser = await chromium.launch();
    for (const app of ["shop", "admin"]) {
      const r = await startSeedApp(app);
      running.push(r);
      const manifest = withPort(JSON.parse(fs.readFileSync(manifestPath(app), "utf8")) as AppManifest, r.base);
      out[app] = await generate(manifest, browser, { namer: templateNamer });
    }
  }, 180_000);
  afterAll(async () => {
    await browser?.close();
    for (const r of running) await r.close();
  });

  it("generates the seven documented shop tools", () => {
    expect(out.shop?.tools.map((t) => t.name).sort()).toEqual(["add_to_cart", "get_product", "list_orders", "list_products", "place_order", "remove_from_cart", "view_cart"]);
  });

  it("generates the seven documented admin tools", () => {
    expect(out.admin?.tools.map((t) => t.name).sort()).toEqual(["create_user", "deactivate_user", "delete_user", "get_user", "list_users", "set_role", "update_user"]);
  });

  it("grounds every tool in at least two evidence surfaces and gives it a valid contract", () => {
    for (const r of Object.values(out)) {
      expect(r.contracts).toHaveLength(r.tools.length);
      for (const t of r.tools) {
        validate("tool_definition", t);
        expect(new Set(t.provenance.map((p) => p.surface)).size, t.tool_id).toBeGreaterThanOrEqual(2);
      }
      for (const c of r.contracts) {
        validate("contract", c);
        expect(c.postconditions.length).toBeGreaterThanOrEqual(1);
      }
    }
  });

  it("uses DOM bounds and enums from the crawl", () => {
    const qty = (out.shop?.tools.find((t) => t.name === "add_to_cart")?.input_schema.properties as Record<string, Record<string, unknown>>).qty;
    expect(qty).toMatchObject({ type: "integer", minimum: 1, maximum: 10 });
    const role = (out.admin?.tools.find((t) => t.name === "set_role")?.input_schema.properties as Record<string, Record<string, unknown>>).role;
    expect(role?.enum).toEqual(["viewer", "editor", "admin"]);
  });

  it("learns output shapes from observed responses, including get_product's bare id", () => {
    const props = out.shop?.tools.find((t) => t.name === "get_product")?.output_schema?.properties as Record<string, unknown>;
    expect(Object.keys(props)).toEqual(["id", "name", "price_cents", "stock"]);
  });

  it("captures response shapes even when the UI navigates right after the call", () => {
    const fields = (app: string, name: string) => Object.keys((out[app]?.tools.find((t) => t.name === name)?.output_schema?.properties ?? {}) as object);
    expect(fields("shop", "place_order")).toEqual(["order_id", "total_cents"]);
    expect(fields("admin", "create_user")).toContain("id");
    expect(fields("admin", "update_user")).toContain("username");
    expect(fields("admin", "delete_user")).toEqual(["id", "deleted"]);
  });

  it("rejects the unapproved analytics route", () => {
    expect(out.shop?.rejected).toContainEqual({ ref: "POST /api/analytics", reason: "route is not an approved endpoint in the app manifest" });
  });
});

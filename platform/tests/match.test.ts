import fs from "node:fs";
import { describe, expect, it } from "vitest";
import { matchEndpoint, patternMatches } from "../src/contracts/match.js";
import type { AppManifest } from "../src/contracts/types.js";
import { manifestPath } from "../src/paths.js";

const shop = JSON.parse(fs.readFileSync(manifestPath("shop"), "utf8")) as AppManifest;

describe("matchEndpoint (approved_path_matching)", () => {
  it("matches :param patterns ignoring query string and trailing slash", () => {
    expect(matchEndpoint(shop, "DELETE", "http://127.0.0.1:5101/api/cart/3?x=1")).toMatchObject({ approved: true, third_party: false, pattern: "/api/cart/:product_id", risk_level: "delete" });
    expect(matchEndpoint(shop, "GET", "http://127.0.0.1:5101/api/products/")).toMatchObject({ approved: true, path: "/api/products" });
  });

  it("flags first-party endpoints missing from the manifest as unapproved", () => {
    expect(matchEndpoint(shop, "POST", "http://127.0.0.1:5101/api/analytics", "fetch")).toMatchObject({ approved: false, third_party: false });
  });

  it("flags other hosts as third-party and never approved", () => {
    expect(matchEndpoint(shop, "GET", "https://tracker.example.invalid/p")).toMatchObject({ approved: false, third_party: true });
  });

  it("treats first-party page loads and assets as approved", () => {
    expect(matchEndpoint(shop, "GET", "http://127.0.0.1:5101/cart", "document").approved).toBe(true);
    expect(matchEndpoint(shop, "GET", "http://127.0.0.1:5101/app.js", "script").approved).toBe(true);
    expect(matchEndpoint(shop, "GET", "http://127.0.0.1:5101/cart", "fetch").approved).toBe(false);
  });

  it("does not let a param segment swallow slashes", () => {
    expect(patternMatches("/api/users/:id", "/api/users/3/role")).toBe(false);
    expect(patternMatches("/api/users/:id/role", "/api/users/3/role")).toBe(true);
  });
});

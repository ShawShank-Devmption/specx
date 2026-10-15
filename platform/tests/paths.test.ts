import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { REPO_ROOT, resultsDir, toolsPath, verdictsPath } from "../src/paths.js";

describe("paths", () => {
  const saved = process.env.SPECX_RESULTS_DIR;
  afterEach(() => {
    if (saved === undefined) delete process.env.SPECX_RESULTS_DIR;
    else process.env.SPECX_RESULTS_DIR = saved;
  });

  it("finds the repo root as the directory holding contracts/", () => {
    expect(path.basename(path.join(REPO_ROOT, "contracts"))).toBe("contracts");
    expect(REPO_ROOT.endsWith("platform")).toBe(false);
  });

  it("defaults results to <repo>/results and honours an absolute SPECX_RESULTS_DIR", () => {
    delete process.env.SPECX_RESULTS_DIR;
    expect(resultsDir()).toBe(path.join(REPO_ROOT, "results"));
    process.env.SPECX_RESULTS_DIR = "/tmp/specx-x";
    expect(toolsPath("shop")).toBe("/tmp/specx-x/tools/shop.tools.json");
    expect(verdictsPath("f1")).toBe("/tmp/specx-x/verdicts/f1.jsonl");
  });
});

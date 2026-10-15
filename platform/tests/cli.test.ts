import { describe, expect, it, vi } from "vitest";
import { main } from "../src/cli/main.js";

describe("specx cli", () => {
  it("prints usage for help and fails without a command", async () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => undefined);
    expect(await main(["help"])).toBe(0);
    expect(String(log.mock.calls[0]?.[0])).toContain("generate");
    expect(await main([])).toBe(1);
    log.mockRestore();
  });

  it("requires --app and rejects unknown commands", async () => {
    const err = vi.spyOn(console, "error").mockImplementation(() => undefined);
    await expect(main(["verify"])).rejects.toThrow("--app is required");
    expect(await main(["frobnicate", "--app", "shop"])).toBe(1);
    err.mockRestore();
  });

  it("fails clearly when an earlier stage has not run", async () => {
    process.env.SPECX_RESULTS_DIR = "/nonexistent-specx-results";
    await expect(main(["graph", "--app", "shop"])).rejects.toThrow(/missing .*shop\.tools\.json — run the earlier pipeline stage first/);
    delete process.env.SPECX_RESULTS_DIR;
  });
});

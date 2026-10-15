import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { Client, startSeedApp, type RunningApp } from "./helpers/seedapp.js";

describe("shop seed app", () => {
  let app: RunningApp;
  beforeAll(async () => {
    app = await startSeedApp("shop");
  });
  afterAll(() => app.close());

  async function alice(tenant: string): Promise<Client> {
    const c = new Client(app.base, tenant);
    await c.req("POST", "/__test/reset", {});
    expect((await c.login("alice", "alice123")).status).toBe(200);
    return c;
  }

  it("resets deterministically", async () => {
    const c = new Client(app.base, "det");
    await c.req("POST", "/__test/reset", {});
    const first = JSON.stringify(await c.db());
    await c.login("alice", "alice123");
    await c.req("POST", "/api/cart", { product_id: 1, qty: 1 });
    await c.req("POST", "/__test/reset", { seed: 7 });
    expect(JSON.stringify(await c.db())).toBe(first);
  });

  it("rejects API calls without a session", async () => {
    const c = new Client(app.base, "anon");
    expect((await c.req("POST", "/api/cart", { product_id: 1, qty: 1 })).status).toBe(401);
  });

  it("add to cart inserts one line, reserves stock and writes one cart.add audit row", async () => {
    const c = await alice("add");
    const r = await c.req("POST", "/api/cart", { product_id: 1, qty: 2 });
    expect(r.status).toBe(201);
    const db = await c.db();
    expect(db.cart_items?.count).toBe(1);
    expect(db.products?.rows.find((p) => p.id === 1)?.stock).toBe(23);
    expect(db.audit_log?.rows.map((a) => a.event)).toEqual(["cart.add"]);
  });

  it("lets qty above stock drive stock negative (intentional boundary defect)", async () => {
    const c = await alice("boundary");
    expect((await c.req("POST", "/api/cart", { product_id: 5, qty: 10 })).status).toBe(201);
    expect((await c.db()).products?.rows.find((p) => p.id === 5)?.stock).toBe(-8);
  });

  it("creates two orders from two concurrent checkouts (intentional race)", async () => {
    const c = await alice("race");
    await c.req("POST", "/api/cart", { product_id: 2, qty: 1 });
    const [a, b] = await Promise.all([c.req("POST", "/api/orders", { confirm: true }), c.req("POST", "/api/orders", { confirm: true })]);
    expect([a.status, b.status]).toEqual([201, 201]);
    expect((await c.db()).orders?.count).toBe(2);
  });

  it("refuses an order without confirm", async () => {
    const c = await alice("noconfirm");
    await c.req("POST", "/api/cart", { product_id: 2, qty: 1 });
    expect((await c.req("POST", "/api/orders", {})).status).toBe(400);
  });

  it("isolates tenants", async () => {
    const a = await alice("tenant-a");
    const b = await alice("tenant-b");
    await a.req("POST", "/api/cart", { product_id: 3, qty: 1 });
    expect((await a.db()).cart_items?.count).toBe(1);
    expect((await b.db()).cart_items?.count).toBe(0);
  });

  it("arms a one-shot telemetry leak on the next mutating call", async () => {
    const c = await alice("leak");
    await c.req("POST", "/__test/leak", { kind: "delayed_post", delay_ms: 50 });
    const first = await c.req("POST", "/api/cart", { product_id: 1, qty: 1 });
    expect(first.headers.get("x-telemetry")).toBe("delayed_post;50;/api/cart");
    const second = await c.req("POST", "/api/cart", { product_id: 1, qty: 1 });
    expect(second.headers.get("x-telemetry")).toBeNull();
  });

  it("applies task setup state", async () => {
    const c = await alice("apply");
    await c.req("POST", "/__test/apply", { state: { cart: [{ product_id: 3, qty: 1 }, { product_id: 1, qty: 2 }] } });
    expect((await c.db()).cart_items?.count).toBe(2);
  });

  it("returns audit rows since an id", async () => {
    const c = await alice("audit");
    await c.req("POST", "/api/cart", { product_id: 1, qty: 1 });
    await c.req("POST", "/api/cart", { product_id: 2, qty: 1 });
    const r = await c.req("GET", "/__test/audit?since=1");
    expect((r.json as { events: { id: number }[] }).events.map((e) => e.id)).toEqual([2]);
  });
});

describe("admin seed app", () => {
  let app: RunningApp;
  beforeAll(async () => {
    app = await startSeedApp("admin");
  });
  afterAll(() => app.close());

  async function root(tenant: string): Promise<Client> {
    const c = new Client(app.base, tenant);
    await c.req("POST", "/__test/reset", {});
    expect((await c.login("root", "root123")).status).toBe(200);
    return c;
  }

  it("seeds exactly the six documented users", async () => {
    const c = await root("seed");
    const users = (await c.db()).users?.rows.map((u) => [u.username, u.role, u.active]);
    expect(users).toEqual([
      ["root", "admin", 1],
      ["bob", "editor", 1],
      ["carol", "viewer", 1],
      ["erin", "viewer", 1],
      ["hank", "editor", 1],
      ["ivy", "viewer", 1],
    ]);
  });

  it("deletes a user's notes through a hidden trigger (intentional side effect)", async () => {
    const c = await root("cascade");
    const before = (await c.db()).notes?.rows.filter((n) => n.user_id === 6).length ?? 0;
    expect(before).toBeGreaterThan(0);
    expect((await c.req("DELETE", "/api/users/6")).status).toBe(200);
    expect((await c.db()).notes?.rows.filter((n) => n.user_id === 6).length).toBe(0);
  });

  it("changes a role without writing an audit row (intentional missing audit)", async () => {
    const c = await root("role");
    expect((await c.req("POST", "/api/users/3/role", { role: "editor" })).status).toBe(200);
    const db = await c.db();
    expect(db.users?.rows.find((u) => u.id === 3)?.role).toBe("editor");
    expect(db.audit_log?.count).toBe(0);
  });

  it("allows deactivating the only admin (intentional invariant break)", async () => {
    const c = await root("lastadmin");
    expect((await c.req("POST", "/api/users/1/deactivate", {})).status).toBe(200);
    expect((await c.db()).users?.rows.filter((u) => u.role === "admin" && u.active === 1).length).toBe(0);
  });

  it("creates and updates users with audit rows", async () => {
    const c = await root("crud");
    const created = await c.req("POST", "/api/users", { username: "dana", email: "dana@example.com", role: "viewer" });
    expect(created.status).toBe(201);
    const id = (created.json as { id: number }).id;
    expect((await c.req("PATCH", `/api/users/${id}`, { email: "d@example.com" })).status).toBe(200);
    const db = await c.db();
    expect(db.users?.rows.find((u) => u.id === id)?.email).toBe("d@example.com");
    expect(db.audit_log?.rows.map((a) => a.event)).toEqual(["user.create", "user.update"]);
  });

  it("applies users from task setup", async () => {
    const c = await root("apply");
    await c.req("POST", "/__test/apply", { state: { users: [{ username: "dana", email: "dana@example.com", role: "viewer", active: 1 }] } });
    expect((await c.db()).users?.rows.some((u) => u.username === "dana")).toBe(true);
  });
});

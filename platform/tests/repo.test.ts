import path from "node:path";
import { describe, expect, it } from "vitest";
import { parseRoutes, parseSql } from "../src/generator/repo.js";
import { SEED_APPS_DIR } from "../src/paths.js";

const shop = parseRoutes(path.join(SEED_APPS_DIR, "shop", "server.js"));
const admin = parseRoutes(path.join(SEED_APPS_DIR, "admin", "server.js"));
const route = (rs: typeof shop, method: string, p: string) => rs.find((r) => r.method === method && r.path === p);

describe("parseSql", () => {
  it("parses inserts with column lists", () => {
    expect(parseSql("INSERT INTO cart_items (user_id, product_id, qty) VALUES (?, ?, ?)")).toMatchObject({ op: "INSERT", table: "cart_items", insertCols: ["user_id", "product_id", "qty"], insertSelect: false });
  });
  it("parses INSERT ... SELECT with an aliased WHERE", () => {
    expect(parseSql("INSERT INTO order_items (order_id, product_id) SELECT ?, c.product_id FROM cart_items c JOIN products p ON p.id = c.product_id WHERE c.user_id = ?")).toMatchObject({
      op: "INSERT",
      table: "order_items",
      insertSelect: true,
      sourceTable: "cart_items",
      whereCols: ["user_id"],
    });
  });
  it("parses update and delete WHERE columns, ignoring literal comparisons", () => {
    expect(parseSql("UPDATE users SET role = ? WHERE id = ?")).toMatchObject({ op: "UPDATE", table: "users", whereCols: ["id"] });
    expect(parseSql("DELETE FROM cart_items WHERE user_id = ? AND product_id = ?")).toMatchObject({ op: "DELETE", table: "cart_items", whereCols: ["user_id", "product_id"] });
    expect(parseSql("SELECT * FROM users WHERE role = 'admin' AND id = ?")).toMatchObject({ op: "SELECT", table: "users", whereCols: ["id"] });
  });
});

describe("parseRoutes", () => {
  it("finds every route of the shop with its source line", () => {
    const api = shop.filter((r) => r.path.startsWith("/api/")).map((r) => `${r.method} ${r.path}`);
    expect(api).toEqual([
      "GET /api/products",
      "GET /api/products/:id",
      "GET /api/cart",
      "POST /api/cart",
      "DELETE /api/cart/:product_id",
      "POST /api/orders",
      "GET /api/orders",
      "POST /api/analytics",
    ]);
    expect(route(shop, "POST", "/api/cart")?.snippet).toContain('app.post("/api/cart"');
    expect(route(shop, "POST", "/api/cart")?.line).toBeGreaterThan(1);
  });

  it("extracts body fields, path params, tables and the audit event", () => {
    expect(route(shop, "POST", "/api/cart")).toMatchObject({ bodyFields: ["product_id", "qty"], pathParams: [], tablesWritten: ["cart_items", "products"], auditEvent: "cart.add" });
    expect(route(shop, "DELETE", "/api/cart/:product_id")).toMatchObject({ pathParams: ["product_id"], tablesWritten: ["cart_items", "products"] });
    expect(route(shop, "POST", "/api/orders")).toMatchObject({ bodyFields: ["confirm"], tablesWritten: ["orders", "order_items", "cart_items"] });
  });

  it("records how each statement is executed", () => {
    const get = route(shop, "GET", "/api/products/:id");
    expect(get?.statements[0]).toMatchObject({ op: "SELECT", table: "products", whereCols: ["id"], exec: "get" });
  });

  it("sees what the route code says and nothing more (the admin cascade lives in a trigger)", () => {
    expect(route(admin, "DELETE", "/api/users/:id")?.tablesWritten).toEqual(["users"]);
    expect(route(admin, "POST", "/api/users/:id/role")?.auditEvent).toBeNull();
    expect(route(admin, "PATCH", "/api/users/:id")?.bodyFields).toEqual(["username", "email"]);
  });
});

// Seed app "shop" (e-commerce). Intentional defects, kept on purpose for S1/F1 to find:
//  - POST /api/orders has no transaction or idempotency guard: concurrent checkouts create two orders.
//  - POST /api/cart never checks qty against stock, so stock can go negative.
//  - POST /api/analytics is not an approved endpoint; only the telemetry script calls it, in leak mode.
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { buildApp } from "../_lib/app.js";
import { escapeHtml } from "../_lib/core.js";

const APP_DIR = path.dirname(fileURLToPath(import.meta.url));
const money = (cents) => `$${(cents / 100).toFixed(2)}`;
const authorisePayment = () => new Promise((resolve) => setTimeout(resolve, 40)); // simulated gateway latency

function cartLines(db, userId) {
  return db
    .prepare(
      "SELECT c.id AS cart_item_id, c.product_id, p.name, c.qty, p.price_cents FROM cart_items c JOIN products p ON p.id = c.product_id WHERE c.user_id = ? ORDER BY c.id",
    )
    .all(userId)
    .map((r) => ({ ...r }));
}
const cartTotal = (lines) => lines.reduce((sum, l) => sum + l.qty * l.price_cents, 0);

function applyState(db, state) {
  for (const { product_id, qty } of state.cart ?? []) {
    db.prepare("INSERT INTO cart_items (user_id, product_id, qty) VALUES (1, ?, ?)").run(product_id, qty);
    db.prepare("UPDATE products SET stock = stock - ? WHERE id = ?").run(qty, product_id);
  }
}

function routes(app, { requireAuth, audit, page }) {
  // ---------------------------------------------------------------- pages
  app.get("/products", requireAuth, (req, res) => {
    const rows = req.db.prepare("SELECT * FROM products ORDER BY id").all();
    const list = rows
      .map((p) => `<li><a href="/products/${p.id}" data-testid="product-link-${p.id}">${escapeHtml(p.name)}</a> — ${money(p.price_cents)}</li>`)
      .join("");
    res.send(page({ title: "Products", user: req.user.username, body: `<ul aria-label="Products">${list}</ul>` }));
  });

  app.get("/products/:id", requireAuth, (req, res) => {
    const p = req.db.prepare("SELECT * FROM products WHERE id = ?").get(req.params.id);
    if (!p) return res.status(404).send(page({ title: "Not found", user: req.user.username, body: "" }));
    res.send(
      page({
        title: p.name,
        user: req.user.username,
        body: `<p data-testid="price">${money(p.price_cents)}</p><p data-testid="stock">In stock: ${p.stock}</p>
<label for="qty">Quantity</label> <input id="qty" name="qty" data-testid="qty" type="number" min="1" max="10" value="1">
<button data-testid="add-to-cart" aria-label="Add to cart" data-product-id="${p.id}">Add to cart</button>`,
      }),
    );
  });

  app.get("/cart", requireAuth, (req, res) => {
    const lines = cartLines(req.db, req.user.id);
    const rows = lines
      .map(
        (l) => `<tr><td>${escapeHtml(l.name)}</td><td>${l.qty}</td><td>${money(l.qty * l.price_cents)}</td>
<td><button data-testid="remove-from-cart" aria-label="Remove from cart" data-product-id="${l.product_id}">Remove from cart</button></td></tr>`,
      )
      .join("");
    const body = lines.length
      ? `<table aria-label="Cart"><tr><th>Product</th><th>Qty</th><th>Subtotal</th><th></th></tr>${rows}</table>
<p data-testid="cart-total">Total: ${money(cartTotal(lines))}</p>
<p>Ship to: ${escapeHtml(req.user.address)}</p>
<button data-testid="checkout" aria-label="Place order">Place order</button>`
      : `<p data-testid="cart-empty">Your cart is empty.</p>`;
    res.send(page({ title: "Cart", user: req.user.username, body }));
  });

  app.get("/orders", requireAuth, (req, res) => {
    const rows = req.db.prepare("SELECT * FROM orders WHERE user_id = ? ORDER BY id").all(req.user.id);
    const list = rows.map((o) => `<li data-testid="order-${o.id}">Order #${o.id} — ${money(o.total_cents)} — ${o.status}</li>`).join("");
    res.send(page({ title: "Orders", user: req.user.username, body: rows.length ? `<ul aria-label="Orders">${list}</ul>` : "<p>No orders yet.</p>" }));
  });

  // ---------------------------------------------------------------- API
  app.get("/api/products", requireAuth, (req, res) => {
    res.json(req.db.prepare("SELECT id, name, price_cents, stock FROM products ORDER BY id").all());
  });

  app.get("/api/products/:id", requireAuth, (req, res) => {
    const product = req.db.prepare("SELECT id, name, price_cents, stock FROM products WHERE id = ?").get(req.params.id);
    if (!product) return res.status(404).json({ error: "product not found" });
    res.json(product);
  });

  app.get("/api/cart", requireAuth, (req, res) => {
    const lines = cartLines(req.db, req.user.id);
    res.json({ items: lines, total_cents: cartTotal(lines) });
  });

  app.post("/api/cart", requireAuth, (req, res) => {
    const { product_id, qty } = req.body;
    if (!Number.isInteger(qty) || qty < 1) return res.status(400).json({ error: "qty must be a positive integer" });
    const product = req.db.prepare("SELECT id, stock FROM products WHERE id = ?").get(product_id);
    if (!product) return res.status(404).json({ error: "product not found" });
    const line = req.db.prepare("INSERT INTO cart_items (user_id, product_id, qty) VALUES (?, ?, ?)").run(req.user.id, product.id, qty);
    req.db.prepare("UPDATE products SET stock = stock - ? WHERE id = ?").run(qty, product.id);
    audit(req.db, "cart.add", req.user.username, "cart_items", line.lastInsertRowid);
    res.status(201).json({ cart_item_id: Number(line.lastInsertRowid), cart_total_cents: cartTotal(cartLines(req.db, req.user.id)) });
  });

  app.delete("/api/cart/:product_id", requireAuth, (req, res) => {
    const reserved = req.db.prepare("SELECT SUM(qty) AS qty FROM cart_items WHERE user_id = ? AND product_id = ?").get(req.user.id, req.params.product_id);
    if (!reserved.qty) return res.status(404).json({ error: "product not in cart" });
    req.db.prepare("DELETE FROM cart_items WHERE user_id = ? AND product_id = ?").run(req.user.id, req.params.product_id);
    req.db.prepare("UPDATE products SET stock = stock + ? WHERE id = ?").run(reserved.qty, req.params.product_id);
    audit(req.db, "cart.remove", req.user.username, "cart_items", req.params.product_id);
    res.json({ removed_qty: reserved.qty, cart_total_cents: cartTotal(cartLines(req.db, req.user.id)) });
  });

  app.post("/api/orders", requireAuth, async (req, res) => {
    if (req.body.confirm !== true) return res.status(400).json({ error: "confirm must be true" });
    const db = req.db;
    const items = db.prepare("SELECT product_id, qty FROM cart_items WHERE user_id = ?").all(req.user.id);
    if (items.length === 0) return res.status(400).json({ error: "cart is empty" });
    const total = cartTotal(cartLines(db, req.user.id));
    await authorisePayment(total);
    const order = db
      .prepare("INSERT INTO orders (user_id, total_cents, status, created_at) VALUES (?, ?, 'placed', ?)")
      .run(req.user.id, total, new Date().toISOString());
    db.prepare(
      "INSERT INTO order_items (order_id, product_id, qty, price_cents) SELECT ?, c.product_id, c.qty, p.price_cents FROM cart_items c JOIN products p ON p.id = c.product_id WHERE c.user_id = ?",
    ).run(order.lastInsertRowid, req.user.id);
    db.prepare("DELETE FROM cart_items WHERE user_id = ?").run(req.user.id);
    audit(db, "order.place", req.user.username, "orders", order.lastInsertRowid);
    res.status(201).json({ order_id: Number(order.lastInsertRowid), total_cents: total });
  });

  app.get("/api/orders", requireAuth, (req, res) => {
    res.json(req.db.prepare("SELECT id, total_cents, status, created_at FROM orders WHERE user_id = ? ORDER BY id").all(req.user.id));
  });

  app.post("/api/analytics", (_req, res) => res.status(204).end());
}

export function createApp() {
  return buildApp({
    appDir: APP_DIR,
    cookieName: "shop_sid",
    tables: ["products", "users", "cart_items", "orders", "order_items", "audit_log"],
    pollPath: "/api/cart",
    home: "/products",
    nav: [
      ["/products", "Products"],
      ["/cart", "Cart"],
      ["/orders", "Orders"],
    ],
    applyState,
    routes,
  });
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) {
  const port = Number(process.env.PORT ?? 5101);
  createApp().listen(port, "127.0.0.1", () => console.log(`shop listening on http://127.0.0.1:${port}`));
}

// Seed app "admin" (user administration). Intentional defects, kept on purpose for F1/S1 to find:
//  - Deleting a user also deletes their notes through a legacy SQLite trigger (see schema.sql).
//  - Deactivating, demoting or deleting the only admin is allowed (breaks inv_active_admin).
//  - POST /api/users/:id/role writes no audit row.
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { buildApp } from "../_lib/app.js";
import { escapeHtml } from "../_lib/core.js";

const APP_DIR = path.dirname(fileURLToPath(import.meta.url));
const ROLES = ["viewer", "editor", "admin"];
const publicUser = (u) => ({ id: u.id, username: u.username, email: u.email, role: u.role, active: u.active });

function applyState(db, state) {
  for (const u of state.users ?? []) {
    db.prepare("INSERT INTO users (username, email, role, active) VALUES (?, ?, ?, ?)").run(u.username, u.email, u.role ?? "viewer", u.active ?? 1);
  }
}

function routes(app, { requireAuth, audit, page }) {
  // ---------------------------------------------------------------- pages
  app.get("/users", requireAuth, (req, res) => {
    const rows = req.db.prepare("SELECT * FROM users ORDER BY id").all();
    const trs = rows
      .map(
        (u) =>
          `<tr><td><a href="/users/${u.id}" data-testid="user-link-${u.id}">${escapeHtml(u.username)}</a></td><td>${escapeHtml(u.email)}</td><td>${u.role}</td><td>${u.active ? "active" : "inactive"}</td></tr>`,
      )
      .join("");
    res.send(
      page({
        title: "Users",
        user: req.user.username,
        body: `<p><a href="/users/new" data-testid="new-user-link">New user</a></p>
<table aria-label="Users"><tr><th>Username</th><th>Email</th><th>Role</th><th>Status</th></tr>${trs}</table>`,
      }),
    );
  });

  app.get("/users/new", requireAuth, (req, res) => {
    const options = ROLES.map((r) => `<option value="${r}">${r}</option>`).join("");
    res.send(
      page({
        title: "New user",
        user: req.user.username,
        body: `<label for="new-username">Username</label> <input id="new-username" name="username" data-testid="new-username"><br>
<label for="new-email">Email</label> <input id="new-email" name="email" type="email" data-testid="new-email"><br>
<label for="new-role">Role</label> <select id="new-role" name="role" data-testid="new-role">${options}</select><br>
<button data-testid="create-user" aria-label="Create user">Create user</button>`,
      }),
    );
  });

  app.get("/users/:id", requireAuth, (req, res) => {
    const u = req.db.prepare("SELECT * FROM users WHERE id = ?").get(req.params.id);
    if (!u) return res.status(404).send(page({ title: "Not found", user: req.user.username, body: "" }));
    const options = ROLES.map((r) => `<option value="${r}"${r === u.role ? " selected" : ""}>${r}</option>`).join("");
    res.send(
      page({
        title: `User ${u.username}`,
        user: req.user.username,
        body: `<p data-testid="user-status">${u.role} · ${u.active ? "active" : "inactive"}</p>
<label for="edit-username">Username</label> <input id="edit-username" name="username" data-testid="edit-username" value="${escapeHtml(u.username)}"><br>
<label for="edit-email">Email</label> <input id="edit-email" name="email" type="email" data-testid="edit-email" value="${escapeHtml(u.email)}"><br>
<button data-testid="update-user" aria-label="Update user" data-user-id="${u.id}">Update user</button>
<hr><label for="role">Role</label> <select id="role" name="role" data-testid="role">${options}</select>
<button data-testid="set-role" aria-label="Set role" data-user-id="${u.id}">Set role</button>
<hr><button data-testid="deactivate-user" aria-label="Deactivate user" data-user-id="${u.id}">Deactivate user</button>
<button data-testid="delete-user" aria-label="Delete user" data-user-id="${u.id}">Delete user</button>`,
      }),
    );
  });

  // ---------------------------------------------------------------- API
  app.get("/api/users", requireAuth, (req, res) => {
    res.json(req.db.prepare("SELECT id, username, email, role, active FROM users ORDER BY id").all());
  });

  app.get("/api/users/:id", requireAuth, (req, res) => {
    const user = req.db.prepare("SELECT id, username, email, role, active FROM users WHERE id = ?").get(req.params.id);
    if (!user) return res.status(404).json({ error: "user not found" });
    res.json(user);
  });

  app.post("/api/users", requireAuth, (req, res) => {
    const { username, email, role } = req.body;
    if (!username || !email || !ROLES.includes(role)) return res.status(400).json({ error: "username, email and a valid role are required" });
    const created = req.db.prepare("INSERT INTO users (username, email, role, active) VALUES (?, ?, ?, 1)").run(username, email, role);
    audit(req.db, "user.create", req.user.username, "users", created.lastInsertRowid);
    res.status(201).json(publicUser(req.db.prepare("SELECT * FROM users WHERE id = ?").get(created.lastInsertRowid)));
  });

  app.patch("/api/users/:id", requireAuth, (req, res) => {
    const { username, email } = req.body;
    const result = req.db
      .prepare("UPDATE users SET username = COALESCE(?, username), email = COALESCE(?, email) WHERE id = ?")
      .run(username ?? null, email ?? null, req.params.id);
    if (result.changes === 0) return res.status(404).json({ error: "user not found" });
    audit(req.db, "user.update", req.user.username, "users", req.params.id);
    res.json(publicUser(req.db.prepare("SELECT * FROM users WHERE id = ?").get(req.params.id)));
  });

  app.post("/api/users/:id/role", requireAuth, (req, res) => {
    const { role } = req.body;
    if (!ROLES.includes(role)) return res.status(400).json({ error: "invalid role" });
    const result = req.db.prepare("UPDATE users SET role = ? WHERE id = ?").run(role, req.params.id);
    if (result.changes === 0) return res.status(404).json({ error: "user not found" });
    res.json({ id: Number(req.params.id), role });
  });

  app.post("/api/users/:id/deactivate", requireAuth, (req, res) => {
    const result = req.db.prepare("UPDATE users SET active = 0 WHERE id = ?").run(req.params.id);
    if (result.changes === 0) return res.status(404).json({ error: "user not found" });
    audit(req.db, "user.deactivate", req.user.username, "users", req.params.id);
    res.json({ id: Number(req.params.id), active: 0 });
  });

  app.delete("/api/users/:id", requireAuth, (req, res) => {
    const result = req.db.prepare("DELETE FROM users WHERE id = ?").run(req.params.id);
    if (result.changes === 0) return res.status(404).json({ error: "user not found" });
    audit(req.db, "user.delete", req.user.username, "users", req.params.id);
    res.json({ id: Number(req.params.id), deleted: true });
  });
}

export function createApp() {
  return buildApp({
    appDir: APP_DIR,
    cookieName: "admin_sid",
    tables: ["users", "notes", "audit_log"],
    pollPath: "/api/users",
    home: "/users",
    nav: [
      ["/users", "Users"],
      ["/users/new", "New user"],
    ],
    applyState,
    routes,
  });
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) {
  const port = Number(process.env.PORT ?? 5102);
  createApp().listen(port, "127.0.0.1", () => console.log(`admin listening on http://127.0.0.1:${port}`));
}

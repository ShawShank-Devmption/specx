// Express app factory shared by seed apps: JSON body, sessions, tenancy, leak middleware, static assets, hooks.
import path from "node:path";
import { fileURLToPath } from "node:url";
import express from "express";
import { audit, createAuth, createTenantStore, jsonErrors, tenantOf } from "./core.js";
import { page } from "./layout.js";
import { createLeakState, testHooks } from "./testhooks.js";

const LIB_PUBLIC = path.join(path.dirname(fileURLToPath(import.meta.url)), "public");

/**
 * @param {object} o
 * @param {string} o.appDir directory holding schema.sql, seed.sql, public/
 * @param {string} o.cookieName session cookie name
 * @param {string[]} o.tables tables exposed by /__test/db
 * @param {string} o.pollPath path the background_poll leak hits
 * @param {string} o.home page to land on after login
 * @param {[string, string][]} o.nav header links
 * @param {(db, state) => void} o.applyState task setup applier
 * @param {(app, h) => void} o.routes registers the app's pages and API routes
 */
export function buildApp({ appDir, cookieName, tables, pollPath, home, nav, applyState, routes }) {
  const store = createTenantStore(appDir);
  const auth = createAuth(cookieName);
  const leaks = createLeakState(pollPath);
  const app = express();
  app.disable("x-powered-by");
  app.use(express.json());
  app.use(express.static(LIB_PUBLIC));
  app.use(express.static(path.join(appDir, "public")));
  app.use((req, _res, next) => {
    req.db = store.get(tenantOf(req));
    const username = auth.usernameOf(req);
    req.user = username ? (req.db.prepare("SELECT * FROM users WHERE username = ?").get(username) ?? null) : null;
    next();
  });
  app.use(leaks.middleware);
  app.use(testHooks({ store, tables, leaks, applyState }));

  const requireAuth = (req, res, next) => {
    if (req.user) return next();
    if (req.path.startsWith("/api/")) return res.status(401).json({ error: "login required" });
    res.redirect("/login");
  };

  app.post("/api/login", (req, res) => {
    const { username, password } = req.body ?? {};
    const user = req.db.prepare("SELECT * FROM users WHERE username = ? AND password = ?").get(username, password);
    if (!user) return res.status(401).json({ error: "bad credentials" });
    auth.login(res, username);
    res.json({ ok: true, home });
  });
  app.get("/login", (_req, res) =>
    res.send(
      page({
        title: "Log in",
        nav: [],
        user: null,
        body: `<form data-testid="login-form" aria-label="Log in">
<label for="username">Username</label> <input id="username" name="username" data-testid="username" autocomplete="username"><br>
<label for="password">Password</label> <input id="password" name="password" type="password" data-testid="password" autocomplete="current-password"><br>
<button type="submit" data-testid="login" aria-label="Log in">Log in</button></form>`,
      }),
    ),
  );
  app.get("/logout", (req, res) => {
    auth.logout(req, res);
    res.redirect("/login");
  });
  app.get("/", (req, res) => res.redirect(req.user ? home : "/login"));

  routes(app, { requireAuth, audit, page: (o) => page({ nav, ...o }) });
  app.use(jsonErrors);
  return app;
}

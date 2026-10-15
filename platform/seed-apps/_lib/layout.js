// Minimal server-rendered page shell shared by the seed apps.
import { escapeHtml } from "./core.js";

export function page({ title, nav, user, body }) {
  const links = nav.map(([href, label]) => `<a href="${href}">${escapeHtml(label)}</a>`).join(" · ");
  const menu = user
    ? `<span data-testid="user-menu" aria-label="Signed in as ${escapeHtml(user)}">${escapeHtml(user)} · <a href="/logout">Log out</a></span>`
    : "";
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>${escapeHtml(title)}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="/style.css"></head>
<body><header><nav aria-label="Main">${links}</nav>${menu}</header>
<main><h1>${escapeHtml(title)}</h1>${body}<p role="status" data-testid="status" aria-live="polite"></p></main>
<script src="/telemetry.js"></script><script src="/app.js"></script></body></html>`;
}

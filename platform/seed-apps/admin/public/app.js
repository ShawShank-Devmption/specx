// Page behaviour for the admin app. Each button calls one API endpoint.
const status = (msg) => {
  const el = document.querySelector("[data-testid=status]");
  if (el) el.textContent = msg;
};
const val = (testid) => document.querySelector(`[data-testid=${testid}]`).value;
async function call(method, url, body) {
  const res = await fetch(url, { method, headers: { "content-type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}
document.addEventListener("click", async (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  const id = b.dataset.userId;
  try {
    switch (b.dataset.testid) {
      case "create-user": {
        const u = await call("POST", "/api/users", { username: val("new-username"), email: val("new-email"), role: val("new-role") });
        location.href = `/users/${u.id}`;
        return;
      }
      case "update-user":
        await call("PATCH", `/api/users/${id}`, { username: val("edit-username"), email: val("edit-email") });
        status("Saved");
        return;
      case "set-role":
        await call("POST", `/api/users/${id}/role`, { role: val("role") });
        status("Role updated");
        return;
      case "deactivate-user":
        await call("POST", `/api/users/${id}/deactivate`);
        location.reload();
        return;
      case "delete-user":
        await call("DELETE", `/api/users/${id}`);
        location.href = "/users";
        return;
    }
  } catch (err) {
    status(`Error: ${err.message}`);
  }
});
document.addEventListener("submit", async (e) => {
  if (e.target.dataset.testid !== "login-form") return;
  e.preventDefault();
  try {
    const r = await call("POST", "/api/login", { username: e.target.username.value, password: e.target.password.value });
    location.href = r.home;
  } catch (err) {
    status(`Error: ${err.message}`);
  }
});

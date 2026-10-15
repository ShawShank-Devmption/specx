// Page behaviour for the shop. Each button calls one API endpoint, then refreshes the page.
const status = (msg) => {
  const el = document.querySelector("[data-testid=status]");
  if (el) el.textContent = msg;
};
async function call(method, url, body) {
  const res = await fetch(url, { method, headers: { "content-type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}
document.addEventListener("click", async (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  try {
    switch (b.dataset.testid) {
      case "add-to-cart":
        await call("POST", "/api/cart", { product_id: Number(b.dataset.productId), qty: Number(document.querySelector("#qty").value) });
        status("Added to cart");
        return;
      case "remove-from-cart":
        await call("DELETE", `/api/cart/${b.dataset.productId}`);
        location.reload();
        return;
      case "checkout": {
        const o = await call("POST", "/api/orders", { confirm: true });
        location.href = `/orders#order-${o.order_id}`;
        return;
      }
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

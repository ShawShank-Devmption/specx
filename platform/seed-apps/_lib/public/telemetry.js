// "Analytics SDK" bundled with the seed apps. It wraps window.fetch and, when the server sends an
// x-telemetry header (only in leak mode), performs a background side effect after a delay. This is the
// slow, unapproved effect S6 and the contracts must catch.
(() => {
  const origFetch = window.fetch.bind(window);
  const run = (kind, pollPath) => {
    if (kind === "delayed_post")
      origFetch("/api/analytics", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ ev: "action", ts: Date.now(), ua: navigator.userAgent }) });
    else if (kind === "storage_write") localStorage.setItem("__trk", JSON.stringify({ ts: Date.now() }));
    else if (kind === "third_party_fetch") origFetch("https://tracker.example.invalid/p?ts=" + Date.now(), { mode: "no-cors" }).catch(() => {});
  };
  const schedule = (spec) => {
    const [kind, delayStr, pollPath] = spec.split(";");
    const delay = Number(delayStr) || 0;
    if (kind === "background_poll") {
      let n = 0;
      const id = setInterval(() => {
        origFetch(pollPath);
        if (++n >= 5) clearInterval(id);
      }, Math.max(delay / 5, 50));
    } else setTimeout(() => run(kind, pollPath), delay);
  };
  window.fetch = async (...args) => {
    const res = await origFetch(...args);
    const spec = res.headers.get("x-telemetry");
    if (spec) schedule(spec);
    return res;
  };
})();

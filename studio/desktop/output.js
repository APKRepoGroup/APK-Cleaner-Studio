(() => {
  "use strict";
  const button = document.querySelector("#revealSavedOutput");
  const download = document.querySelector("#downloadButton");
  if (!button || !download) return;
  let revision = 0, opening = false;

  function currentJob() {
    const url = new URL(download.href, location.href);
    return url.origin === location.origin && /^\/api\/jobs\/([a-f0-9]{32})\/download$/.exec(url.pathname)?.[1] || null;
  }

  async function refresh() {
    const request = ++revision, job = currentJob(), api = globalThis.pywebview?.api;
    button.classList.toggle("hidden", !job || !api?.saved_output_exists);
    button.disabled = true;
    if (!job || !api?.saved_output_exists || opening) return;
    try {
      const saved = await api.saved_output_exists(job);
      if (request === revision && currentJob() === job) button.disabled = saved !== true;
    } catch { /* Keep unavailable when the native window is closing. */ }
  }

  button.addEventListener("click", async () => {
    const job = currentJob(), api = globalThis.pywebview?.api;
    if (!job || button.disabled || opening || !api?.reveal_saved_output) return;
    opening = true; button.disabled = true;
    try {
      const result = await api.reveal_saved_output(job);
      if (currentJob() === job && !result?.opened) toast(result?.error || "APK'nın bulunduğu klasör açılamadı.");
    } catch {
      if (currentJob() === job) toast("APK'nın bulunduğu klasör açılamadı.");
    } finally {
      opening = false; void refresh();
    }
  });
  new MutationObserver(refresh).observe(download, { attributes: true, attributeFilter: ["href"] });
  globalThis.addEventListener("pywebviewready", refresh);
  globalThis.chrome?.webview?.addEventListener("message", event => {
    if (event.data?.type === "apk-cleaner-output-saved" && event.data.job === currentJob()) void refresh();
  });
  void refresh();
})();

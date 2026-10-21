(() => {
  "use strict";
  const choices = document.querySelector("#desktopNotificationChoices");
  if (!choices) return;
  const status = document.querySelector("#desktopNotificationStatus");
  let saved = null;
  function render(mode) {
    for (const radio of choices.querySelectorAll("input")) radio.checked = radio.value === mode;
  }
  async function request(mode) {
    choices.disabled = true;
    try {
      const response = await fetch("/api/desktop/preferences", mode === undefined
        ? { cache: "no-store" }
        : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ notifications: mode }) });
      const value = await response.json();
      if (!response.ok || !["all", "errors", "off"].includes(value.notifications)) throw new Error();
      saved = value.notifications;
      render(saved);
      status.textContent = saved === "off" ? "Windows işlem bildirimleri kapalı." : "Tercihiniz bu bilgisayarda saklanır. Windows bildirim ayarları da geçerlidir.";
      status.dataset.error = "false";
    } catch {
      render(saved);
      status.textContent = "Bildirim tercihi kaydedilemedi. Yeniden deneyin.";
      status.dataset.error = "true";
    } finally {
      choices.disabled = false;
    }
  }
  choices.addEventListener("change", (event) => {
    if (event.target.matches('input[name="desktopNotifications"]')) request(event.target.value);
  });
  request();
})();

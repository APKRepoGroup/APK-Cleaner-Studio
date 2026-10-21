(() => {
  "use strict";
  const button = document.querySelector("#desktopNetworkToggle");
  if (!button) return;
  const status = document.querySelector("#desktopNetworkStatus");
  let enabled = false;
  function render(state) {
    enabled = state.enabled === true;
    document.documentElement.dataset.lanEnabled = String(enabled);
    document.querySelector("#desktopNetworkAddresses").hidden = !enabled;
    document.querySelector("#desktopNetworkUrl").value = state.url || "";
    document.querySelector("#desktopNetworkSecureUrl").value = state.secure_url || "";
    document.querySelector("#desktopNetworkCode").value = state.pairing_code || "";
    button.textContent = enabled ? "Yerel ağ erişimini kapat" : "Yerel ağ erişimini aç";
    button.setAttribute("aria-pressed", String(enabled));
    status.textContent = enabled
      ? "Erişim açık. Kod, erişim kapatılıp yeniden açıldığında yenilenir. Bağlanılamıyorsa Windows güvenlik duvarındaki özel ağ iznini kontrol edin."
      : "Erişim kapalı. Uygulama yalnızca bu bilgisayarda kullanılabilir.";
    status.dataset.error = "false";
  }
  async function request(body) {
    button.disabled = true;
    try {
      const response = await fetch("/api/desktop/network", body === undefined
        ? { cache: "no-store" }
        : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const state = await response.json();
      if (!response.ok) throw new Error(state.error || "Yerel ağ ayarı değiştirilemedi.");
      render(state);
    } catch (error) {
      status.textContent = error instanceof TypeError ? "Uygulamaya ulaşılamadı. Yeniden deneyin." : error.message;
      status.dataset.error = "true";
      button.textContent = enabled ? "Yerel ağ erişimini kapat" : "Yerel ağ erişimini aç";
    } finally {
      button.disabled = false;
    }
  }
  button.addEventListener("click", async () => {
    button.disabled = true;
    try {
      const approved = await confirmAction(enabled ? "Yerel ağ erişimi kapatılsın mı?" : "Yerel ağ erişimi açılsın mı?",
        enabled ? "Bağlı cihazların erişimi kesilir. Başlatılmış işlemler bilgisayarda devam eder."
          : "Aynı ağdaki cihazlar eşleştirme koduyla bağlanabilir. HTTP trafiği şifreli değildir; yalnızca güvendiğiniz özel ağlarda etkinleştirin.",
        enabled ? "Erişimi kapat" : "Erişimi aç");
      if (approved) await request({ enabled: !enabled });
    } finally {
      button.disabled = false;
    }
  });
  document.querySelectorAll(".desktop-network-addresses input").forEach((input) => {
    input.addEventListener("click", () => input.select());
  });
  request();
})();

/* Layout adapter for prototype v2 only. The original processing UI owns state. */
(() => {
  "use strict";
  if (document.documentElement.dataset.desktopWorkspace !== "true") return;
  const find = selector => document.querySelector(selector);
  const definitions = [
    ["work", "Çalışma alanı", "Paketini seç, işlemini yapılandır ve sonucu al.", "M4 7h16v13H4z M8 7V4h8v3"],
    ["history", "İşlem geçmişi", "Önceki işlemlerine, raporlarına ve çıktılarına ulaş.", "M4 11a8 8 0 1 1 2 7 M4 4v7h7 M12 8v5l3 2"],
    ["storage", "Depolama", "Yerel işlem dosyalarını ve kullanılan alanı yönet.", "M4 5h16v14H4z M4 14h16 M16 17h1"],
    ["settings", "Motor ve ayarlar", "İşlem bileşenlerinin durumunu kontrol et.", "M5 7h14 M5 17h14 M9 4v6 M15 14v6"],
    ["about", "Hakkında", "APK Cleaner Studio ve katkıda bulunanlar.", "M12 11v6 M12 7h.01 M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0"],
  ];
  const shell = document.createElement("div");
  shell.className = "desktop-shell";
  shell.innerHTML = `<aside class="desktop-rail"><div class="desktop-brand"></div>
    <small class="desktop-nav-label">ÇALIŞMA ALANI</small><nav class="desktop-nav" aria-label="Uygulama bölümleri"></nav>
    <div class="desktop-rail-bottom"><span class="desktop-prototype-tag">AYRI PROTOTİP · 02</span>
    <p>Mevcut uygulamanız değiştirilmez.</p><div class="desktop-connection"></div></div></aside>
    <div class="desktop-main"><header class="desktop-toolbar"><div><small>APK CLEANER STUDIO</small>
    <h1 id="desktopPageTitle"></h1></div><div class="desktop-toolbar-actions"></div></header>
    <div class="desktop-scroll auto-hide-scrollbar" tabindex="-1"><p id="desktopPageDescription" class="desktop-description"></p>
    <div class="desktop-pages"></div></div><footer class="desktop-statusbar"><span>Yerel işlem · Dosyalar bu cihazda kalır</span>
    <span id="desktopStage">Paket bekleniyor</span></footer></div>`;
  const nav = shell.querySelector(".desktop-nav");
  const pages = new Map();
  for (const [id, title, , path] of definitions) {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.desktopPage = id;
    button.innerHTML = `<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="${path}"/></svg><span>${title}</span>`;
    nav.append(button);
    const page = document.createElement("section");
    page.className = "desktop-page";
    page.id = `desktop-${id}`;
    page.setAttribute("aria-label", title);
    button.setAttribute("aria-controls", page.id);
    pages.set(id, page);
    shell.querySelector(".desktop-pages").append(page);
  }
  document.body.append(shell);
  shell.querySelector(".desktop-brand").append(find(".brand"));
  shell.querySelector(".desktop-connection").append(find("#connection"));
  shell.querySelector(".desktop-toolbar-actions").append(find(".top-actions"));
  const workspace = find(".workspace");
  pages.get("work").append(workspace);
  pages.get("history").append(find("#historyCard"));
  pages.get("storage").append(find("#storageCard"));
  pages.get("settings").append(find("#toolCard"));
  pages.get("about").append(find("#specialThanks"));
  const info = document.createElement("section");
  info.className = "desktop-info-card";
  info.innerHTML = `<small>MASAÜSTÜ DÜZEN DENEMESİ</small><h2>Tanıdık motor, yeni çalışma alanı</h2>
    <p>Bu pencere ayrı veri ve işlem geçmişi kullanır. Mevcut Windows uygulaması ve ilk pencere prototipi korunur.</p>
    <p>Güncelleme ve bileşen indirme bu denemede kapalıdır. Geri dönmek için pencereyi kapatıp önceki sürümü açabilirsiniz.</p>`;
  pages.get("settings").append(info);
  // Keep old nodes and IDs for app.js, but remove website-only presentation.
  find("#toolCertificate").hidden = true;
  find("#clientCard").hidden = true;
  find(".privacy").hidden = true;
  const railBrand = shell.querySelector(".brand");
  railBrand.setAttribute("aria-label", "Çalışma alanına dön");
  const scroller = shell.querySelector(".desktop-scroll");
  const positions = new Map();
  let current = "";
  function showPage(id, focus = false) {
    if (!pages.has(id)) return;
    if (current === id) return;
    positions.set(current, scroller.scrollTop);
    current = id;
    for (const [key, page] of pages) page.hidden = key !== id;
    nav.querySelectorAll("button").forEach(button => {
      if (button.dataset.desktopPage === id) button.setAttribute("aria-current", "page");
      else button.removeAttribute("aria-current");
    });
    const definition = definitions.find(item => item[0] === id);
    find("#desktopPageTitle").textContent = definition[1];
    find("#desktopPageDescription").textContent = definition[2];
    scroller.scrollTop = positions.get(id) || 0;
    if (id === "storage") {
      // Existing disclosure listener loads actual storage data; no second API.
      const storage = find("#storageCard");
      if (!storage.open) storage.querySelector("summary").click();
    }
    if (focus) scroller.focus({ preventScroll: true });
  }
  nav.addEventListener("click", event => {
    const button = event.target.closest("[data-desktop-page]");
    if (button) showPage(button.dataset.desktopPage, true);
  });
  railBrand.addEventListener("click", event => {
    event.preventDefault(); // Never reload/reset a running job.
    showPage("work", true);
  });
  document.addEventListener("click", event => {
    if (event.target.closest("#toolsButton")) showPage("settings");
    if (event.target.closest("#storagePreflightManage")) showPage("storage");
  }, true);
  const stageLabels = { select: "Paket bekleniyor", analysis: "Paket yapılandırılıyor", working: "İşlem devam ediyor", result: "Çıktı hazır" };
  function syncStage(returnToWork = false) {
    const stage = workspace.dataset.stage || "select";
    find("#desktopStage").textContent = stageLabels[stage] || "Yerel işlem";
    if (returnToWork) showPage("work");
  }
  new MutationObserver(() => syncStage(true)).observe(workspace, { attributes: true, attributeFilter: ["data-stage"] });
  showPage("work");
  syncStage();
  document.documentElement.classList.add("desktop-workspace-ready");
})();

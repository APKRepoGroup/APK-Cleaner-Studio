const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const state = {
  file: null, profile: "balanced", operation: "patch", patchAdsSelected: true, jobId: null, analysis: null, toolchain: null,
  splitSelection: { abis: [], languages: [] },
  messageTargets: [], messageCandidates: [],
  displayedProgress: 0, targetProgress: 0, progressFrame: 0, progressLastTick: 0,
  pollInFlight: false, jobRunning: false, statusInFlight: false,
  installedApps: [], installedAppsLoading: false, installedAppsReady: false, selectedInstalledPackage: "", installedSharePackage: "",
  outputUrl: "", outputFilename: "", nativeInstallBusy: false, nativeShareBusy: false, nativeSplitInstallBusy: false,
  splitInstallPlan: null, splitInstallRequestJobId: null, splitInstallSubmitted: false,
  update: null, updateBusy: false, updateCheckInFlight: false, updateCheckOnResume: false, dismissedUpdateVersion: ""
};
const MAX_UPLOAD_BYTES = 1024 ** 3;
const PACKAGE_EXTENSIONS = [".apk", ".apks", ".apkm", ".xapk"];
const SPLIT_EXTENSIONS = [".apks", ".apkm", ".xapk"];
const THEME_KEY = "apk-cleaner-theme";
const CLIENT_ID_KEY = "apk-cleaner-client-id";
const CLIENT_COOKIE_NAME = "apk_cleaner_client_id";
const SAVED_PRESETS_KEY = "apk-cleaner-processing-presets-v1";
const ACTION_NEXT_ICON = '<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12h15m-6-6 6 6-6 6"/></svg>';
function setJobRunning(active) {
  state.jobRunning = Boolean(active);
  if (document.documentElement.dataset.embedded !== "android") return;
  try { globalThis.AndroidThemeBridge?.setProcessingActive?.(state.jobRunning); } catch {}
}
const httpFallback = document.getElementById("httpFallback");
if (httpFallback) {
  httpFallback.href = `http://${location.host}${location.pathname}${location.search}${location.hash}`;
  httpFallback.hidden = location.protocol === "http:";
}
function clientCookieValue() {
  const prefix = `${CLIENT_COOKIE_NAME}=`;
  const entry = document.cookie.split(";").map((part) => part.trim()).find((part) => part.startsWith(prefix));
  return entry ? entry.slice(prefix.length) : "";
}
const clientId = (() => {
  let saved = "";
  try {
    saved = localStorage.getItem(CLIENT_ID_KEY) || "";
  } catch {}
  const selected = StudioUI.selectClientId(clientCookieValue(), saved, () =>
    globalThis.crypto?.randomUUID?.() || `client-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
  );
  // HTTP and HTTPS have separate localStorage areas, while the host cookie is
  // shared. Mirroring the shared identity prevents one PC from appearing twice
  // during the trusted local HTTP -> HTTPS hand-off.
  try { localStorage.setItem(CLIENT_ID_KEY, selected); } catch {}
  return selected;
})();
document.cookie = `${CLIENT_COOKIE_NAME}=${clientId}; Path=/; Max-Age=31536000; SameSite=Strict${location.protocol === "https:" ? "; Secure" : ""}`;
const themeMedia = matchMedia("(prefers-color-scheme: dark)");
const motionMedia = matchMedia("(prefers-reduced-motion: reduce)");
const desktopPointer = matchMedia("(hover: hover) and (pointer: fine)");
const desktopThanks = matchMedia("(min-width: 721px)");
const supporterDisclosure = $(".supporter-disclosure");
let supporterDisclosureInitialized = false;
function syncSupporterDisclosure() {
  if (!supporterDisclosure) return;
  // Keep an expanded list open when a desktop window becomes narrow. Closing
  // it during resize removes page height and makes the browser jump upward.
  if (desktopThanks.matches) {
    if (supporterDisclosureInitialized) setInlineDisclosureOpen(supporterDisclosure, true);
    else supporterDisclosure.open = true;
  }
  else if (!supporterDisclosureInitialized) supporterDisclosure.open = false;
  supporterDisclosureInitialized = true;
  const summary = supporterDisclosure.querySelector("summary");
  if (summary) summary.tabIndex = desktopThanks.matches ? -1 : 0;
}
supporterDisclosure?.querySelector("summary")?.addEventListener("click", (event) => {
  if (desktopThanks.matches) event.preventDefault();
});
desktopThanks.addEventListener?.("change", syncSupporterDisclosure);
syncSupporterDisclosure();
const uiScheduler = StudioUI.createScheduler();
let nativeUiVisible = true;
let uiReadController = new AbortController();
let embeddedEngineRecoveryTask = null;
let heroSwapTimer = 0;
let heroInViewport = true;
const uiWaiters = new Set();
const isUiActive = () => !document.hidden && nativeUiVisible && !state.accessBlocked;
const modalMotion = StudioUI.createModalMotion({
  reduced: () => motionMedia.matches || !isUiActive(),
  desktop: () => document.documentElement.dataset.embedded !== "android" && desktopPointer.matches,
});

function enableAutoHideScrollbar(element) {
  if (!element || element.dataset.autoHideScrollbar === "ready") return;
  element.dataset.autoHideScrollbar = "ready";
  let hideTimer = 0;
  const reveal = () => {
    element.classList.add("is-scrollbar-active");
    clearTimeout(hideTimer);
    hideTimer = setTimeout(() => element.classList.remove("is-scrollbar-active"), 650);
  };
  element.addEventListener("scroll", reveal, { passive: true });
  element.addEventListener("wheel", reveal, { passive: true });
  element.addEventListener("touchstart", reveal, { passive: true });
  element.addEventListener("pointerdown", reveal, { passive: true });
  element.addEventListener("keydown", reveal);
}

$$('.auto-hide-scrollbar').forEach(enableAutoHideScrollbar);

function waitForUiActive() {
  return isUiActive() ? Promise.resolve() : new Promise((resolve) => uiWaiters.add(resolve));
}

function syncUiActivity() {
  const active = isUiActive();
  document.documentElement.classList.toggle("ui-suspended", !active);
  uiScheduler.setActive(active);
  if (!active) {
    uiReadController.abort();
    clearTimeout(heroSwapTimer);
    $("#heroPhrase")?.classList.remove("is-entering", "is-leaving");
    if (state.progressFrame) cancelAnimationFrame(state.progressFrame);
    state.progressFrame = 0;
    state.progressLastTick = 0;
    modalMotion.settle();
    return;
  }
  if (uiReadController.signal.aborted) uiReadController = new AbortController();
  for (const resolve of uiWaiters) resolve();
  uiWaiters.clear();
  refreshStatus(); refreshHistory();
  if (state.displayedProgress < state.targetProgress) updateProgress(state.targetProgress, progressElements.phase.textContent);
}

globalThis.setNativeVisibility = (visible) => {
  const reopening = !nativeUiVisible && Boolean(visible);
  nativeUiVisible = Boolean(visible);
  syncUiActivity();
  if (reopening) restoreUpdateNotice();
};
document.addEventListener("visibilitychange", syncUiActivity);
window.addEventListener("pagehide", () => { nativeUiVisible = false; syncUiActivity(); });
window.addEventListener("pageshow", (event) => {
  nativeUiVisible = true; syncUiActivity();
  if (event.persisted) restoreUpdateNotice();
  else focusUpdateNoticeOnLaunch();
});
let embeddedNativeTheme = (() => {
  const value = new URLSearchParams(location.search).get("nativeTheme");
  return ["light", "dark"].includes(value) ? value : "";
})();
const HERO_PHRASES = [
  "Temiz, tek APK olarak al.",
  "Split paketini cihazına göre hazırla.",
  "Reklam izlerini yerel olarak temizle."
];
const progressElements = {
  ring: $("#progressRing"),
  value: $("#progressRing b"),
  bar: $("#progressBar"),
  phase: $("#phaseText"),
  log: $("#liveLog")
};

function escapeHTML(value) {
  return String(value).replace(/[&<>'"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[character]);
}

function clientHeaders(extra = {}) { return { "X-Client-ID": clientId, ...extra }; }

async function recoverEmbeddedEngine() {
  if (document.documentElement.dataset.embedded !== "android" || !globalThis.AndroidThemeBridge?.ensureEngine) return false;
  if (embeddedEngineRecoveryTask) return embeddedEngineRecoveryTask;
  embeddedEngineRecoveryTask = (async () => {
    try { globalThis.AndroidThemeBridge.ensureEngine(); } catch { return false; }
    const deadline = Date.now() + 20000;
    while (Date.now() < deadline) {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), Math.min(1500, deadline - Date.now()));
      try {
        const response = await fetch("/api/status", { cache: "no-store", headers: clientHeaders(), signal: controller.signal });
        if (response.ok) return true;
      } catch {} finally { clearTimeout(timer); }
      await new Promise((resolve) => setTimeout(resolve, 180));
    }
    return false;
  })().finally(() => { embeddedEngineRecoveryTask = null; });
  return embeddedEngineRecoveryTask;
}

async function apiFetch(input, init) {
  const readOnly = ["GET", "HEAD"].includes((init?.method || "GET").toUpperCase());
  const embedded = document.documentElement.dataset.embedded === "android" && globalThis.AndroidThemeBridge?.ensureEngine;
  if (!readOnly && embedded) {
    // Recover before sending a mutation. A lost response must never replay an upload or patch.
    if (!await recoverEmbeddedEngine()) throw new Error("Yerel işlem motoruna bağlanılamadı. Lütfen yeniden dene.");
    if (init?.signal?.aborted) throw new DOMException("İstek iptal edildi.", "AbortError");
  }
  try {
    return await fetch(input, init);
  } catch (error) {
    if (error?.name === "AbortError" || !readOnly || !await recoverEmbeddedEngine()) throw error;
    if (init?.signal?.aborted) throw new DOMException("İstek iptal edildi.", "AbortError");
    return fetch(input, init);
  }
}

async function resolvePublicIpv4() {
  if (!location.hostname.toLowerCase().endsWith(".keenetic.link")) return "";
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 4000);
  try {
    const response = await fetch("https://api.ipify.org?format=json", {
      cache: "no-store", credentials: "omit", referrerPolicy: "no-referrer", signal: controller.signal
    });
    if (!response.ok) return "";
    const payload = await response.json();
    return typeof payload?.ip === "string" ? payload.ip : "";
  } catch {
    return "";
  } finally {
    clearTimeout(timer);
  }
}

async function detectBrowserName() {
  try {
    if (navigator.brave?.isBrave && await navigator.brave.isBrave()) return "Brave";
  } catch {}
  const ua = navigator.userAgent.toLowerCase();
  if (/edg\/|edga\/|edgios\//.test(ua)) return "Microsoft Edge";
  if (/opr\/|opera/.test(ua)) return "Opera";
  if (ua.includes("samsungbrowser")) return "Samsung Internet";
  if (/firefox|fxios/.test(ua)) return "Firefox";
  if (/chrome|crios/.test(ua)) return "Google Chrome";
  if (ua.includes("safari")) return "Safari";
  return "";
}

function extension(name) { return PACKAGE_EXTENSIONS.find((item) => name.toLowerCase().endsWith(item)) || ""; }
function isSplit(name) { return SPLIT_EXTENSIONS.includes(extension(name)); }

function applyTheme(preference, persist = true) {
  const selected = ["light", "dark", "system"].includes(preference) ? preference : "system";
  const resolved = selected === "system"
    ? (embeddedNativeTheme || (themeMedia.matches ? "dark" : "light"))
    : selected;
  document.documentElement.dataset.theme = resolved;
  document.documentElement.dataset.themePreference = selected;
  document.documentElement.style.colorScheme = resolved;
  document.querySelector('meta[name="theme-color"]').content = resolved === "dark" ? "#07100d" : "#f2f5ef";
  $$('[data-theme-choice]').forEach((button) => button.setAttribute("aria-pressed", String(button.dataset.themeChoice === selected)));
  if (persist) localStorage.setItem(THEME_KEY, selected);
  try { globalThis.AndroidThemeBridge?.setTheme(resolved); } catch {}
}

globalThis.setNativeTheme = (theme) => {
  if (!["light", "dark"].includes(theme)) return;
  embeddedNativeTheme = theme;
  if (document.documentElement.dataset.themePreference === "system") applyTheme("system", false);
};

function toast(message) {
  const element = $("#toast"); element.textContent = message; element.classList.add("show");
  clearTimeout(toast.timer); toast.timer = setTimeout(() => element.classList.remove("show"), 5200);
}

let activeDialog = null;
let lockedPageScrollTop = 0;
const pageScrollLocks = new Set();

function lockPageScroll(owner) {
  if (pageScrollLocks.has(owner)) return;
  if (pageScrollLocks.size === 0) {
    lockedPageScrollTop = window.scrollY || document.documentElement.scrollTop || 0;
    document.body.style.top = `-${lockedPageScrollTop}px`;
    document.body.classList.add("modal-scroll-locked");
  }
  pageScrollLocks.add(owner);
}

function unlockPageScroll(owner) {
  if (!pageScrollLocks.delete(owner) || pageScrollLocks.size > 0) return;
  document.body.classList.remove("modal-scroll-locked");
  document.body.style.removeProperty("top");
  window.scrollTo({ top: lockedPageScrollTop, left: 0, behavior: "auto" });
}

function containModalTouch(modalSelector, scrollableSelector = "") {
  // Modern engines keep the fixed page locked using CSS. Do not put their
  // native scrolling path behind a synchronous, non-passive touch listener.
  if (globalThis.CSS?.supports?.("overscroll-behavior", "contain")) return;
  $(modalSelector).addEventListener("touchmove", (event) => {
    // Popup'ın kaydırılabilir içeriği dışında başlayan hareketler arka sayfaya
    // ulaşmasın. Böylece aynı davranış tüm platformlarda ve tüm modallarda geçerli olur.
    if (!scrollableSelector || !event.target.closest(scrollableSelector)) event.preventDefault();
  }, { passive: false });
}

function closeAppDialog(value) {
  if (!activeDialog) return;
  const { resolve, mode } = activeDialog;
  activeDialog = null;
  const dialog = $("#appDialog");
  modalMotion.close(dialog, () => unlockPageScroll("app-dialog"));
  resolve(mode === "prompt" && value !== null ? $("#appDialogInput").value.trim() : value);
}

function openAppDialog({ title, message, confirmText = "Onayla", eyebrow = "ONAY GEREKİYOR", mode = "confirm", value = "", destructive = false }) {
  if (activeDialog) closeAppDialog(null);
  const dialog = $("#appDialog");
  const inputWrap = $("#appDialogInputWrap");
  const input = $("#appDialogInput");
  const confirmButton = $("#appDialogConfirm");
  $("#appDialogEyebrow").textContent = eyebrow;
  $("#appDialogTitle").textContent = title;
  $("#appDialogMessage").textContent = message;
  confirmButton.textContent = confirmText;
  confirmButton.classList.toggle("destructive", destructive);
  inputWrap.classList.toggle("hidden", mode !== "prompt");
  input.value = value;
  modalMotion.open(dialog);
  lockPageScroll("app-dialog");
  return new Promise((resolve) => {
    activeDialog = { resolve, mode };
    requestAnimationFrame(() => (mode === "prompt" ? input : confirmButton).focus());
  });
}

function confirmAction(title, message, confirmText = "Onayla", destructive = false) {
  return openAppDialog({ title, message, confirmText, destructive });
}

function promptAction(title, message, value = "") {
  return openAppDialog({ title, message, confirmText: "Kaydet", eyebrow: "CİHAZ BİLGİSİ", mode: "prompt", value });
}

function closeReportViewer() {
  const viewer = $("#reportViewer");
  $("#reportViewerDownload").removeAttribute("href");
  modalMotion.close(viewer, () => unlockPageScroll("report-viewer"));
}

let diagnosticJobId = null;
let diagnosticGeneration = 0;
let diagnosticSanitizedReport = null;
function closeDiagnosticViewer() {
  diagnosticGeneration++;
  diagnosticJobId = null;
  $("#diagnosticViewerContent").setAttribute("aria-busy", "false");
  const download = $("#diagnosticViewerDownload");
  download.removeAttribute("href");
  download.setAttribute("aria-disabled", "true");
  download.classList.remove("has-report");
  const card = $("#diagnosticViewer .diagnostic-card");
  card.classList.remove("is-size-stable");
  card.style.removeProperty("--diagnostic-stable-height");
  modalMotion.close($("#diagnosticViewer"), () => unlockPageScroll("diagnostic-viewer"));
}

async function refreshDiagnosticPreview(stabilizeSize = false) {
  const generation = ++diagnosticGeneration;
  const content = $("#diagnosticViewerContent");
  const download = $("#diagnosticViewerDownload");
  const includesIdentifiers = $("#diagnosticIdentifiers").checked;
  const query = `identifiers=${includesIdentifiers ? "1" : "0"}`;
  const base = diagnosticJobId ? `/api/jobs/${encodeURIComponent(diagnosticJobId)}/diagnostic` : "/api/diagnostic";
  if (stabilizeSize) {
    const card = $("#diagnosticViewer .diagnostic-card");
    if (!card.classList.contains("is-size-stable")) {
      card.style.setProperty("--diagnostic-stable-height", `${card.getBoundingClientRect().height.toFixed(2)}px`);
      card.classList.add("is-size-stable");
    }
  }
  // Checkbox changes should not briefly replace the report with a one-line
  // placeholder: that shrinks the dialog and makes the content flash. When the
  // option is turned off, never leave the identifying version on screen.
  if (!includesIdentifiers && content.dataset.identifiers === "true") {
    content.textContent = diagnosticSanitizedReport ?? "";
    content.dataset.identifiers = "false";
  }
  content.setAttribute("aria-busy", "true");
  // Keep the existing link styling while refreshing. aria-disabled and the
  // click guard below prevent downloading a stale report in the meantime.
  download.setAttribute("aria-disabled", "true");
  try {
    const response = await apiFetch(`${base}?${query}`, { cache: "no-store", headers: clientHeaders() });
    const report = await response.text();
    if (!response.ok) {
      let message = report;
      try { message = JSON.parse(report).error || report; } catch {}
      throw new Error(message || "Hata raporu açılamadı.");
    }
    if (generation !== diagnosticGeneration) return;
    content.textContent = report;
    content.dataset.identifiers = includesIdentifiers ? "true" : "false";
    if (!includesIdentifiers) diagnosticSanitizedReport = report;
    content.scrollTop = 0;
    download.href = `${base}?${query}&download=1`;
    download.classList.add("has-report");
    download.setAttribute("aria-disabled", "false");
  } catch (error) {
    if (generation === diagnosticGeneration) {
      content.textContent = `Hata raporu açılamadı.\n\n${error.message || "Bilinmeyen hata"}`;
      content.dataset.identifiers = "false";
      download.removeAttribute("href");
      download.classList.remove("has-report");
    }
  } finally {
    if (generation === diagnosticGeneration) content.setAttribute("aria-busy", "false");
  }
}

function openDiagnosticViewer(jobId = null) {
  diagnosticJobId = jobId;
  diagnosticSanitizedReport = null;
  const download = $("#diagnosticViewerDownload");
  download.removeAttribute("href");
  download.setAttribute("aria-disabled", "true");
  download.classList.remove("has-report");
  const card = $("#diagnosticViewer .diagnostic-card");
  card.classList.remove("is-size-stable");
  card.style.removeProperty("--diagnostic-stable-height");
  $("#diagnosticIdentifiers").checked = false;
  $("#diagnosticViewerContent").textContent = "Rapor hazırlanıyor…";
  $("#diagnosticViewerContent").dataset.identifiers = "false";
  modalMotion.open($("#diagnosticViewer"));
  lockPageScroll("diagnostic-viewer");
  requestAnimationFrame(() => $("#diagnosticViewerClose").focus());
  refreshDiagnosticPreview();
}

function closeMessageReview() {
  messageReviewGeneration++;
  const viewer = $("#messageReview");
  modalMotion.close(viewer, () => unlockPageScroll("message-review"));
}

function closeInstalledApps() {
  cancelInstalledAppReveal();
  state.selectedInstalledPackage = "";
  const viewer = $("#installedApps");
  modalMotion.close(viewer, () => unlockPageScroll("installed-apps"));
}

function installedAppActionsMarkup(item) {
  const packageName = escapeHTML(item.package);
  const label = escapeHTML(item.label || item.package);
  const sharing = state.installedSharePackage === item.package;
  return `<div class="installed-app-actions" role="group" aria-label="${label} işlemleri">
    <button class="secondary" type="button" data-installed-action="share" data-installed-package="${packageName}"${sharing ? " disabled" : ""}>${sharing ? "Hazırlanıyor…" : "Paylaş"}</button>
    <button class="primary" type="button" data-installed-action="process" data-installed-package="${packageName}">İşleme al</button>
  </div>`;
}

function installedAppEntry(packageName) {
  return [...$("#installedAppsList").querySelectorAll("[data-installed-entry]")]
    .find((entry) => entry.dataset.installedEntry === packageName);
}

let installedRevealTimer = 0;
let installedAutoScrolling = false;

function cancelInstalledAppReveal() {
  clearTimeout(installedRevealTimer);
  installedRevealTimer = 0;
  if (installedAutoScrolling) {
    const list = $("#installedAppsList");
    // Stop only our own reveal, never consume the user's pointer/wheel event.
    list.scrollTo({ top: list.scrollTop, behavior: "instant" });
    installedAutoScrolling = false;
  }
}

function scheduleInstalledAppReveal(list, entry) {
  cancelInstalledAppReveal();
  installedRevealTimer = setTimeout(() => {
    installedRevealTimer = 0;
    if (!isUiActive() || $("#installedApps").matches(".hidden, .is-closing")
        || !entry.isConnected || !entry.classList.contains("selected")) return;
    const viewport = list.getBoundingClientRect();
    const row = entry.getBoundingClientRect();
    const delta = row.top < viewport.top ? row.top - viewport.top
      : Math.max(0, row.bottom - viewport.bottom);
    if (Math.abs(delta) < 1) return;
    installedAutoScrolling = !motionMedia.matches;
    // Confine the reveal to this list; scrollIntoView also moves ancestors.
    list.scrollTo({ top: list.scrollTop + delta, behavior: motionMedia.matches ? "instant" : "smooth" });
  }, motionMedia.matches ? 0 : 380);
}

function captureInstalledAppPositions(list) {
  const viewport = list.getBoundingClientRect();
  const positions = new Map();
  const entries = [...list.querySelectorAll(".installed-app-entry")];
  entries.forEach((entry) => {
    const rect = entry.getBoundingClientRect();
    if (rect.bottom >= viewport.top - 96 && rect.top <= viewport.bottom + 96) {
      positions.set(entry.dataset.installedEntry, rect.top);
    }
  });
  // Keep the currently visible position on rapid taps; finishing first snaps
  // every moving row to its old endpoint before the next transition starts.
  entries.forEach((entry) => entry.getAnimations?.().forEach((animation) => animation.cancel()));
  return positions;
}

function animateInstalledAppReflow(list, positions) {
  if (motionMedia.matches || typeof Element.prototype.animate !== "function") return;
  const moves = [];
  list.querySelectorAll(".installed-app-entry").forEach((entry) => {
    const previousTop = positions.get(entry.dataset.installedEntry);
    if (previousTop == null) return;
    const delta = previousTop - entry.getBoundingClientRect().top;
    if (Math.abs(delta) < .5) return;
    moves.push({ entry, delta });
  });
  // Batch geometry reads before animation writes: no read/write layout thrashing.
  moves.forEach(({ entry, delta }) => {
    entry.animate(
      [
        { transform: `translate3d(0, ${delta}px, 0)` },
        { transform: "translate3d(0, 0, 0)" },
      ],
      INLINE_REFLOW_MOTION,
    );
  });
}

function updateInstalledAppSelection(item) {
  cancelInstalledAppReveal();
  const list = $("#installedAppsList");
  const positions = captureInstalledAppPositions(list);
  list.querySelectorAll(".installed-app-entry.selected").forEach((entry) => {
    entry.classList.remove("selected");
    entry.querySelector(".installed-app-row")?.setAttribute("aria-expanded", "false");
    entry.querySelector(".installed-app-actions")?.remove();
  });
  if (!state.selectedInstalledPackage || !item) {
    animateInstalledAppReflow(list, positions);
    return;
  }
  const entry = installedAppEntry(item.package);
  if (!entry) return;
  entry.classList.add("selected");
  const row = entry.querySelector(".installed-app-row");
  entry.querySelector(".installed-app-actions")?.remove();
  row?.setAttribute("aria-expanded", "true");
  row?.insertAdjacentHTML("afterend", installedAppActionsMarkup(item));
  animateInstalledAppReflow(list, positions);
  scheduleInstalledAppReveal(list, entry);
}

function finishInstalledShareUi() {
  const packageName = state.installedSharePackage;
  state.installedSharePackage = "";
  const entry = packageName ? installedAppEntry(packageName) : null;
  const button = entry?.querySelector('[data-installed-action="share"]');
  if (button) { button.disabled = false; button.textContent = "Paylaş"; }
}

function renderInstalledApps(query = "") {
  cancelInstalledAppReveal();
  const needle = query.trim().toLocaleLowerCase("tr-TR");
  const list = $("#installedAppsList");
  const entries = new Map([...list.querySelectorAll('[data-installed-entry]')]
    .map((entry) => [entry.dataset.installedEntry, entry]));
  list.querySelectorAll('.installed-apps-empty, .installed-apps-loading').forEach((node) => node.remove());
  const retained = new Set();
  let cursor = list.firstElementChild;
  let visible = 0;
  // Keep each decoded image node across reopening, native refresh and filtering.
  for (const item of state.installedApps) {
    if (!item.package || retained.has(item.package)) continue;
    retained.add(item.package);
    let entry = entries.get(item.package);
    if (!entry) {
      entry = document.createElement('div');
      entry.className = 'installed-app-entry';
      entry.dataset.installedEntry = item.package;
      entry.innerHTML = `<button class="installed-app-row" type="button" data-installed-package="${escapeHTML(item.package)}" aria-expanded="false"><span class="installed-app-mark"></span><span><b></b><small></small></span></button>`;
    }
    const row = entry.querySelector('.installed-app-row');
    const label = item.label || item.package;
    const detail = `${item.package}${item.version ? ` · v${item.version}` : ''}${item.splits ? ` · ${Number(item.splits)} split` : ''}`;
    if (row.querySelector('b').textContent !== label) row.querySelector('b').textContent = label;
    if (row.querySelector('small').textContent !== detail) row.querySelector('small').textContent = detail;
    let icon = row.firstElementChild;
    if (item.icon) {
      if (icon.tagName !== 'IMG') {
        const image = document.createElement('img');
        image.className = 'installed-app-icon'; image.alt = ''; image.loading = 'lazy'; image.decoding = 'async';
        icon.replaceWith(image); icon = image;
      }
      if (icon.getAttribute('src') !== item.icon) icon.setAttribute('src', item.icon);
    } else {
      if (icon.tagName === 'IMG') {
        const mark = document.createElement('span'); mark.className = 'installed-app-mark';
        icon.replaceWith(mark); icon = mark;
      }
      const initial = label.slice(0, 1).toUpperCase();
      if (icon.textContent !== initial) icon.textContent = initial;
    }
    const selected = state.selectedInstalledPackage === item.package;
    entry.classList.toggle('selected', selected);
    row.setAttribute('aria-expanded', String(selected));
    if (!selected) entry.querySelector('.installed-app-actions')?.remove();
    else if (!entry.querySelector('.installed-app-actions')) row.insertAdjacentHTML('afterend', installedAppActionsMarkup(item));
    entry.hidden = Boolean(needle && !`${label} ${item.package}`.toLocaleLowerCase('tr-TR').includes(needle));
    if (!entry.hidden) visible++;
    if (entry !== cursor) list.insertBefore(entry, cursor);
    cursor = entry.nextElementSibling;
  }
  entries.forEach((entry, key) => { if (!retained.has(key)) entry.remove(); });
  if (!visible) list.insertAdjacentHTML('beforeend', '<p class="installed-apps-empty">Aramayla eşleşen uygulama bulunamadı.</p>');
}

function installedPackageFilename(item) {
  const label = String(item?.label || "installed-app").trim() || "installed-app";
  const version = String(item?.version || "").trim();
  return `${label}${version ? ` v${version}` : ""}${item?.splits ? ".apks" : ".apk"}`;
}

function processInstalledApp(item) {
  if (!item) return;
  closeInstalledApps();
  state.file = { name: installedPackageFilename(item), size: 0, installed: true };
  prepareAnalysisView(state.file.name, 0, Boolean(item.splits));
  try { globalThis.AndroidThemeBridge.importInstalledPackage(item.package); }
  catch { toast("Yüklü uygulama alınamadı."); reset(); }
}

function openInstalledApps() {
  $("#installedAppsSearch").value = "";
  state.selectedInstalledPackage = "";
  const viewer = $("#installedApps");
  modalMotion.open(viewer);
  lockPageScroll("installed-apps");
  if (state.installedAppsReady) renderInstalledApps();
  else $("#installedAppsList").innerHTML = `<div class="installed-apps-loading"><i></i><b>Uygulamalar hazırlanıyor</b><small>Liste cihazından güvenli biçimde okunuyor…</small></div>`;
  if (state.installedAppsLoading) return;
  state.installedAppsLoading = true;
  try {
    if (globalThis.AndroidThemeBridge?.requestInstalledPackages) {
      globalThis.AndroidThemeBridge.requestInstalledPackages();
    } else {
      globalThis.onInstalledPackagesLoaded(globalThis.AndroidThemeBridge?.listInstalledPackages?.() || "[]");
    }
  } catch {
    state.installedAppsLoading = false;
    $("#installedAppsList").innerHTML = "<p class=\"installed-apps-empty\">Yüklü uygulamalar okunamadı.</p>";
  }
}

globalThis.onInstalledPackagesLoaded = (payload) => {
  state.installedAppsLoading = false;
  try {
    state.installedApps = JSON.parse(payload);
    state.installedAppsReady = true;
  } catch {
    state.installedApps = [];
    state.installedAppsReady = false;
  }
  if (!state.installedApps.some((item) => item.package === state.selectedInstalledPackage)) state.selectedInstalledPackage = "";
  if (!$("#installedApps").classList.contains("hidden")) renderInstalledApps($("#installedAppsSearch").value);
};

globalThis.onNativeAction = async (action, payload) => {
  let result;
  try { result = JSON.parse(payload); }
  catch { result = { status: "error", error: "Android yanıtı okunamadı." }; }
  if (action === "split_install") {
    const button = $("#directSplitInstallButton");
    if (result.status === "plan_ready") {
      if (!state.jobId || !state.splitInstallRequestJobId || state.splitInstallRequestJobId !== state.jobId) return;
      state.nativeSplitInstallBusy = false;
      button.disabled = false;
      button.textContent = "Bileşenleri yeniden incele";
      renderDirectSplitPlan(result);
      return;
    }
    if (["installed", "error", "cancelled"].includes(result.status)) {
      state.nativeSplitInstallBusy = false;
      state.splitInstallSubmitted = false;
      button.disabled = false;
      button.textContent = "Bileşenleri yeniden incele";
      clearDirectSplitPlan();
      refreshInstallHistory();
    }
    if (result.status === "permission_required") {
      toast("Kuruluma devam etmek için bu kaynaktan uygulama yükleme iznini etkinleştir.");
    } else if (result.status === "session_submitted") {
      state.nativeSplitInstallBusy = false;
      toast(`${result.modules || 0} özgün APK bileşeni Android kurulumuna gönderildi.`);
    } else if (result.status === "confirmation_opened") {
      toast("Android kurulum onayı açıldı.");
    } else if (result.status === "installed") {
      toast(result.message || "Özgün split paketi kuruldu.");
    } else if (result.status === "error" || result.status === "cancelled") {
      await openAppDialog({ title: "Doğrudan kurulum tamamlanamadı", message: result.error || result.message || "Android paketi kuramadı.", confirmText: "Anladım", eyebrow: "SPLIT KURULUMU" });
    }
    return;
  }
  if (action === "update") {
    const button = $("#updateDownload");
    if (result.status === "permission_required") {
      toast("Güncellemeye devam etmek için bu kaynaktan uygulama yükleme iznini etkinleştir.");
      return;
    }
    if (result.status === "incompatible") {
      state.updateBusy = false; button.disabled = false; button.textContent = button.dataset.defaultLabel || "İndir ve yükle";
      await openAppDialog({
        title: "Güncelleme bu cihazla uyumlu değil",
        message: (result.reasons || []).join("\n") || "Android sürümü veya işlemci mimarisi güncellemenin gereksinimlerini karşılamıyor.",
        confirmText: "Anladım", eyebrow: "GÜNCELLEME DENETİMİ"
      });
      return;
    }
    if (result.status === "installer_opened") {
      state.updateBusy = false; button.disabled = false; button.textContent = button.dataset.defaultLabel || "İndir ve yükle";
      toast("Güncelleme doğrulandı; Android kurulum ekranı açıldı.");
      return;
    }
    if (result.status === "error") {
      state.updateBusy = false; button.disabled = false; button.textContent = button.dataset.defaultLabel || "İndir ve yükle";
      toast(result.error || "Güncelleme tamamlanamadı.");
    }
    return;
  }
  if (result.status === "error") {
    if (action === "install") { state.nativeInstallBusy = false; $("#installButton").disabled = false; }
    if (action === "share") {
      state.nativeShareBusy = false; finishInstalledShareUi(); $("#shareOutputButton").disabled = false;
    }
    return toast(result.error || "İşlem tamamlanamadı.");
  }
  if (action === "share") {
    state.nativeShareBusy = false; finishInstalledShareUi(); $("#shareOutputButton").disabled = false;
    if (result.status === "opened") toast("Paylaşım seçenekleri açıldı.");
    return;
  }
  if (action !== "install") return;
  if (result.status === "permission_required") {
    toast("Kuruluma devam etmek için bu kaynaktan uygulama yükleme iznini etkinleştir.");
    return;
  }
  if (result.status === "incompatible") {
    state.nativeInstallBusy = false; $("#installButton").disabled = false;
    await openAppDialog({
      title: "Bu paket cihazla uyumlu değil",
      message: (result.reasons || []).join("\n") || "Android sürümü veya işlemci mimarisi paketin gereksinimlerini karşılamıyor.",
      confirmText: "Anladım", eyebrow: "KURULUM DENETİMİ"
    });
    return;
  }
  if (result.status === "requires_uninstall") {
    const reasons = (result.reasons || []).join("\n");
    const approved = await confirmAction(
      "Mevcut uygulama kaldırılmalı",
      `${reasons}\n\nDevam edersen cihazdaki mevcut uygulama ve uygulamaya ait yerel veriler kaldırılır. Ardından temizlenmiş paket için Android kurulum ekranı açılır.`,
      "Kaldır ve devam et", true
    );
    if (approved) globalThis.AndroidThemeBridge?.confirmReplaceInstall?.(result.token);
    else {
      globalThis.AndroidThemeBridge?.cancelPendingInstall?.(result.token);
      state.nativeInstallBusy = false; $("#installButton").disabled = false;
    }
    return;
  }
  if (result.status === "installer_opened") {
    state.nativeInstallBusy = false; $("#installButton").disabled = false;
    toast("Paket doğrulandı; Android kurulum ekranı açıldı.");
  }
};

function shortDexClass(value = "") {
  return value.replace(/^L/, "").replace(/;$/, "").replaceAll("/", ".");
}

let messageScanTask = null;
let messageReviewGeneration = 0;

function renderMessageCandidates(candidates) {
  state.messageCandidates = candidates || [];
  const list = $("#messageCandidateList");
  if (!state.messageCandidates.length) {
    list.innerHTML = "<p>İzlenebilir bir başlangıç mesajı çağrısı bulunamadı. Bu sonuç uygulamada hiç diyalog olmadığı anlamına gelmez; çözülemeyen veya başlangıç dışındaki akışlara dokunulmadı.</p>";
    return;
  }
  const assessmentLabel = (item) => ({
    likely_added: "Yüksek olasılık",
    needs_review: "İnceleme gerekli",
    likely_internal: "Düşük olasılık",
  })[item.assessment] || "İnceleme gerekli";
  const renderItem = (item) => `
    <div class="message-startup-item">
      <label class="message-candidate"><input type="checkbox" data-message-target value="${escapeHTML(item.id)}" ${state.messageTargets.includes(item.id) ? "checked" : ""}>
        <span><span class="message-likelihood" data-level="${escapeHTML(item.assessment || "needs_review")}">${escapeHTML(assessmentLabel(item))}</span><b>${escapeHTML(item.kind)} başlatma adayı</b><small>${escapeHTML(shortDexClass(item.owner_class))} → ${escapeHTML(item.owner_method)}() · ${escapeHTML(item.dex)}</small>
        <small>Hedef: ${escapeHTML(shortDexClass(item.target_class))} → ${escapeHTML(item.target_method)}()</small>
        <small>${item.location === "before_super" ? "Üst sınıf başlangıcından önce çağrılıyor." : "Başlangıç yaşam döngüsünden çağrılıyor."} ${item.deferred ? "Gecikmeli görev üzerinden mesaj gösterimine ulaşıyor." : "Mesaj gösterimine ulaşan çağrı zinciri bulundu."}</small>
        ${Array.isArray(item.signals) && item.signals.length ? `<small class="message-analysis-reasons">${item.signals.map((signal) => escapeHTML(signal)).join(" ")}</small>` : ""}
        ${item.confidence === "review" ? '<small class="message-review-warning">Ek yan etkiler algılandı: bu çağrı mesaj dışında veri, ağ veya başka başlangıç işlemleri de yapabilir.</small>' : ''}
        ${item.confidence === "partial" ? '<small class="message-review-warning">Mesaja ulaşan yol bulundu; tarama sınırı nedeniyle diğer yolların tamamı incelenemedi. Bu çağrı başka işlevleri de etkileyebilir.</small>' : ''}</span>
      </label><details><summary>Çağrı zincirini göster</summary><code>${escapeHTML(item.trace || "")}</code></details>
    </div>`;
  const priority = state.messageCandidates.filter((item) => item.focus === "priority");
  const review = state.messageCandidates.filter((item) => item.focus === "review");
  const other = state.messageCandidates.filter((item) => item.focus !== "priority" && item.focus !== "review");
  const selectedReview = review.filter((item) => state.messageTargets.includes(item.id)).length;
  const selectedOther = other.filter((item) => state.messageTargets.includes(item.id)).length;
  list.innerHTML = priority.length
    ? `<div class="message-focus-heading"><b>Olası sonradan eklenmiş çağrılar</b><span>${priority.length}</span></div><p class="message-focus-note">Yerleşim, kod alanı, çağrı zinciri saflığı ve başlangıç köklerindeki kullanım birlikte değerlendirildi. Bunlar güçlü adaylardır; kesin kaynak doğrulaması değildir.</p>${priority.map(renderItem).join("")}`
    : '<p class="message-focus-note">Çoklu analiz işaretlerinde yüksek olasılığa ulaşan bir çağrı bulunamadı. Bu, eklenmiş mesaj olmadığı anlamına gelmez; belirsiz sonuçları aşağıdan inceleyebilirsin.</p>';
  if (review.length) list.insertAdjacentHTML("beforeend", `
    <details class="message-other-results message-review-results" ${selectedReview ? "open" : ""}>
      <summary>İncelenmesi gereken çağrılar <span>${review.length}${selectedReview ? ` · ${selectedReview} seçili` : ""}</span></summary>
      <p>Bazı eklenme işaretleri var; ancak uygulamanın kendi başlangıç akışı olma ihtimali de anlamlı. Çağrı zincirini doğrulamadan seçme.</p>
      ${review.map(renderItem).join("")}
    </details>`);
  if (other.length) list.insertAdjacentHTML("beforeend", `
    <details class="message-other-results" ${selectedOther ? "open" : ""}>
      <summary>Düşük olasılıklı uygulama içi çağrılar <span>${other.length}${selectedOther ? ` · ${selectedOther} seçili` : ""}</span></summary>
      <p>Uygulamanın kendi mesajları, ortak kullanılan yardımcılar veya tamamı çözülemeyen akışlar bu bölümde süzüldü. Özel bir doğrulaman yoksa seçme.</p>
      ${other.map(renderItem).join("")}
    </details>`);
}

function openMessageReview() {
  const viewer = $("#messageReview");
  $("#messageRiskAcknowledged").checked = false;
  clearMessageRiskError();
  modalMotion.open(viewer);
  lockPageScroll("message-review");
  requestAnimationFrame(() => $("#messageReviewClose").focus());
  scanMessageCandidates();
}

async function scanMessageCandidates() {
  const generation = ++messageReviewGeneration;
  const jobId = state.jobId;
  const selection = JSON.stringify({ split_selection: state.splitSelection });
  const key = `${jobId}:${selection}`;
  const button = $("#messageScanButton");
  button.disabled = true; button.textContent = "Çağrılar izleniyor…";
  $("#messageReviewApply").disabled = true;
  $("#messageCandidateList").innerHTML = "<p>Activity başlangıçları ve DEX dosyaları arasındaki çağrı zincirleri inceleniyor…</p>";
  try {
    if (messageScanTask && messageScanTask.key !== key) throw new Error("Önceki taramanın tamamlanmasını bekle, ardından yeniden tara.");
    if (!messageScanTask) {
      const task = {key, promise: null};
      task.promise = (async () => {
        const response = await apiFetch(`/api/jobs/${encodeURIComponent(jobId)}/message-candidates`, { method: "POST", headers: clientHeaders({"Content-Type":"application/json"}), body: selection });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Başlangıç çağrıları taranamadı.");
        return data;
      })().finally(() => { if (messageScanTask === task) messageScanTask = null; });
      messageScanTask = task;
    }
    const data = await messageScanTask.promise;
    if (generation !== messageReviewGeneration || state.jobId !== jobId) return;
    renderMessageCandidates(data.candidates || []);
    $("#messageReviewApply").disabled = false;
  } catch (error) {
    if (generation === messageReviewGeneration) $("#messageCandidateList").innerHTML = `<p>${escapeHTML(error.message)}</p>`;
  } finally {
    if (generation === messageReviewGeneration) { button.disabled = false; button.textContent = "Yeniden tara"; }
  }
}

function clearMessageRiskError() {
  $("#messageRiskAcknowledged").removeAttribute("aria-invalid");
  $("#messageRiskError").classList.add("hidden");
  $("#messageRiskError").textContent = "";
}

function applyMessageSelection() {
  const selected = $$('[data-message-target]:checked').map((input) => input.value);
  if (selected.length && !$("#messageRiskAcknowledged").checked) {
    const message = "Seçili başlangıç çağrılarını uygulamadan önce etki uyarısını onayla.";
    const input = $("#messageRiskAcknowledged");
    input.setAttribute("aria-invalid", "true");
    $("#messageRiskError").textContent = message;
    $("#messageRiskError").classList.remove("hidden");
    input.focus({ preventScroll: true });
    input.closest("label").scrollIntoView({ block: "center", behavior: motionMedia.matches ? "auto" : "smooth" });
    return;
  }
  clearMessageRiskError();
  state.messageTargets = selected;
  closeMessageReview();
  updateActionState();
  toast(state.messageTargets.length ? `${state.messageTargets.length} başlangıç çağrısı seçildi; yama işlem başlatıldığında uygulanacak.` : "Başlangıç çağrısı seçimi kaldırıldı.");
}

async function openReportViewer(jobId, title = "Paket işlem raporu") {
  if (!jobId) return;
  const viewer = $("#reportViewer");
  const content = $("#reportViewerContent");
  const download = $("#reportViewerDownload");
  $("#reportViewerTitle").textContent = title || "Paket işlem raporu";
  download.href = `/api/jobs/${encodeURIComponent(jobId)}/report`;
  download.setAttribute("download", "apk-cleaner-studio-report.txt");
  content.textContent = "Rapor hazırlanıyor…";
  modalMotion.open(viewer);
  lockPageScroll("report-viewer");
  requestAnimationFrame(() => $("#reportViewerClose").focus());
  try {
    const response = await apiFetch(`/api/jobs/${encodeURIComponent(jobId)}/report`, {
      cache: "no-store", headers: clientHeaders()
    });
    const report = await response.text();
    if (!response.ok) {
      let message = report;
      try { message = JSON.parse(report).error || report; } catch {}
      throw new Error(message || "Rapor görüntülenemedi.");
    }
    content.textContent = report.trim() || "Bu işlem için rapor içeriği bulunamadı.";
    content.scrollTop = 0;
  } catch (error) {
    content.textContent = `Rapor görüntülenemedi.\n\n${error.message || "Bilinmeyen hata"}`;
  }
}

function renderAccessBlocked() {
  if (state.accessBlocked) return;
  state.accessBlocked = true;
  uiScheduler.setActive(false);
  document.title = "Erişim engellendi · APK Cleaner Studio";
  document.body.className = "access-blocked-page";
  document.body.innerHTML = `<main class="access-blocked"><i>!</i><h1>Erişim engellendi</h1><p>Bu cihazın APK Cleaner Studio arayüzüne erişimi ana makine tarafından engellendi.</p><small>Erişimin yeniden açılması için yöneticiye istek gönderebilirsin.</small><form method="post" action="/api/access-request"><button type="submit">Yöneticiden erişim iste</button></form></main>`;
}

function humanSize(bytes) { return bytes > 1024 ** 2 ? `${(bytes / 1024 ** 2).toFixed(1)} MB` : `${(bytes / 1024).toFixed(1)} KB`; }
function showView(id) {
  $$(".view").forEach((view) => view.classList.add("hidden"));
  $(id).classList.remove("hidden");
  const showStartGuide = id === "#selectView" || id === "#workingView" || id === "#resultView";
  $("#startGuide").classList.toggle("hidden", !showStartGuide);
  $(".workspace-primary > .features").classList.toggle("hidden", !["#selectView", "#analysisView", "#workingView", "#resultView"].includes(id));
  const workspace = $(".workspace");
  if (workspace) workspace.dataset.stage = id.slice(1).replace(/View$/, "");
}
function setStep(step) { $$(".steps>div").forEach((item) => item.classList.toggle("active", Number(item.dataset.step) <= step)); }

function startHeroRotation() {
  const phrase = $("#heroPhrase");
  if (!phrase) return;
  if (typeof IntersectionObserver === "function") {
    const observer = new IntersectionObserver(([entry]) => { heroInViewport = entry.isIntersecting; });
    observer.observe(phrase);
  }
  let index = 0;
  const rotate = () => {
    if (!isUiActive() || motionMedia.matches || !heroInViewport || pageScrollLocks.size) return;
    phrase.classList.add("is-leaving");
    heroSwapTimer = setTimeout(() => {
      index = (index + 1) % HERO_PHRASES.length;
      phrase.textContent = HERO_PHRASES[index];
      phrase.classList.remove("is-leaving");
      phrase.classList.add("is-entering");
      requestAnimationFrame(() => requestAnimationFrame(() => phrase.classList.remove("is-entering")));
    }, 510);
  };
  uiScheduler.add("hero", rotate, 6000);
}

function seenTime(value) {
  const date = new Date(Number(value) * 1000);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" });
}

function renderClients(clients = []) {
  const list = $("#clientList");
  if (!list) return;
  const signature = JSON.stringify(clients);
  if (renderClients.signature === signature) return;
  renderClients.signature = signature;
  list.setAttribute("aria-busy", "false");
  $("#clientTitle").textContent = clients.length ? `${clients.length} cihaz bu oturumda görüldü` : "Henüz bağlantı yok";
  list.innerHTML = clients.map((client) => `
    <div class="client-row ${client.blocked ? "is-blocked" : client.online ? "is-online" : "is-offline"}">
      <span class="client-dot" aria-hidden="true"></span>
      <div><b title="${escapeHTML(client.display_name || (client.local ? "Bu bilgisayar" : "Ağ cihazı"))}">${escapeHTML(client.display_name || (client.local ? "Bu bilgisayar" : "Ağ cihazı"))}</b><small>${escapeHTML(`${client.address} · ${client.description}`)}</small>${client.access_requested_at ? `<span class="access-request-badge">ERİŞİM İSTİYOR</span>` : ""}<nav class="client-actions">${client.can_rename ? `<button type="button" data-rename-client="${escapeHTML(client.id)}" data-client-name="${escapeHTML(client.display_name || "")}">Adını değiştir</button>` : ""}${client.can_manage ? client.access_requested_at ? `<button type="button" data-manage-client="${escapeHTML(client.id)}" data-client-action="unblock" data-client-name="${escapeHTML(client.display_name || "Ağ cihazı")}">İzin ver</button><button type="button" data-manage-client="${escapeHTML(client.id)}" data-client-action="deny" data-client-name="${escapeHTML(client.display_name || "Ağ cihazı")}">Reddet</button>` : `<button type="button" data-manage-client="${escapeHTML(client.id)}" data-client-action="${client.blocked ? "unblock" : "block"}" data-client-name="${escapeHTML(client.display_name || "Ağ cihazı")}">${client.blocked ? "Engeli kaldır" : "Engelle"}</button>` : ""}${client.can_manage ? `<button type="button" data-manage-client="${escapeHTML(client.id)}" data-client-action="delete" data-client-name="${escapeHTML(client.display_name || "Ağ cihazı")}">Listeden sil</button>` : ""}</nav></div>
      <time><strong>${client.blocked ? "ENGELLENDİ" : client.online ? "BAĞLI" : "BAĞLANTI KESİLDİ"}</strong><small>İLK ${seenTime(client.first_seen)}</small><b>SON ${seenTime(client.last_seen)}</b></time>
    </div>`).join("");
  $$('[data-rename-client]').forEach((button) => button.addEventListener("click", () => renameClient(button.dataset.renameClient, button.dataset.clientName)));
  $$('[data-manage-client]').forEach((button) => button.addEventListener("click", () => manageClient(button.dataset.manageClient, button.dataset.clientAction, button.dataset.clientName)));
}

async function saveClientName(targetId, name) {
  try {
    const response = await apiFetch("/api/client/name", {
      method: "POST", headers: clientHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ client_id: clientId, target_id: targetId, name })
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Cihaz adı kaydedilemedi.");
    renderClients(data.clients || []); toast("Cihaz adı kaydedildi.");
  } catch (error) { toast(error.message); }
}

async function renameClient(targetId, currentName) {
  const name = await promptAction("Görünen adı değiştir", "Bu cihaz için arayüzde kullanılacak adı yaz.", currentName || "");
  if (name === null) return;
  await saveClientName(targetId, name);
}

async function manageClient(targetId, action, name) {
  const messages = {
    block: `${name} adlı cihazın uygulamaya erişimi engellensin mi?`,
    unblock: `${name} adlı cihazın erişim engeli kaldırılsın mı?`,
    deny: `${name} adlı cihazın erişim isteği reddedilsin mi?`,
    delete: `${name} oturum listesinden silinsin mi? Bağlı cihaz yeniden istek gönderirse tekrar görünebilir.`
  };
  if (!await confirmAction("Cihaz erişimini yönet", messages[action] || "Bu işlem uygulansın mı?", action === "delete" ? "Listeden sil" : "Uygula", ["block", "deny", "delete"].includes(action))) return;
  try {
    const response = await apiFetch("/api/client/manage", {
      method: "POST", headers: clientHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ target_id: targetId, action })
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Cihaz yönetimi uygulanamadı.");
    renderClients(data.clients || []);
    toast(action === "block" ? "Cihaz engellendi." : action === "unblock" ? "Cihaza erişim izni verildi." : action === "deny" ? "Erişim isteği reddedildi." : "Cihaz oturum listesinden silindi.");
  } catch (error) { toast(error.message); }
}

async function registerClientDetails() {
  const details = { client_id: clientId, model: "", platform: "", mobile: false, form_factors: [], public_ip: "", browser: "" };
  const publicIp = resolvePublicIpv4();
  const browserName = detectBrowserName();
  try {
    if (navigator.userAgentData?.getHighEntropyValues) {
      const values = await navigator.userAgentData.getHighEntropyValues(["model", "platform", "platformVersion", "formFactors"]);
      details.model = values.model || "";
      details.platform = values.platform || navigator.userAgentData.platform || "";
      details.mobile = Boolean(values.mobile ?? navigator.userAgentData.mobile);
      details.form_factors = Array.isArray(values.formFactors) ? values.formFactors.slice(0, 4) : [];
    }
  } catch {}
  details.platform ||= navigator.userAgentData?.platform || navigator.platform || "";
  details.mobile ||= Boolean(navigator.userAgentData?.mobile || /Android|iPhone|iPad|Mobile/i.test(navigator.userAgent));
  if (!details.model) {
    const patterns = [
      /Android\s[^;)]*;\s*([^;)]+?)\s+Build\//i,
      /Android\s[^;)]*;\s*([^;)]+?)(?:;\s*(?:wv|[a-z]{2}[-_][A-Z]{2})|\))/i,
      /;\s*((?:SM|GT|SCH|SGH|Pixel|CPH|RMX|V\d|M\d|TA)-?[A-Z0-9._-]+)\s+Build\//i
    ];
    const candidate = patterns.map((pattern) => navigator.userAgent.match(pattern)?.[1]?.trim()).find(Boolean) || "";
    if (candidate && !/^(?:K|Mobile|Tablet|wv)$/i.test(candidate)) details.model = candidate;
  }
  [details.public_ip, details.browser] = await Promise.all([publicIp, browserName]);
  try {
    const response = await apiFetch("/api/client", {
      method: "POST", headers: clientHeaders({ "Content-Type": "application/json" }), body: JSON.stringify(details)
    });
    const data = await response.json();
    if (response.status === 403) { renderAccessBlocked(); return; }
    if (response.ok) renderClients(data.clients || []);
  } catch {}
}

function historyTime(value) {
  const date = new Date(Number(value) * 1000);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString("tr-TR", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

function renderHistory(jobs = []) {
  const list = $("#historyList");
  if (!list) return;
  const signature = JSON.stringify(jobs);
  if (renderHistory.signature === signature) return;
  renderHistory.signature = signature;
  list.setAttribute("aria-busy", "false");
  $("#historyTitle").textContent = jobs.length ? `${jobs.length} son işlem` : "Henüz işlem geçmişi yok";
  list.innerHTML = jobs.length ? jobs.map((job) => `
    <article class="history-row">
      <div><b>${escapeHTML(job.filename)}</b><small>${historyTime(job.updated_at)} · ${job.status === "done" ? "Tamamlandı" : job.status === "error" ? "Hata" : "Hazır"}</small></div>
      <nav>
        ${job.can_reuse ? `<button type="button" data-history-reuse="${escapeHTML(job.job_id)}">Tekrar işle</button>` : ""}
        ${job.has_report ? `<button type="button" data-history-report="${escapeHTML(job.job_id)}" data-history-name="${escapeHTML(job.filename)}">Rapor</button>` : ""}
        ${job.status === "error" ? `<button type="button" data-history-diagnostic="${escapeHTML(job.job_id)}">Hata raporu</button>` : ""}
        ${job.has_output ? `<a href="/api/jobs/${escapeHTML(job.job_id)}/download?filename=${encodeURIComponent(job.output_filename || "APK-Cleaner-Studio-output.apk")}" download="${escapeHTML(job.output_filename || "APK-Cleaner-Studio-output.apk")}">İndir</a>` : ""}
        ${job.can_delete ? `<button type="button" class="history-delete" data-history-delete="${escapeHTML(job.job_id)}" data-history-name="${escapeHTML(job.filename)}">Sil</button>` : ""}
      </nav>
    </article>`).join("") : `<p class="fineprint">Tamamladığın paketler burada görünür. Kayıtlar yalnızca bu yerel cihazda tutulur.</p>`;
  $$('[data-history-reuse]').forEach((button) => button.addEventListener("click", () => loadHistoryJob(button.dataset.historyReuse)));
  $$('[data-history-report]').forEach((button) => button.addEventListener("click", () => openReportViewer(button.dataset.historyReport, button.dataset.historyName)));
  $$('[data-history-diagnostic]').forEach((button) => button.addEventListener("click", () => openDiagnosticViewer(button.dataset.historyDiagnostic)));
  $$('[data-history-delete]').forEach((button) => button.addEventListener("click", () => deleteHistoryJob(button.dataset.historyDelete, button.dataset.historyName)));
}

async function deleteHistoryJob(jobId, filename) {
  if (!await confirmAction("İşlem geçmişini sil", `${filename || "Bu işlem"} ve ilişkili yerel dosyalar kalıcı olarak silinsin mi?`, "Kalıcı olarak sil", true)) return;
  try {
    const response = await apiFetch(`/api/jobs/${jobId}/delete`, { method: "POST", headers: clientHeaders() });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "İşlem kaydı silinemedi.");
    renderHistory(data.jobs || []);
    toast("İşlem kaydı ve ilişkili dosyalar silindi.");
  } catch (error) { toast(error.message); }
}

async function refreshHistory() {
  if (!isUiActive() || state.historyInFlight) return;
  state.historyInFlight = true;
  try {
    const response = await apiFetch("/api/history", { cache: "no-store", headers: clientHeaders(), signal: uiReadController.signal });
    const data = await response.json();
    if (response.ok) renderHistory(data.jobs || []);
  } catch {}
  finally { state.historyInFlight = false; }
}

async function refreshStorage() {
  if (!$("#storageCard").open) return;
  try {
    const response = await apiFetch("/api/storage", { cache: "no-store", headers: clientHeaders() });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Depolama bilgisi okunamadı.");
    const totals = data.totals || {};
    $("#storageTitle").textContent = `${(data.jobs || []).length} yerel işlem kaydı`;
    $("#storageTotals").textContent = `Kaynak: ${humanSize(totals.source || 0)} · Çıktı: ${humanSize(totals.output || 0)} · Çalışma dosyaları: ${humanSize(totals.working || 0)}`;
    $("#storageList").innerHTML = (data.jobs || []).length ? data.jobs.map((job) => {
      const sizes = job.sizes || {};
      return `<label class="storage-row"><input type="checkbox" value="${escapeHTML(job.job_id)}" ${job.can_delete ? "" : "disabled"}><span><b>${escapeHTML(job.filename || "Paket")}</b><small>Kaynak ${humanSize(sizes.source || 0)} · Çıktı ${humanSize(sizes.output || 0)} · Çalışma ${humanSize(sizes.working || 0)}${job.can_delete ? "" : " · İşlem sürüyor"}</small></span></label>`;
    }).join("") : '<p class="fineprint">Temizlenecek işlem dosyası yok.</p>';
    $("#storageCleanButton").disabled = true;
    refreshNativeCacheStorage();
  } catch (error) { $("#storageTitle").textContent = error.message || "Depolama bilgisi okunamadı."; }
}

function refreshNativeCacheStorage() {
  const bridge = globalThis.AndroidThemeBridge;
  const area = $("#nativeCacheStorage");
  area.classList.toggle("hidden", !bridge?.getNativeCacheStorage);
  if (!bridge?.getNativeCacheStorage) return;
  try {
    const data = JSON.parse(bridge.getNativeCacheStorage());
    $("#nativeCacheTotals").textContent = `${Number(data.count || 0)} eski dosya · ${humanSize(data.bytes || 0)}. Son 24 saatte kullanılan dosyalar korunur.`;
    $("#nativeCacheCleanButton").disabled = !data.count;
  } catch { $("#nativeCacheTotals").textContent = "Önbellek bilgisi okunamadı."; }
}

async function cleanNativeCache() {
  if (!await confirmAction("Eski önbelleği temizle", "Yalnızca 24 saatten eski Android kurulum önbelleği dosyaları silinecek. Devam edilsin mi?", "Önbelleği temizle", true)) return;
  try {
    const result = JSON.parse(globalThis.AndroidThemeBridge?.clearNativeCache?.() || "{}");
    toast(`${Number(result.removed || 0)} eski önbellek dosyası temizlendi.`);
    refreshNativeCacheStorage();
  } catch { toast("Android önbelleği temizlenemedi."); }
}

async function cleanSelectedStorage() {
  const selected = $$('#storageList input:checked').map((item) => item.value).filter((id) => /^[a-f0-9]{32}$/.test(id));
  if (!selected.length) return;
  if (!await confirmAction("Seçili dosyaları temizle", `${selected.length} işlem kaydı, kaynak paketleri, çıktıları ve çalışma dosyalarıyla birlikte kalıcı olarak silinecek. Devam edilsin mi?`, "Kalıcı olarak sil", true)) return;
  const button = $("#storageCleanButton");
  button.disabled = true;
  let removed = 0;
  try {
    for (const id of selected) {
      const response = await apiFetch(`/api/jobs/${id}/delete`, { method: "POST", headers: clientHeaders() });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Dosyalar temizlenemedi.");
      removed++;
    }
    toast(`${removed} işlem kaydı temizlendi.`);
  } catch (error) { toast(`${removed} kayıt temizlendi. ${error.message}`); }
  finally { await Promise.all([refreshStorage(), refreshHistory()]); }
}

function refreshInstallHistory() {
  const card = $("#installHistoryCard");
  if (card.classList.contains("hidden") || !card.open) return;
  let rows = [];
  try { rows = JSON.parse(globalThis.AndroidThemeBridge?.getInstallHistory?.() || "[]"); } catch {}
  const list = $("#installHistoryList");
  list.innerHTML = rows.length ? rows.map((row) => {
    const success = row.status === "installed";
    const pending = row.status === "pending";
    const date = new Date(Number(row.timestamp || 0));
    const when = Number.isNaN(date.getTime()) ? "—" : date.toLocaleString("tr-TR", { dateStyle: "short", timeStyle: "short" });
    return `<article class="install-history-row ${success || pending ? "" : "failed"}"><b>${escapeHTML(row.package || "Split paketi")}</b><small>${when} · ${success ? "Kuruldu" : pending ? "Onay bekleniyor" : row.status === "cancelled" ? "İptal edildi" : "Başarısız"} · ${Number(row.modules || 0)} bileşen</small><small>${escapeHTML(row.message || "")}</small></article>`;
  }).join("") : '<p class="fineprint">Henüz doğrudan split kurulum kaydı yok.</p>';
}

async function loadHistoryJob(jobId) {
  try {
    const response = await apiFetch(`/api/jobs/${jobId}/reuse`, { method: "POST", cache: "no-store", headers: clientHeaders() });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Eski işlem açılamadı.");
    const analysis = data.analysis;
    state.file = null; state.jobId = data.job_id; state.analysis = analysis; state.operation = "patch";
    $("#diagnosticAfterFailure").classList.add("hidden");
    const badge = String(analysis.source_type || "apk").toUpperCase();
    $("#fileCard").innerHTML = `<div class="apk">${escapeHTML(badge)}</div><div><b>${escapeHTML(analysis.filename)}</b><span>${humanSize(analysis.size || 0)} · Geçmiş işlem yeniden açıldı</span></div>`;
    renderNetworks(analysis); renderSplitOptions(analysis.split_options);
    updateDirectSplitInstall(analysis);
    prepareCloneOption(analysis);
    $("#convertOperation").classList.toggle("hidden", !analysis.split_merged);
    $("#patchAds").checked = false; $("#patchAds").disabled = !analysis.network_count;
    setOperation(analysis.split_merged && !analysis.network_count ? "convert" : "patch");
    $("#scanProgress").classList.add("hidden"); $("#analysisContent").classList.remove("hidden");
    setStep(2); showView("#analysisView");
    $(".workspace").scrollIntoView({ behavior: "smooth", block: "start" });
    toast("Eski işlem yeniden açıldı; seçenekleri değiştirip tekrar çalıştırabilirsin.");
  } catch (error) { toast(error.message); }
}

async function refreshStatus() {
  if (state.statusInFlight || !isUiActive()) return;
  state.statusInFlight = true;
  try {
    const response = await apiFetch("/api/status", { cache: "no-store", headers: clientHeaders(), signal: uiReadController.signal }); const data = await response.json();
    if (response.status === 403) { renderAccessBlocked(); return; }
    state.toolchain = data.toolchain;
    state.platform = data.platform || "desktop";
    const connectionMarkup = `<i></i> ${data.channel === "dev" ? "Test kanalı" : "Yerel motor hazır"} · ${escapeHTML(data.engine_version ? `Motor v${data.engine_version}` : `v${data.version || "0.3"}`)}`;
    $("#connection").classList.add("online");
    if ($("#connection").innerHTML !== connectionMarkup) $("#connection").innerHTML = connectionMarkup;
    renderTools(data.toolchain);
    renderClients(data.clients || []);
  } catch (error) {
    if (error.name === "AbortError" || !isUiActive()) return;
    $("#connection").classList.remove("online"); $("#connection").innerHTML = "<i></i> Yerel motora ulaşılamıyor";
  }
  finally { state.statusInFlight = false; }
}

// Match the installed-app action menu's expansion/collapse rhythm.
const INLINE_REFLOW_MOTION = { duration: 360, easing: "cubic-bezier(.22,.61,.36,1)" };

function rememberUpdateLaunch(available) {
  try {
    if (available) sessionStorage.setItem("apk-cleaner-update-launch", location.pathname + location.search);
    else sessionStorage.removeItem("apk-cleaner-update-launch");
  } catch {}
}

function revealUpdateLaunch() {
  document.documentElement.classList.remove("update-launch-pending");
}

function appendReleaseNoteText(element, text) {
  // Release bodies are external Markdown, never trusted HTML.
  const tokens = /(`[^`]+`|\*\*[^*]+\*\*|\[[^\]]+\]\([^)]+\))/g;
  let offset = 0;
  for (const match of text.matchAll(tokens)) {
    element.append(document.createTextNode(text.slice(offset, match.index)));
    const token = match[0];
    let part;
    if (token.startsWith("`")) {
      part = document.createElement("code"); part.textContent = token.slice(1, -1);
    } else if (token.startsWith("**")) {
      part = document.createElement("strong"); part.textContent = token.slice(2, -2);
    } else {
      const [, label, address] = token.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
      let safe = false;
      try { const url = new URL(address); safe = url.protocol === "https:" && !url.username && !url.password; } catch {}
      part = document.createElement(safe ? "a" : "span"); part.textContent = label;
      if (safe) { part.href = address; part.target = "_blank"; part.rel = "noopener noreferrer"; }
    }
    element.append(part);
    offset = match.index + token.length;
  }
  element.append(document.createTextNode(text.slice(offset)));
}

function renderUpdateReleaseNotes(notes) {
  const body = $("#updateReleaseNotesBody");
  body.replaceChildren();
  const text = String(notes || "").slice(0, 32000).trim();
  if (!text) {
    const empty = document.createElement("p");
    empty.textContent = "Bu sürüm için sürüm notları bulunmuyor.";
    body.append(empty); return;
  }
  let list = null;
  let paragraph = [];
  const flush = () => {
    if (!paragraph.length) return;
    const p = document.createElement("p");
    appendReleaseNoteText(p, paragraph.join(" ")); body.append(p); paragraph = [];
  };
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || /^(?:---+|\*\*\*+)$/.test(line)) { flush(); list = null; continue; }
    const heading = line.match(/^#{1,6}\s+(.+)$/);
    const item = line.match(/^(?:[-*+]\s+|\d+[.)]\s+)(.+)$/);
    if (heading) {
      flush(); list = null;
      const h = document.createElement("h3"); appendReleaseNoteText(h, heading[1]); body.append(h);
    } else if (item) {
      flush();
      if (!list) { list = document.createElement("ul"); body.append(list); }
      const li = document.createElement("li"); appendReleaseNoteText(li, item[1]); list.append(li);
    } else if (line.startsWith(">")) {
      flush(); list = null;
      const p = document.createElement("p"); p.className = "release-note-callout";
      appendReleaseNoteText(p, line.replace(/^>\s*/, "")); body.append(p);
    } else {
      list = null; paragraph.push(line);
    }
  }
  flush();
}

let updateNoticeAnimation = null;
const inlineDisclosureAnimations = new WeakMap();
let updateNoticeFocusPending = true;

function focusUpdateNoticeOnLaunch() {
  if (!updateNoticeFocusPending || document.readyState !== "complete" || !state.update) return;
  const notice = $("#updateNotice");
  if (notice.classList.contains("hidden")) return;
  updateNoticeFocusPending = false;
  if (!isUiActive() || state.updateBusy || state.jobRunning || pageScrollLocks.size) { revealUpdateLaunch(); return; }
  const version = notice.dataset.version;
  // Wait for the browser's load-time scroll restoration and the new panel's
  // layout. Ordinary polling must never interrupt the user's scroll position.
  requestAnimationFrame(() => requestAnimationFrame(() => {
    if (!isUiActive() || state.updateBusy || state.jobRunning || pageScrollLocks.size
        || notice.classList.contains("hidden") || notice.dataset.version !== version
        || state.dismissedUpdateVersion === version) { revealUpdateLaunch(); return; }
    window.scrollTo({ top: 0, left: 0, behavior: "instant" });
    revealUpdateLaunch();
  }));
}

function cancelUpdateNoticeMotion() {
  const animation = updateNoticeAnimation;
  updateNoticeAnimation = null;
  animation?.cancel();
  const notice = $("#updateNotice");
  notice.classList.remove("is-closing");
  notice.inert = false;
}

function resetUpdateNotes() {
  setInlineDisclosureOpen($("#updateReleaseNotes"), false);
}

function setInlineDisclosureOpen(details, expanded) {
  const animation = inlineDisclosureAnimations.get(details);
  inlineDisclosureAnimations.delete(details);
  animation?.cancel();
  details.classList.remove("is-animating");
  delete details.dataset.expanded;
  details.open = expanded;
  details.querySelector("summary").setAttribute("aria-expanded", String(expanded));
}

function toggleUpdateNotes(event) {
  toggleInlineDisclosure($("#updateReleaseNotes"), event);
}

function handleInlineDisclosureClick(event) {
  if (event.defaultPrevented) return;
  const summary = event.target.closest?.("summary");
  const details = summary?.parentElement;
  if (details?.tagName !== "DETAILS" || summary !== details.querySelector("summary")) return;
  // Links or controls embedded in a summary retain their own action. Event
  // delegation also covers disclosures created later, without double toggles.
  if (event.target.closest("a, button, input, select, textarea")) return;
  if (details === $("#updateReleaseNotes")) toggleUpdateNotes(event);
  else toggleInlineDisclosure(details, event);
}

function toggleInlineDisclosure(details, event) {
  event.preventDefault();
  const startHeight = details.getBoundingClientRect().height;
  const previous = inlineDisclosureAnimations.get(details);
  const expanded = previous ? details.dataset.expanded !== "true" : !details.open;
  inlineDisclosureAnimations.delete(details);
  previous?.cancel();
  details.classList.remove("is-animating");
  details.open = expanded;
  details.dataset.expanded = String(expanded);
  details.querySelector("summary").setAttribute("aria-expanded", String(expanded));
  if (motionMedia.matches || !isUiActive() || typeof details.animate !== "function") return;
  const endHeight = details.getBoundingClientRect().height;
  // Keep the body rendered until the closing transition finishes. Reversals
  // start at the current animated height, not at either full-size endpoint.
  details.open = true;
  details.classList.add("is-animating");
  const animation = details.animate([
    { height: `${startHeight}px` }, { height: `${endHeight}px` },
  ], { ...INLINE_REFLOW_MOTION, fill: "both" });
  inlineDisclosureAnimations.set(details, animation);
  animation.finished.then(() => {
    if (inlineDisclosureAnimations.get(details) !== animation) return;
    inlineDisclosureAnimations.delete(details);
    details.open = expanded;
    details.classList.remove("is-animating");
    animation.cancel();
  }, () => {});
}

function renderAvailableUpdate(update) {
  rememberUpdateLaunch(true);
  state.update = update;
  if (state.dismissedUpdateVersion === update.latest_version) return;
  const notice = $("#updateNotice");
  cancelUpdateNoticeMotion();
  if (notice.dataset.version !== update.latest_version) resetUpdateNotes();
  $("#updateTitle").textContent = `APK Cleaner Studio v${update.latest_version}`;
  const isDev = update.release_channel === "dev" || update.latest_version.includes("-dev.");
  $("#updateText").textContent = update.notes || (isDev
    ? "Yeni test sürümü kullanıma hazır. Güncelleme notlarına aşağıdan ulaşabilirsiniz."
    : "Yeni sürüm kullanıma hazır. Güncelleme notlarına aşağıdan ulaşabilirsiniz.");
  renderUpdateReleaseNotes(update.release_notes);
  const button = $("#updateDownload");
  const target = update.download_url || update.release_url;
  button.classList.toggle("hidden", !target);
  const label = update.automatic
    ? (update.install_mode === "android" ? "İndir ve yükle" : "Güncelle ve yeniden başlat")
    : "Sürüm sayfasını aç";
  button.dataset.defaultLabel = label;
  button.textContent = label;
  button.disabled = false;
  notice.dataset.version = update.latest_version;
  notice.classList.remove("hidden");
  focusUpdateNoticeOnLaunch();
}

function dismissUpdateNotice() {
  const notice = $("#updateNotice");
  if (updateNoticeAnimation || notice.classList.contains("hidden")) return;
  state.dismissedUpdateVersion = notice.dataset.version || "";
  revealUpdateLaunch();
  if (motionMedia.matches || !isUiActive() || typeof notice.animate !== "function") {
    notice.classList.add("hidden");
    resetUpdateNotes();
    return;
  }
  const style = getComputedStyle(notice);
  notice.classList.add("is-closing");
  notice.inert = true;
  const animation = notice.animate([
    { height: `${notice.getBoundingClientRect().height}px`, opacity: 1, transform: "translateY(0)",
      paddingTop: style.paddingTop, paddingBottom: style.paddingBottom,
      marginTop: style.marginTop, marginBottom: style.marginBottom,
      borderTopWidth: style.borderTopWidth, borderBottomWidth: style.borderBottomWidth },
    { height: "0px", opacity: 0, transform: "translateY(-6px)", paddingTop: "0px", paddingBottom: "0px",
      marginTop: "0px", marginBottom: "0px", borderTopWidth: "0px", borderBottomWidth: "0px" },
  ], { ...INLINE_REFLOW_MOTION, fill: "both" });
  updateNoticeAnimation = animation;
  animation.finished.then(() => {
    if (updateNoticeAnimation !== animation) return;
    notice.classList.add("hidden");
    resetUpdateNotes();
    cancelUpdateNoticeMotion();
  }, () => {});
}

function restoreUpdateNotice() {
  if (state.updateBusy) return;
  state.dismissedUpdateVersion = "";
  updateNoticeFocusPending = true;
  cancelUpdateNoticeMotion();
  resetUpdateNotes();
  if (state.update) renderAvailableUpdate(state.update);
  // A suspended read may still be unwinding its abort when Android resumes.
  if (state.updateCheckInFlight) state.updateCheckOnResume = true;
  else checkForUpdates();
}

async function checkForUpdates() {
  if (state.updateBusy || state.updateCheckInFlight) return;
  state.updateCheckInFlight = true;
  try {
    const response = await apiFetch("/api/update", { cache: "no-store", headers: clientHeaders() });
    const data = await response.json();
    const update = data.update;
    if (!response.ok) { rememberUpdateLaunch(false); revealUpdateLaunch(); updateNoticeFocusPending = false; return; }
    if (state.updateBusy) return;
    if (!data.available || !update) {
      rememberUpdateLaunch(false);
      revealUpdateLaunch();
      state.update = null;
      updateNoticeFocusPending = false;
      cancelUpdateNoticeMotion();
      resetUpdateNotes();
      $("#updateNotice").classList.add("hidden");
      return;
    }
    renderAvailableUpdate(update);
  } catch {
    if (!state.updateCheckOnResume) {
      rememberUpdateLaunch(false);
      revealUpdateLaunch();
      updateNoticeFocusPending = false;
    }
  }
  finally {
    state.updateCheckInFlight = false;
    if (state.updateCheckOnResume) {
      state.updateCheckOnResume = false;
      if (isUiActive() && !state.updateBusy) checkForUpdates();
    }
  }
}

function openUpdateLink(address) {
  if (!address) return;
  const link = document.createElement("a");
  link.href = address; link.target = "_blank"; link.rel = "noopener noreferrer";
  document.body.append(link); link.click(); link.remove();
}

async function applyAvailableUpdate() {
  const update = state.update;
  const button = $("#updateDownload");
  if (!update || state.updateBusy) return;
  if (!update.automatic) {
    openUpdateLink(update.download_url || update.release_url);
    return;
  }
  state.updateBusy = true;
  button.disabled = true;
  button.textContent = "Güncelleme hazırlanıyor…";
  if (update.install_mode === "android" && globalThis.AndroidThemeBridge?.installUpdate) {
    globalThis.AndroidThemeBridge.installUpdate(update.download_url, update.filename, update.sha256);
    return;
  }
  try {
    const response = await apiFetch("/api/update/apply", { method: "POST", headers: clientHeaders() });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Güncelleme başlatılamadı.");
    if (result.status === "manual") {
      state.updateBusy = false; button.disabled = false; button.textContent = button.dataset.defaultLabel || "Sürüm sayfasını aç";
      openUpdateLink(result.url || update.download_url || update.release_url);
      return;
    }
    button.textContent = "Yeniden başlatılıyor…";
    $("#updateText").textContent = "Paket doğrulandı. Uygulama yeni sürümle yeniden başlatılıyor.";
  } catch (error) {
    state.updateBusy = false; button.disabled = false; button.textContent = button.dataset.defaultLabel || "Yeniden dene";
    toast(error.message || "Güncelleme tamamlanamadı.");
  }
}

function renderTools(tools) {
  const rows = [
    ["java", state.platform === "android" ? "Gömülü çalışma ortamı" : "Java çalışma ortamı", tools.java], ["dex_tools", "Doğrudan DEX motoru", tools.dex_tools], ["manifest_tool", "Manifest ve XML", tools.manifest_tool],
    ["split_tool", "Split birleştirici", tools.split_tool], ["signer", "APK imzalayıcı", tools.signer], ["zipalign", "APK optimizasyonu", tools.zipalign]
  ];
  rows.forEach(([key, name, ok]) => {
    let row = $(`#toolList [data-tool="${key}"]`);
    if (!row) {
      row = document.createElement("div");
      row.className = "tools-row"; row.dataset.tool = key;
      row.innerHTML = `<span>${name}</span><span></span>`;
      $("#toolList").append(row);
    }
    row.classList.remove("pending"); row.classList.toggle("ok", Boolean(ok));
    row.lastElementChild.textContent = ok ? "HAZIR" : "EKSİK";
  });
  const setupButton = $("#setupButton");
  $("#toolList").setAttribute("aria-busy", "false");
  const setupNeeded = !(tools.fully_ready && tools.zipalign);
  setupButton.classList.remove("setup-pending");
  setupButton.classList.toggle("setup-hidden", !setupNeeded);
  setupButton.disabled = !setupNeeded;
  setupButton.setAttribute("aria-hidden", String(!setupNeeded));
  $("#optimizeApk").disabled = !tools.zipalign;
  $("#optimizeApk").closest(".option").classList.toggle("option-unavailable", !tools.zipalign);
}

function renderNetworks(analysis) {
  $(".network-card").classList.toggle("network-card--scrollable", analysis.detections.length > 7);
  $("#networkTitle").textContent = analysis.network_count ? `${analysis.network_count} reklam ağı tespit edildi` : "Bilinen reklam ağı bulunamadı";
  $("#networkList").innerHTML = analysis.detections.length
    ? analysis.detections.map((item) => `<div class="network">${StudioUI.networkBadge(item.id)}<b>${escapeHTML(item.label)}</b><i>${Number(item.references) || 0} REFERANS</i></div>`).join("")
    : "<p>Bilinen reklam ağı bulunmadı. Split dönüştürme ve isteğe bağlı iyileştirmeler kullanılabilir.</p>";
  const manifestCount = Object.values(analysis.manifest_hits || {}).reduce((a, b) => a + b, 0);
  const layoutCount = (analysis.layout_hits || []).length;
  $("#analysisSummary").innerHTML = `<span><b>${analysis.dex_count}</b> DEX dosyası</span><span><b>${analysis.network_count}</b> reklam ağı</span><span><b>${manifestCount}</b> manifest referansı</span><span><b>${layoutCount}</b> XML adayı</span><span><b>${analysis.split_merged ? "EVET" : "HAYIR"}</b> split birleşimi</span>`;
  const checks = analysis.install_source_checks || [];
  const sourceIntegrityRisk = Boolean(analysis.source_integrity_risk);
  const splitRequired = Boolean(analysis.requires_splits && !analysis.split_merged);
  $("#integrityNotice").classList.toggle("hidden", !checks.length && !splitRequired);
  if (splitRequired) {
    $("#integrityNotice p").innerHTML = "<b>Split dağıtım metadata’sı algılandı.</b> Paket işlenebilir; ancak gerçekten eksik bir split bileşeni varsa çıktı kurulmayabilir. Böyle bir durumda uygulamanın özgün APKS, APKM veya XAPK paketini kullan.";
    $("#integrityNotice p").title = "Split paket gerekli";
  } else if (sourceIntegrityRisk) {
    $("#integrityNotice p").innerHTML = "<b>Play Store kaynak veya bütünlük denetimi riski algılandı.</b> Paket farklı bir imzayla yeniden oluşturulduğunda kurulumdan sonra Play Store’a yönlendirme yapabilir ya da kullanımı sınırlayabilir. APK Cleaner Studio bu denetimi değiştirmez; kaldırılması uygulamaya özel ileri tersine mühendislik çalışması gerektirebilir.";
    $("#integrityNotice p").title = checks.join(" · ");
  } else {
    $("#integrityNotice p").innerHTML = "<b>Mağaza paket referansı algılandı.</b> Bu bulgu tek başına etkin bir koruma bulunduğunu kanıtlamaz. Ayrıntılar işlem raporuna eklenir; doğrulama mekanizması değiştirilmez.";
    $("#integrityNotice p").title = checks.join(" · ");
  }
  const messageCandidates = analysis.message_ui_candidates || [];
  const messageNotice = $("#messageUiNotice");
  messageNotice.classList.toggle("hidden", !analysis.dex_count);
  if (analysis.dex_count) {
    const summary = messageCandidates
      .map((item) => `${escapeHTML(item.label)}: ${Number(item.references) || 0}`)
      .join(" · ");
    messageNotice.querySelector("p").innerHTML = `<b>Başlangıç mesajı denetimi.</b> Diyalog veya Toast başlatan Activity çağrılarını orijinal APK yüklemeden inceleyebilirsin. Adaylar otomatik kaldırılmaz; yalnızca seçtiğin çağrılar işlenir.`;
    messageNotice.querySelector("p").title = summary;
  }
}

function renderSplitOptions(options) {
  const abis = options?.abis || [];
  const languages = options?.languages || [];
  $("#splitSelector").classList.toggle("hidden", !options || (!abis.length && !languages.length));
  state.splitSelection = { abis: [...abis], languages: languages.map((item) => item.code) };
  const labels = { "arm64-v8a": "ARM64", "armeabi-v7a": "ARMv7", x86: "x86", "x86_64": "x86_64" };
  $("#abiChoices").innerHTML = abis.map((abi) => `<label class="split-choice"><input type="checkbox" data-split-abi value="${escapeHTML(abi)}" checked><span class="choice-check" aria-hidden="true"></span><span class="choice-copy"><b>${escapeHTML(labels[abi] || abi)}</b><small>${escapeHTML(options.recommended_densities?.[abi] || "Otomatik DPI")}</small></span><i>SEÇİLİ</i></label>`).join("");
  $("#languageGroup").classList.toggle("hidden", !languages.length);
  $("#languageChoices").innerHTML = languages.map((item) => `<label class="split-choice"><input type="checkbox" data-split-language value="${escapeHTML(item.code)}" checked><span class="choice-check" aria-hidden="true"></span><span class="choice-copy"><b>${escapeHTML(item.label)}</b><small>${escapeHTML(item.code.toUpperCase())} dil paketi</small></span><i>SEÇİLİ</i></label>`).join("");
  updateSplitSelection(options);
  $$('[data-split-abi], [data-split-language]').forEach((input) => input.addEventListener("change", () => updateSplitSelection(options)));
}

function updateSplitSelection(options = state.analysis?.split_options) {
  state.splitSelection.abis = $$('[data-split-abi]:checked').map((input) => input.value);
  state.splitSelection.languages = $$('[data-split-language]:checked').map((input) => input.value);
  const densities = state.splitSelection.abis.map((abi) => options?.recommended_densities?.[abi]).filter(Boolean);
  $("#densityHint").textContent = densities.length ? `Otomatik DPI: ${[...new Set(densities)].join(", ")}` : "Paket mimari ayrımı içeriyorsa en az bir işlemci mimarisi seçilmelidir.";
}

function setOperation(operation, toggle = false) {
  if (toggle && operation === "patch" && state.analysis && !state.analysis.network_count) {
    toast("Bu pakette desteklenen reklam SDK’sı bulunmadı; reklam yaması uygulanamaz.");
    return;
  }
  if (toggle && operation === "clone" && !state.analysis?.package_name) {
    toast("Paket adı okunamadığı için bu pakette klonlama kullanılamıyor.");
    return;
  }
  if (operation === "patch") {
    const hasAds = Number(state.analysis?.network_count || 0) > 0;
    const hasConvertChoice = Boolean(state.analysis?.split_merged);
    const canClearStandalonePatch = toggle && !hasConvertChoice && state.operation === "patch" && state.patchAdsSelected;
    state.patchAdsSelected = canClearStandalonePatch
      ? false
      : hasAds || !state.analysis;
    const description = $("#patchOperationDescription");
    if (description) {
      description.textContent = state.analysis && !hasAds
        ? "Bu pakette desteklenen reklam SDK’sı bulunmadı; reklam yaması uygulanamaz."
        : hasConvertChoice
        ? "Doğrulanmış DEX çağrılarını, manifest kayıtlarını ve XML reklam alanlarını düzenler. Tek APK oluşturma seçeneğiyle bunun arasında geçiş yapabilirsin."
        : "Doğrulanmış DEX çağrılarını, manifest kayıtlarını ve XML reklam alanlarını düzenler. İstemiyorsan tekrar dokunarak kapatabilirsin.";
    }
  }
  state.operation = operation;
  $$(".operation").forEach((item) => {
    const selected = item.dataset.operation === operation && (operation !== "patch" || state.patchAdsSelected);
    item.classList.toggle("selected", selected);
    item.setAttribute("aria-pressed", String(selected));
  });
  const converting = operation === "convert";
  const combining = converting || operation === "clone";
  $("#convertPatchOption").classList.toggle("hidden", !combining);
  $("#combinedPatchTitle").textContent = converting ? "Dönüştürme sırasında reklam yaması uygula" : "Klonlama sırasında reklam yaması uygula";
  $("#cloneOptions").classList.toggle("hidden", operation !== "clone");
  $("#profileSection").classList.toggle("soft-disabled", combining && !$("#patchAds").checked);
  updateActionState();
}

function prepareCloneOption(analysis) {
  const original = String(analysis?.package_name || "");
  $("#originalPackageName").textContent = original || "Paket adı okunamadı";
  $("#clonePackageName").value = original ? String(analysis.suggested_clone_package_name || `${original}.clone`) : "";
  $("#cloneOperation").classList.toggle("operation-unavailable", !original);
  $("#cloneOperation").setAttribute("aria-disabled", String(!original));
  $("#cloneAvailabilityNote").classList.toggle("hidden", Boolean(original));
  $("#cloneOperation").title = original ? "" : "Paket adı okunamadığı için klonlama kullanılamıyor.";
}

function updateDirectSplitInstall(analysis) {
  clearDirectSplitPlan();
  state.splitInstallRequestJobId = null;
  state.nativeSplitInstallBusy = false;
  state.splitInstallSubmitted = false;
  $("#directSplitInstallButton").disabled = false;
  $("#directSplitInstallButton").textContent = "Bileşenleri incele";
  const supported = document.documentElement.dataset.embedded === "android"
    && ["apks", "apkm", "xapk"].includes(String(analysis?.source_type || "").toLowerCase());
  $("#directSplitInstall").classList.toggle("hidden", !supported);
}

function clearDirectSplitPlan() {
  state.splitInstallPlan = null;
  $("#directSplitPlan").classList.add("hidden");
  $("#directSplitModules").replaceChildren();
}

function chosenDirectSplitModules() {
  return $$("#directSplitModules input[type=checkbox]:checked").map((input) => input.value);
}

function updateDirectSplitSummary() {
  const plan = state.splitInstallPlan;
  if (!plan) return;
  const selected = new Set(chosenDirectSplitModules());
  const selectedModules = plan.modules.filter((module) => selected.has(module.name));
  const bytes = selectedModules.reduce((sum, module) => sum + Number(module.size || 0), 0);
  $("#directSplitSelectionSummary").textContent = `${selectedModules.length} / ${plan.modules.length} bileşen · ${humanSize(bytes)} · Özgün imza korunur`;
  const blocked = String(plan.blocked_reason || "");
  $("#directSplitWarning").textContent = blocked || ($("input[name=directSplitMode]:checked").value === "manual"
    ? "Temel APK zorunludur; alternatif temel APK aynı kuruluma eklenemez. Gerekli bir split bileşenini çıkarırsan kurulum veya uygulamanın açılışı başarısız olabilir." : "");
  $("#directSplitWarning").classList.toggle("hidden", !$("#directSplitWarning").textContent);
  $("#directSplitConfirm").disabled = Boolean(blocked) || state.nativeSplitInstallBusy || state.splitInstallSubmitted
    || !selected.has(plan.modules.find((module) => module.required)?.name);
}

function renderDirectSplitPlan(plan) {
  state.splitInstallPlan = plan;
  state.splitInstallSubmitted = false;
  $("#directSplitPlan").classList.remove("hidden");
  $("#directSplitPackageSummary").textContent = `${plan.package} · sürüm ${plan.version} (${plan.version_code}) · ${plan.installed ? "Mevcut kurulum güncellenecek" : "Yeni kurulum"} · ${plan.signature_status}`;
  $("input[name=directSplitMode][value=auto]").checked = true;
  const list = $("#directSplitModules");
  list.replaceChildren();
  const labels = { base: "Temel APK", abi: "İşlemci", density: "Ekran yoğunluğu", language: "Dil", feature: "Özellik", alternative: "Alternatif temel APK" };
  for (const splitModule of plan.modules) {
    const row = document.createElement("label");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox"; checkbox.value = splitModule.name; checkbox.checked = Boolean(splitModule.auto);
    checkbox.disabled = true;
    checkbox.dataset.required = String(Boolean(splitModule.required));
    checkbox.dataset.alternative = String(splitModule.kind === "alternative");
    const name = document.createElement("span"); name.textContent = splitModule.name;
    const kind = document.createElement("small"); kind.textContent = labels[splitModule.kind] || "Bileşen";
    row.append(checkbox, name, kind);
    list.append(row);
  }
  updateDirectSplitSummary();
  $("#directSplitPlan").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function validClonePackageName() {
  const original = String(state.analysis?.package_name || "");
  const proposed = $("#clonePackageName").value.trim();
  return proposed !== original && proposed.length <= 200 && /^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)+$/.test(proposed);
}

function updateAdProfileAvailability(enabled = null) {
  const hasAds = Number(state.analysis?.network_count || 0) > 0;
  $("#patchAvailabilityNote").textContent = state.analysis?.split_merged
    ? "Bu pakette desteklenen bir reklam SDK’sı bulunmadı. Reklam yaması uygulanamaz; split paketi yine tek APK’ya dönüştürebilirsin."
    : "Bu pakette desteklenen bir reklam SDK’sı bulunmadı. Reklam yaması uygulanamaz; diğer bağımsız iyileştirmeleri kullanabilirsin.";
  $("#patchAvailabilityNote").classList.toggle("hidden", hasAds || !state.analysis);
  $("[data-operation='patch']").classList.toggle("operation-unavailable", !hasAds && Boolean(state.analysis));
  $("[data-operation='patch']").setAttribute("aria-disabled", String(!hasAds && Boolean(state.analysis)));
  const profilesEnabled = hasAds && (enabled === null ? true : Boolean(enabled));
  $$(".profile").forEach((button) => {
    button.disabled = !profilesEnabled;
    button.setAttribute("aria-disabled", String(!profilesEnabled));
    button.classList.toggle("selected", profilesEnabled && button.dataset.profile === state.profile);
  });
  $("#noAdsProfileNote").classList.toggle("hidden", hasAds);
  if (!hasAds) {
    state.patchAdsSelected = false;
    $("#patchAds").checked = false;
    $("#patchAds").disabled = true;
  } else {
    $("#patchAds").disabled = false;
    if (!state.profile) state.profile = "balanced";
  }
}

function updateActionState() {
  if (!state.analysis) return;
  const hasAds = Number(state.analysis.network_count || 0) > 0;
  const wantsAds = hasAds && ((state.operation === "patch" && state.patchAdsSelected) || (state.operation !== "patch" && $("#patchAds").checked));
  updateAdProfileAvailability(wantsAds);
  const hasIndependentPatch = $("#stripDebug").checked || $("#normalizeDex").checked || $("#optimizeApk").checked || $("#deobfuscateResources").checked || state.messageTargets.length > 0;
  const canRun = state.operation === "clone" ? validClonePackageName() : state.operation === "convert" || wantsAds || hasIndependentPatch;
  $("#profileSection").classList.toggle("soft-disabled", !wantsAds);
  $(".manifest-note").classList.toggle("hidden", !wantsAds || state.profile === "safe");
  $("#cleanButton").disabled = !canRun;
  if (state.operation === "clone") {
    $("#cleanButton").innerHTML = `Klonlamayı başlat ${ACTION_NEXT_ICON}`;
  } else if (state.operation === "convert") {
    $("#cleanButton").innerHTML = `APK oluşturmayı başlat ${ACTION_NEXT_ICON}`;
  } else if (wantsAds) {
    $("#cleanButton").innerHTML = `Temizlemeyi başlat ${ACTION_NEXT_ICON}`;
  } else {
    $("#cleanButton").innerHTML = `Seçili işlemleri başlat ${ACTION_NEXT_ICON}`;
  }
}

function readSavedPresets() {
  try {
    const parsed = JSON.parse(localStorage.getItem(SAVED_PRESETS_KEY) || "[]");
    return Array.isArray(parsed) ? parsed.filter((item) => item && typeof item.id === "string" && typeof item.name === "string" && item.options && typeof item.options === "object").slice(0, 12) : [];
  } catch { return []; }
}

function renderSavedPresets(selectedId = $("#savedPresetSelect").value) {
  const select = $("#savedPresetSelect");
  select.replaceChildren(new Option("Profil seç", ""));
  for (const preset of readSavedPresets()) select.add(new Option(preset.name, preset.id));
  select.value = [...select.options].some((option) => option.value === selectedId) ? selectedId : "";
  $("#applyPresetButton").disabled = !select.value;
  $("#deletePresetButton").disabled = !select.value;
}

function currentPresetOptions() {
  return {
    operation: state.operation,
    profile: state.profile,
    patchAds: state.operation !== "patch" ? $("#patchAds").checked : state.patchAdsSelected,
    stripDebug: $("#stripDebug").checked,
    normalizeDex: $("#normalizeDex").checked,
    optimizeApk: $("#optimizeApk").checked,
    deobfuscateResources: $("#deobfuscateResources").checked,
  };
}

function applySavedPreset() {
  const preset = readSavedPresets().find((item) => item.id === $("#savedPresetSelect").value);
  if (!preset || !state.analysis) return;
  const options = preset.options;
  const hasAds = Number(state.analysis.network_count || 0) > 0;
  const canConvert = Boolean(state.analysis.split_merged);
  const operation = options.operation === "clone" && state.analysis.package_name ? "clone" : options.operation === "convert" && canConvert ? "convert" : "patch";
  state.profile = ["safe", "balanced", "deep"].includes(options.profile) ? options.profile : "balanced";
  setOperation(operation);
  state.patchAdsSelected = hasAds && Boolean(options.patchAds);
  $("#patchAds").checked = hasAds && Boolean(options.patchAds);
  for (const [key, selector] of Object.entries({
    stripDebug: "#stripDebug", normalizeDex: "#normalizeDex", optimizeApk: "#optimizeApk", deobfuscateResources: "#deobfuscateResources"
  })) $(selector).checked = Boolean(options[key]);
  $$(".operation").forEach((button) => {
    const selected = button.dataset.operation === operation && (operation !== "patch" || state.patchAdsSelected);
    button.classList.toggle("selected", selected);
    button.setAttribute("aria-pressed", String(selected));
  });
  updateActionState();
  toast(options.operation === "clone" && !state.analysis.package_name
    ? "Paket adı okunamadı; klonlama seçeneği uygulanamadı."
    : options.operation === "convert" && !canConvert
    ? "Bu paket split değil; profilin diğer seçenekleri uygulandı."
    : !hasAds && options.patchAds ? "Reklam ağı bulunmadı; profilin diğer seçenekleri uygulandı." : "İşlem profili uygulandı.");
}

async function saveCurrentPreset() {
  if (!state.analysis) return;
  const name = await openAppDialog({
    title: "İşlem profilini kaydet", message: "Bu cihazda tekrar kullanmak için kısa bir ad ver.",
    confirmText: "Kaydet", eyebrow: "İŞLEM PROFİLİ", mode: "prompt"
  });
  if (name === null) return;
  const cleanName = name.replace(/\s+/g, " ").trim();
  if (!cleanName || cleanName.length > 40) return toast("Profil adı 1–40 karakter olmalı.");
  const presets = readSavedPresets();
  const previous = presets.find((item) => item.name.toLocaleLowerCase("tr-TR") === cleanName.toLocaleLowerCase("tr-TR"));
  if (previous && !(await confirmAction("Profil güncellensin mi?", `${previous.name} adlı kayıtlı profil mevcut seçeneklerle değiştirilecek.`, "Güncelle"))) return;
  if (!previous && presets.length >= 12) return toast("En fazla 12 işlem profili kaydedilebilir.");
  const entry = { id: previous?.id || globalThis.crypto?.randomUUID?.() || `preset-${Date.now()}`, name: cleanName, options: currentPresetOptions() };
  const updated = previous ? presets.map((item) => item.id === previous.id ? entry : item) : [...presets, entry];
  try { localStorage.setItem(SAVED_PRESETS_KEY, JSON.stringify(updated)); }
  catch { return toast("Profil bu cihazda kaydedilemedi."); }
  renderSavedPresets(entry.id);
  toast("İşlem profili kaydedildi.");
}

async function deleteSavedPreset() {
  const selected = $("#savedPresetSelect").value;
  const presets = readSavedPresets();
  const preset = presets.find((item) => item.id === selected);
  if (!preset || !(await confirmAction("Profil silinsin mi?", `${preset.name} adlı işlem profili yalnızca bu cihazdan kaldırılacak.`, "Sil", true))) return;
  try { localStorage.setItem(SAVED_PRESETS_KEY, JSON.stringify(presets.filter((item) => item.id !== selected))); }
  catch { return toast("Profil kaldırılamadı."); }
  renderSavedPresets("");
  toast("İşlem profili silindi.");
}

function prepareAnalysisView(name, size, split = false) {
  state.operation = "patch"; setStep(2); showView("#analysisView");
  const ext = extension(name) || ".apk";
  $("#fileCard").innerHTML = `<div class="apk">${escapeHTML(ext.slice(1).toUpperCase())}</div><div><b>${escapeHTML(name)}</b><span>${humanSize(size)} · ${split ? "Split modüller birleştirilecek" : "Yerel analiz"}</span></div>`;
  $("#scanProgress").classList.remove("hidden"); $("#analysisContent").classList.add("hidden");
}

function applyAnalysisResult(data) {
  state.messageTargets = []; state.messageCandidates = [];
  state.jobId = data.job_id; state.analysis = data.analysis; renderNetworks(data.analysis); renderSplitOptions(data.analysis.split_options);
  $("#diagnosticAfterFailure").classList.add("hidden");
  updateDirectSplitInstall(data.analysis);
  prepareCloneOption(data.analysis);
  $("#convertOperation").classList.toggle("hidden", !data.analysis.split_merged);
  $("#patchAds").checked = false; $("#patchAds").disabled = !data.analysis.network_count;
  updateAdProfileAvailability();
  setOperation(data.analysis.split_merged && !data.analysis.network_count ? "convert" : "patch");
  $("#scanProgress").classList.add("hidden"); $("#analysisContent").classList.remove("hidden");
}

globalThis.onInstalledPackageImported = (payload) => {
  try {
    const data = JSON.parse(payload);
    if (data.error) throw new Error(data.error);
    const file = data.native_file || { name: "installed-app.apk", size: 0 };
    state.file = { name: file.name, size: Number(file.size || 0), installed: true };
    prepareAnalysisView(file.name, Number(file.size || 0), isSplit(file.name));
    applyAnalysisResult(data);
  } catch (error) { toast(error.message || "Yüklü uygulama alınamadı."); reset(); }
};

async function acceptFile(file) {
  const ext = file ? extension(file.name) : "";
  if (!file || !ext) return toast("Lütfen .apk, .apks, .apkm veya .xapk dosyası seç.");
  if (file.size > MAX_UPLOAD_BYTES) return toast("Paket 1 GB sınırını aşıyor.");
  state.file = file; prepareAnalysisView(file.name, file.size, isSplit(file.name));
  const form = new FormData(); form.append("package", file);
  try {
    const response = await apiFetch("/api/analyze", { method: "POST", headers: clientHeaders(), body: form }); const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Analiz başarısız.");
    applyAnalysisResult(data);
  } catch (error) { toast(error.message); reset(); }
}

function renderProgress(value) {
  progressElements.ring.style.setProperty("--p", `${value.toFixed(2)}%`);
  const label = `${Math.floor(value)}%`;
  if (progressElements.value.textContent !== label) progressElements.value.textContent = label;
  progressElements.bar.style.transform = `scaleX(${value / 100})`;
}

function animateProgress(timestamp = 0) {
  state.progressFrame = 0;
  if (!isUiActive()) return;
  if (state.displayedProgress >= state.targetProgress) return;
  const elapsed = state.progressLastTick ? timestamp - state.progressLastTick : 0;
  state.progressLastTick = timestamp;
  state.displayedProgress = StudioUI.advanceProgress(state.displayedProgress, state.targetProgress, elapsed);
  renderProgress(state.displayedProgress);
  if (state.displayedProgress < state.targetProgress) state.progressFrame = requestAnimationFrame(animateProgress);
}

function updateProgress(progress, message) {
  const value = Math.max(state.displayedProgress, Math.min(100, Math.round(progress)));
  state.targetProgress = Math.max(state.targetProgress, value);
  progressElements.phase.textContent = message;
  progressElements.log.textContent = `✓ Orijinal paket korunuyor\n● ${message}`;
  if (motionMedia.matches || !isUiActive()) {
    state.displayedProgress = state.targetProgress;
    renderProgress(state.displayedProgress);
  } else if (!state.progressFrame) {
    state.progressLastTick = 0;
    state.progressFrame = requestAnimationFrame(animateProgress);
  }
}

function resetProgress() {
  if (state.progressFrame) cancelAnimationFrame(state.progressFrame);
  state.progressFrame = 0;
  state.displayedProgress = 0;
  state.targetProgress = 0;
  state.progressLastTick = 0;
  renderProgress(0);
}

function waitForProgress(target, timeout = 2600) {
  const deadline = performance.now() + timeout;
  return new Promise((resolve) => {
    const check = () => {
      if (!isUiActive() || state.displayedProgress >= target || performance.now() >= deadline) return resolve();
      setTimeout(check, 32);
    };
    check();
  });
}

async function pollJob() {
  if (!isUiActive() || !state.jobId || state.pollInFlight) return null;
  state.pollInFlight = true;
  try {
    const response = await apiFetch(`/api/jobs/${state.jobId}/state`, { cache: "no-store", headers: clientHeaders() });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "İş durumu alınamadı.");
    if (["working", "cancelling", "done"].includes(data.status)) updateProgress(data.progress || 0, data.message || "İşleniyor");
    return data;
  } catch { return null; }
  finally { state.pollInFlight = false; }
}

const wait = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

function focusProcessingView(selector) {
  const element = $(selector);
  if (!element) return;
  requestAnimationFrame(() => requestAnimationFrame(() => element.scrollIntoView({
    behavior: motionMedia.matches ? "auto" : "smooth",
    block: "start",
    inline: "nearest"
  })));
}

async function waitForJobResult(initialResult = null) {
  if (initialResult) return initialResult;
  let connectionFailures = 0;
  while (state.jobRunning && state.jobId) {
    await waitForUiActive();
    await wait(connectionFailures ? Math.min(5000, 900 + connectionFailures * 650) : 900);
    await waitForUiActive();
    const job = await pollJob();
    if (!job) { connectionFailures += 1; continue; }
    connectionFailures = 0;
    if (job.status === "done" && job.result) return job.result;
    if (job.status === "cancelled") throw new Error(job.message || "İşlem iptal edildi.");
    if (job.status === "error") throw new Error(job.message || "İşlem tamamlanamadı.");
  }
  throw new Error("İşlem oturumu sonlandırıldı.");
}

async function runJob() {
  if (!state.jobId || state.jobRunning) return;
  const hasAds = Number(state.analysis?.network_count || 0) > 0;
  const patchAds = hasAds && ((state.operation === "patch" && state.patchAdsSelected) || (state.operation !== "patch" && $("#patchAds").checked));
  if (state.operation === "clone" && !validClonePackageName()) { toast("Klon için özgün addan farklı, geçerli bir paket adı gir."); return; }
  const needsDex = state.operation === "clone" || patchAds || $("#stripDebug").checked || $("#normalizeDex").checked;
  const needsResources = $("#deobfuscateResources").checked;
  if (state.toolchain && (!state.toolchain.signer || (needsDex && !state.toolchain.dex_tools) || (state.operation === "clone" && !state.toolchain.manifest_tool) || (needsResources && !state.toolchain.resource_tool))) {
    toast("İşlem için önce eksik bileşenleri hazırla."); $("#toolCard").scrollIntoView({ behavior: "smooth", block: "center" }); return;
  }
  setJobRunning(true);
  $("#diagnosticAfterFailure").classList.add("hidden");
  const cancelButton = $("#cancelJobButton");
  cancelButton.disabled = false; cancelButton.textContent = "İşlemi iptal et";
  resetProgress(); setStep(3); showView("#workingView"); updateProgress(4, "Yerel işlem motoru hazırlanıyor");
  focusProcessingView("#workingView");
  try {
    const payload = {
      job_id: state.jobId, profile: state.profile, operation: state.operation, patch_ads: patchAds,
      clone_package_name: state.operation === "clone" ? $("#clonePackageName").value.trim() : null,
      strip_debug: $("#stripDebug").checked, normalize_dex: $("#normalizeDex").checked, optimize_apk: $("#optimizeApk").checked,
      deobfuscate_resources: $("#deobfuscateResources").checked, normalize_resources: false,
      message_targets: state.messageTargets,
      split_selection: state.analysis?.split_merged ? state.splitSelection : null
    };
    const response = await apiFetch("/api/clean", { method: "POST", headers: clientHeaders({ "Content-Type": "application/json" }), body: JSON.stringify(payload) });
    const data = await response.json(); if (!response.ok) throw new Error(data.error || "İşlem başarısız.");
    const result = await waitForJobResult(data.result || null);
    updateProgress(100, "Tamamlandı"); await waitForProgress(100);
    const patchCount = result.patches.void_patches + result.patches.boolean_patches;
    $("#resultTitle").textContent = result.operation === "clone" ? "Klon APK oluşturuldu." : result.operation === "convert" ? "Tek APK başarıyla oluşturuldu." : "Temizlenmiş APK kullanıma hazır.";
    $("#resultStats").innerHTML = result.operation === "clone"
      ? `<div><b>${result.clone?.dex_strings_changed || 0}</b><span>DEX kimliği</span></div><div><b>${result.clone?.changes?.length || 0}</b><span>Manifest alanı</span></div><div><b>${patchCount}</b><span>Reklam yaması</span></div><div><b>${result.layouts?.count || 0}</b><span>XML alanı</span></div>`
      : `<div><b>${patchCount}</b><span>DEX yaması</span></div><div><b>${result.manifest.count}</b><span>Manifest kaydı</span></div><div><b>${result.layouts?.count || 0}</b><span>XML alanı</span></div><div><b>${result.patches.debug_directives_removed || 0}</b><span>Hata ayıklama yönergesi</span></div>`;
    const outputFilename = result.output || "APK-Cleaner-Studio-output.apk";
    state.outputUrl = `/api/jobs/${state.jobId}/download?filename=${encodeURIComponent(outputFilename)}`;
    state.outputFilename = outputFilename;
    $("#downloadButton").href = state.outputUrl;
    $("#downloadButton").download = outputFilename;
    $$(".native-android-action").forEach((button) => button.classList.toggle("hidden", document.documentElement.dataset.embedded !== "android"));
    $("#reportButton").dataset.jobId = state.jobId;
    setStep(4); showView("#resultView"); focusProcessingView("#resultView");
    refreshHistory();
    if (!result.signed) toast(result.sign_warning || "Çıktı imzalanamadı.");
  } catch (error) {
    toast(error.message);
    setStep(2); showView("#analysisView");
    $("#diagnosticAfterFailure").classList.toggle("hidden", !state.jobId);
    refreshHistory();
  }
  finally { setJobRunning(false); state.pollInFlight = false; }
}

async function cancelJob() {
  if (!state.jobRunning || !state.jobId) return;
  const button = $("#cancelJobButton");
  button.disabled = true; button.textContent = "İptal ediliyor…";
  try {
    const response = await apiFetch(`/api/jobs/${state.jobId}/cancel`, { method: "POST", headers: clientHeaders() });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "İşlem iptal edilemedi.");
    updateProgress(state.displayedProgress, "İşlem güvenli biçimde durduruluyor");
  } catch (error) {
    button.disabled = false; button.textContent = "İşlemi iptal et"; toast(error.message);
  }
}

function reset() {
  Object.assign(state, { file: null, jobId: null, analysis: null, profile: "balanced", operation: "patch", patchAdsSelected: true, splitSelection: { abis: [], languages: [] }, messageTargets: [], messageCandidates: [], pollInFlight: false, jobRunning: false, outputUrl: "", outputFilename: "", nativeInstallBusy: false, nativeShareBusy: false, nativeSplitInstallBusy: false, splitInstallRequestJobId: null, splitInstallSubmitted: false, installedSharePackage: "" });
  setJobRunning(false);
  resetProgress();
  $("#fileInput").value = ""; $("#cleanButton").disabled = false; $("#stripDebug").checked = false; $("#normalizeDex").checked = false; $("#optimizeApk").checked = false; $("#deobfuscateResources").checked = false; $("#patchAds").checked = false;
  $("#clonePackageName").value = ""; $("#cloneOptions").classList.add("hidden");
  $("#patchAvailabilityNote").classList.add("hidden"); $("#cloneAvailabilityNote").classList.add("hidden");
  for (const operation of [$("[data-operation='patch']"), $("#cloneOperation")]) {
    operation.classList.remove("operation-unavailable"); operation.setAttribute("aria-disabled", "false");
  }
  $("#directSplitInstall").classList.add("hidden"); clearDirectSplitPlan(); $("#directSplitInstallButton").disabled = false; $("#directSplitInstallButton").textContent = "Bileşenleri incele";
  $("#installButton").disabled = false; $("#shareOutputButton").disabled = false;
  $(".network-card").classList.remove("network-card--scrollable");
  $("#networkTitle").textContent = "İşlenecek paket bekleniyor"; $("#networkList").innerHTML = "<p>Paket seçildiğinde tespit edilen reklam ağları ve referans sayıları burada gösterilir.</p>";
  $("#splitSelector").classList.add("hidden"); $("#abiChoices").innerHTML = ""; $("#languageChoices").innerHTML = "";
  setStep(1); showView("#selectView");
}

$("#selectButton").addEventListener("click", (event) => { event.stopPropagation(); $("#fileInput").click(); });
$("#installedAppsButton").addEventListener("click", (event) => { event.stopPropagation(); openInstalledApps(); });
$("#installedAppsClose").addEventListener("click", closeInstalledApps);
$("#installedApps").addEventListener("click", (event) => { if (event.target === event.currentTarget) closeInstalledApps(); });
containModalTouch("#installedApps", ".installed-apps-list");
for (const name of ["pointerdown", "touchstart", "wheel", "keydown"]) {
  $("#installedApps").addEventListener(name, cancelInstalledAppReveal, { passive: true });
}
$("#installedAppsSearch").addEventListener("input", (event) => renderInstalledApps(event.target.value));
$("#installedAppsList").addEventListener("click", (event) => {
  const button = event.target.closest("[data-installed-package]");
  if (!button) return;
  const item = state.installedApps.find((candidate) => candidate.package === button.dataset.installedPackage);
  if (!item) return;
  const action = button.dataset.installedAction;
  if (action === "share") {
    if (!globalThis.AndroidThemeBridge?.shareInstalledPackage) return toast("Paylaşım bu platformda kullanılamıyor.");
    if (state.installedSharePackage) return;
    state.installedSharePackage = item.package;
    button.disabled = true;
    button.textContent = "Hazırlanıyor…";
    globalThis.AndroidThemeBridge.shareInstalledPackage(item.package);
    return;
  }
  if (action === "process") return processInstalledApp(item);
  state.selectedInstalledPackage = state.selectedInstalledPackage === item.package ? "" : item.package;
  updateInstalledAppSelection(item);
});
$("#dropzone").addEventListener("click", () => $("#fileInput").click());
$("#dropzone").addEventListener("keydown", (event) => { if (["Enter", " "].includes(event.key)) $("#fileInput").click(); });
$("#fileInput").addEventListener("change", (event) => acceptFile(event.target.files[0]));
$("#dropzone").addEventListener("dragover", (event) => { event.preventDefault(); event.currentTarget.classList.add("drag"); });
$("#dropzone").addEventListener("dragleave", (event) => event.currentTarget.classList.remove("drag"));
$("#dropzone").addEventListener("drop", (event) => { event.preventDefault(); event.currentTarget.classList.remove("drag"); acceptFile(event.dataTransfer.files[0]); });
$$(".operation").forEach((button) => button.addEventListener("click", () => setOperation(button.dataset.operation, true)));
$$(".profile").forEach((button) => button.addEventListener("click", () => {
  if (button.disabled || !Number(state.analysis?.network_count || 0)) return;
  $$(".profile").forEach((item) => item.classList.remove("selected"));
  button.classList.add("selected");
  state.profile = button.dataset.profile;
  updateActionState();
}));
$("#patchAds").addEventListener("change", updateActionState);
$("#patchAds").addEventListener("input", updateActionState);
$("#clonePackageName").addEventListener("input", updateActionState);
$("#savedPresetSelect").addEventListener("change", () => renderSavedPresets());
$("#applyPresetButton").addEventListener("click", applySavedPreset);
$("#savePresetButton").addEventListener("click", saveCurrentPreset);
$("#deletePresetButton").addEventListener("click", deleteSavedPreset);
["#stripDebug", "#normalizeDex", "#optimizeApk", "#deobfuscateResources"].forEach((selector) => {
  $(selector).addEventListener("change", updateActionState);
  $(selector).addEventListener("input", updateActionState);
});
$("#cleanButton").addEventListener("click", runJob); $("#resetButton").addEventListener("click", reset); $("#againButton").addEventListener("click", reset);
$("#cancelJobButton").addEventListener("click", cancelJob);
$("#reportButton").addEventListener("click", () => openReportViewer($("#reportButton").dataset.jobId || state.jobId, state.analysis?.filename || "Paket işlem raporu"));
$("#installButton").addEventListener("click", () => {
  if (!state.outputUrl) return toast("Kurulacak çıktı bulunamadı.");
  if (state.nativeInstallBusy) return;
  state.nativeInstallBusy = true; $("#installButton").disabled = true;
  globalThis.AndroidThemeBridge?.prepareInstall?.(new URL(state.outputUrl, location.href).href, state.outputFilename);
});
$("#directSplitInstallButton").addEventListener("click", () => {
  if (!state.jobId || !state.analysis || state.nativeSplitInstallBusy) return;
  if (!globalThis.AndroidThemeBridge?.inspectOriginalSplit) return toast("Doğrudan kurulum yalnızca Android uygulamasında kullanılabilir.");
  if (!["apks", "apkm", "xapk"].includes(String(state.analysis.source_type || "").toLowerCase())) return;
  clearDirectSplitPlan();
  state.nativeSplitInstallBusy = true;
  state.splitInstallRequestJobId = state.jobId;
  const button = $("#directSplitInstallButton");
  button.disabled = true; button.textContent = "Bileşenler inceleniyor…";
  const sourceUrl = new URL(`/api/jobs/${state.jobId}/source`, location.href).href;
  globalThis.AndroidThemeBridge.inspectOriginalSplit(sourceUrl, state.analysis.filename);
});
$$('input[name="directSplitMode"]').forEach((radio) => radio.addEventListener("change", () => {
  const manual = $("input[name=directSplitMode]:checked").value === "manual";
  $$("#directSplitModules input[type=checkbox]").forEach((checkbox) => {
    checkbox.disabled = !manual || checkbox.dataset.required === "true" || checkbox.dataset.alternative === "true";
    if (!manual) checkbox.checked = Boolean(state.splitInstallPlan?.modules.find((module) => module.name === checkbox.value)?.auto);
  });
  updateDirectSplitSummary();
}));
$("#directSplitModules").addEventListener("change", updateDirectSplitSummary);
$("#directSplitConfirm").addEventListener("click", async () => {
  const plan = state.splitInstallPlan;
  if (!plan || state.nativeSplitInstallBusy || state.splitInstallSubmitted) return;
  const selected = chosenDirectSplitModules();
  if (!selected.length || plan.blocked_reason) return;
  const bytes = plan.modules.filter((module) => selected.includes(module.name)).reduce((sum, module) => sum + Number(module.size || 0), 0);
  if (!await confirmAction("Özgün split paketi kur", `${plan.package} · sürüm ${plan.version}\n${selected.length} bileşen · ${humanSize(bytes)}\n${plan.installed ? "Mevcut uygulama güncellenecek." : "Yeni uygulama kurulacak."}\nBileşenler değiştirilmeden Android'e gönderilecek.`, "Kuruluma geç")) return;
  if (state.splitInstallPlan !== plan || state.jobId !== state.splitInstallRequestJobId) return;
  state.nativeSplitInstallBusy = true;
  state.splitInstallSubmitted = true;
  $("#directSplitConfirm").disabled = true;
  $("#directSplitInstallButton").disabled = true;
  globalThis.AndroidThemeBridge?.installOriginalSplit?.(JSON.stringify(selected));
});
$("#shareOutputButton").addEventListener("click", () => {
  if (!state.outputUrl) return toast("Paylaşılacak çıktı bulunamadı.");
  if (state.nativeShareBusy) return;
  state.nativeShareBusy = true; $("#shareOutputButton").disabled = true;
  globalThis.AndroidThemeBridge?.shareOutput?.(new URL(state.outputUrl, location.href).href, state.outputFilename);
});
$("#appDialogCancel").addEventListener("click", () => closeAppDialog(null));
$("#appDialogConfirm").addEventListener("click", () => closeAppDialog(true));
$("#appDialog").addEventListener("click", (event) => { if (event.target === event.currentTarget) closeAppDialog(null); });
containModalTouch("#appDialog");
$("#appDialogInput").addEventListener("keydown", (event) => { if (event.key === "Enter") closeAppDialog(true); });
$("#reportViewerClose").addEventListener("click", closeReportViewer);
$("#reportViewerDone").addEventListener("click", closeReportViewer);
$("#reportViewer").addEventListener("click", (event) => { if (event.target === event.currentTarget) closeReportViewer(); });
containModalTouch("#reportViewer", "#reportViewerContent");
$("#diagnosticButton").addEventListener("click", () => openDiagnosticViewer());
$("#storageCard").addEventListener("toggle", refreshStorage);
$("#storageList").addEventListener("change", () => { $("#storageCleanButton").disabled = !$("#storageList input:checked"); });
$("#storageCleanButton").addEventListener("click", cleanSelectedStorage);
$("#nativeCacheCleanButton").addEventListener("click", cleanNativeCache);
$("#installHistoryCard").addEventListener("toggle", refreshInstallHistory);
$("#diagnosticAfterFailure").addEventListener("click", () => openDiagnosticViewer(state.jobId));
$("#diagnosticViewerClose").addEventListener("click", closeDiagnosticViewer);
$("#diagnosticViewerDone").addEventListener("click", closeDiagnosticViewer);
$("#diagnosticViewer").addEventListener("click", (event) => { if (event.target === event.currentTarget) closeDiagnosticViewer(); });
$("#diagnosticIdentifiers").addEventListener("change", () => refreshDiagnosticPreview(true));
$("#diagnosticViewerDownload").addEventListener("click", (event) => {
  if (event.currentTarget.getAttribute("aria-disabled") === "true") event.preventDefault();
});
containModalTouch("#diagnosticViewer", "#diagnosticViewerContent");
$("#messageReviewButton").addEventListener("click", openMessageReview);
$("#messageScanButton").addEventListener("click", scanMessageCandidates);
$("#messageReviewApply").addEventListener("click", applyMessageSelection);
$("#messageRiskAcknowledged").addEventListener("change", clearMessageRiskError);
$("#messageReviewClose").addEventListener("click", closeMessageReview);
$("#messageReviewCancel").addEventListener("click", closeMessageReview);
$("#messageReview").addEventListener("click", (event) => { if (event.target === event.currentTarget) closeMessageReview(); });
containModalTouch("#messageReview", ".message-review-body");
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  if (!$("#messageReview").classList.contains("hidden")) closeMessageReview();
  else if (!$("#diagnosticViewer").classList.contains("hidden")) closeDiagnosticViewer();
  else if (!$("#installedApps").classList.contains("hidden")) closeInstalledApps();
  else if (!$("#reportViewer").classList.contains("hidden")) closeReportViewer();
  else if (activeDialog) closeAppDialog(null);
});
$("#toolsButton").addEventListener("click", () => $("#toolCard").scrollIntoView({ behavior: "smooth", block: "center" }));
$("#updateDownload").addEventListener("click", applyAvailableUpdate);
$("#updateDismiss").addEventListener("click", dismissUpdateNotice);
document.addEventListener("click", handleInlineDisclosureClick);
$("#setupButton").addEventListener("click", async () => {
  const button = $("#setupButton"); button.disabled = true; button.textContent = "Bileşenler hazırlanıyor…";
  try {
    const response = await apiFetch("/api/setup", { method: "POST", headers: clientHeaders() }); const data = await response.json(); if (!response.ok) throw new Error(data.error || "Kurulum başarısız.");
    state.toolchain = data.toolchain; renderTools(data.toolchain);
    toast(data.errors.length ? `Bazı bileşenler hazırlanamadı: ${data.errors.join(" · ")}` : "Java, DEX, split ve imzalama bileşenleri hazır.");
  } catch (error) { toast(error.message || "Bileşenler indirilemedi. İnternet bağlantısını kontrol et."); }
  finally { button.disabled = button.classList.contains("setup-hidden"); button.textContent = "Eksik bileşenleri hazırla"; }
});
$$("[data-theme-choice]").forEach((button) => button.addEventListener("click", () => applyTheme(button.dataset.themeChoice)));
themeMedia.addEventListener?.("change", () => { if ((localStorage.getItem(THEME_KEY) || "system") === "system") applyTheme("system", false); });
if (document.documentElement.dataset.embedded === "android") {
  document.querySelector(".brand")?.addEventListener("click", (event) => {
    event.preventDefault();
    reset();
    scrollTo({ top: 0, behavior: motionMedia.matches ? "auto" : "smooth" });
  });
}
function revealReadyInterface() {
  const reveal = () => requestAnimationFrame(() => requestAnimationFrame(() => {
    document.documentElement.classList.remove("ui-boot");
    document.documentElement.classList.add("ui-ready");
  }));
  reveal();
}

const embeddedAndroid = document.documentElement.dataset.embedded === "android";
$("#installHistoryCard").classList.toggle("hidden", !embeddedAndroid || !globalThis.AndroidThemeBridge?.getInstallHistory);
$("#installedAppsButton").classList.toggle("hidden", !embeddedAndroid
  || (!globalThis.AndroidThemeBridge?.requestInstalledPackages && !globalThis.AndroidThemeBridge?.listInstalledPackages));
applyTheme(localStorage.getItem(THEME_KEY) || "system", false); startHeroRotation();
renderSavedPresets();
if (!embeddedAndroid) registerClientDetails();
refreshStatus(); refreshHistory();
checkForUpdates();
revealReadyInterface();
uiScheduler.add("status", refreshStatus, 10000);
uiScheduler.add("history", refreshHistory, 30000);
uiScheduler.add("updates", checkForUpdates, 6 * 60 * 60 * 1000);
uiScheduler.setActive(isUiActive());

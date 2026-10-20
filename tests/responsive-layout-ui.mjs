// Local fixture only: no real package processing or external requests.
import assert from "node:assert/strict";
const { chromium } = await import(process.env.APK_CLEANER_PLAYWRIGHT || "playwright");
const browser = await chromium.launch({ headless: true, channel: "msedge" });
const errors = [];
const quick = process.env.APK_CLEANER_RESPONSIVE_QUICK === "1";
const widths = quick ? [900, 901, 1000, 1023, 1024, 1080, 1119, 1120, 1200]
  : [360, 390, 620, 720, 760, 840, 900, 901, 1000, 1023, 1024, 1100, 1119, 1120, 1200, 1440, 1920];
const base = "http://127.0.0.1:18081/?capture=responsive-check";

async function check(page, stage, width, theme) {
  await page.waitForTimeout(60);
  const issues = await page.evaluate(() => {
    const failures = [];
    const visible = node => !!node.getClientRects().length;
    const rect = node => node.getBoundingClientRect();
    const overlap = (a, b) => Math.min(a.right, b.right) - Math.max(a.left, b.left) > 1
      && Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 1;
    const copy = document.querySelector(".studio-overview-copy");
    const route = document.querySelector(".process-route");
    if (visible(copy) && overlap(rect(copy), rect(route))) failures.push("guide columns overlap");
    if (visible(copy) && rect(copy).width < 240) failures.push(`guide copy too narrow: ${rect(copy).width}`);
    const controls = [".topbar .brand", ".topbar .connection", ".topbar .top-actions"]
      .map(selector => document.querySelector(selector)).filter(visible);
    for (let i = 0; i < controls.length; i++) for (let j = i + 1; j < controls.length; j++) {
      if (overlap(rect(controls[i]), rect(controls[j]))) failures.push("header controls overlap");
    }
    const selectors = [".profile", ".operation", ".option", ".split-choice", ".working-package", ".working-selection",
      ".working-activity", ".selection-summary", ".package-info", ".result-summary", ".result-comparison",
      ".app-dialog-card", ".report-viewer-card", ".process-route li > div", ".studio-overview-copy > p"];
    for (const selector of selectors) for (const node of document.querySelectorAll(selector)) {
      if (!visible(node)) continue;
      if (node.scrollWidth > node.clientWidth + 2) failures.push(`${selector}: content spills ${node.scrollWidth - node.clientWidth}px`);
      if (rect(node).right > innerWidth + 1 || rect(node).left < -1) failures.push(`${selector}: outside window`);
    }
    for (const card of document.querySelectorAll(".report-viewer-card, .app-dialog-card")) {
      if (visible(card) && (rect(card).top < -1 || rect(card).bottom > innerHeight + 1)) failures.push("dialog outside window height");
    }
    const workspace = document.querySelector(".workspace");
    const main = document.querySelector(".workspace-primary");
    const side = document.querySelector(".workspace > aside");
    const sideBySide = rect(side).left >= rect(main).right - 1;
    if (!sideBySide && visible(copy)) failures.push("guide should be hidden in the single-column workspace");
    const guide = document.querySelector("#startGuide");
    if (sideBySide && !guide.classList.contains("hidden") && !visible(copy)) failures.push("guide missing in the two-column workspace");
    if (innerWidth >= 901 && innerWidth < 1024 && sideBySide) failures.push("sidebar did not reflow at the compact threshold");
    if (innerWidth >= 1024 && !sideBySide) failures.push("sidebar reflowed too early");
    if (sideBySide && rect(main).width < 640) failures.push("main column squeezed");
    if (rect(workspace).right > innerWidth + 1) failures.push("workspace outside window");
    return failures;
  });
  assert.deepEqual(issues, [], JSON.stringify({ width, theme, stage, issues }));
}

try {
  for (const theme of ["light", "dark"]) {
    const context = await browser.newContext({ viewport: { width: 1200, height: 900 } });
    await context.route("**/*", route => new URL(route.request().url()).hostname === "127.0.0.1" ? route.continue() : route.abort());
    const page = await context.newPage();
    page.setDefaultTimeout(10000);
    page.on("pageerror", error => errors.push(error.message));
    await page.goto(base);
    await page.waitForFunction(() => typeof qaAnalysis === "function");
    await page.evaluate(theme => applyTheme(theme), theme);
    await page.evaluate(async () => {
      qaAnalysis(true, false, false);
      const response = await fetch("/api/clean", { method: "POST", referrer: location.origin + "/?capture=result",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify({ profile: "deep", operation: "patch", patch_ads: true }) });
      const data = await response.json();
      await renderCompletedJob(data.result);
    });
    for (const width of widths) {
      await page.setViewportSize({ width, height: 900 });
      await page.evaluate(() => showView("#selectView"));
      await check(page, "select", width, theme);
      await page.evaluate(() => qaAnalysis(true, false, true));
      await check(page, "split-analysis", width, theme);
      await page.evaluate(() => qaAnalysis(true, false, false));
      await check(page, "apk-analysis", width, theme);
      await page.evaluate(() => { qaWorking(true); document.querySelector("#workingSelection").open = true; });
      await check(page, "working-long", width, theme);
      await page.evaluate(() => { showView("#resultView"); document.querySelector("#resultDetails").open = true; });
      await check(page, "result", width, theme);
      if (quick) {
        console.log(`OK ${width}px ${theme}: layout boundary, guide visibility and processing cards`);
        continue;
      }
      await page.evaluate(() => { confirmAction("İşlem iptal edilsin mi?", "Devam eden işlem güvenli biçimde durdurulacak. Orijinal paket korunur."); });
      await page.locator("#appDialog").waitFor({ state: "visible" });
      await check(page, "confirm", width, theme);
      await page.locator("#appDialogCancel").click();
      await page.locator("#appDialog").waitFor({ state: "hidden" });
      await page.evaluate(() => { openInstalledApps(); });
      await page.locator("#installedApps").waitFor({ state: "visible" });
      await check(page, "installed-apps", width, theme);
      await page.locator("#installedAppsClose").click();
      await page.locator("#installedApps").waitFor({ state: "hidden" });
      await page.evaluate(() => { openHistoryStatus(); });
      await check(page, "history-filter", width, theme);
      await page.locator("#historyStatusClose").click();
      await page.locator("#historyStatusDialog").waitFor({ state: "hidden" });
      await page.evaluate(() => { openReportViewer("fixture", "Paket işlem raporu"); });
      await page.locator("#reportViewer").waitFor({ state: "visible" });
      await check(page, "report", width, theme);
      await page.locator("#reportViewerClose").click();
      await page.locator("#reportViewer").waitFor({ state: "hidden" });
      await page.evaluate(() => { openDiagnosticViewer("fixture"); });
      await page.locator("#diagnosticViewer").waitFor({ state: "visible" });
      await check(page, "diagnostic", width, theme);
      await page.locator("#diagnosticViewerClose").click();
      await page.locator("#diagnosticViewer").waitFor({ state: "hidden" });
      await page.evaluate(() => { openMessageReview(); });
      await page.locator("#messageReview").waitFor({ state: "visible" });
      await check(page, "message-review", width, theme);
      await page.locator("#messageReviewClose").click();
      await page.locator("#messageReview").waitFor({ state: "hidden" });
      console.log(`OK ${width}px ${theme}: guide, header, configuration, progress, result, dialogs`);
    }
    for (const width of quick ? [] : [1440, 1120, 1119, 1024, 1023, 901, 900, 840, 760]) {
      await page.setViewportSize({ width, height: 520 });
      await page.evaluate(() => showView("#selectView"));
      await check(page, "live-shrink-short-window", width, theme);
      await page.evaluate(() => { openReportViewer("fixture"); });
      await page.locator("#reportViewer").waitFor({ state: "visible" });
      await check(page, "short-report", width, theme);
      await page.locator("#reportViewerClose").click();
      await page.locator("#reportViewer").waitFor({ state: "hidden" });
    }
    await context.close();
  }
  assert.deepEqual(errors, []);
} finally {
  await browser.close();
}

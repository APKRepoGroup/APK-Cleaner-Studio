// UI-only LAN responses: no real network listener is enabled by this test.
import assert from "node:assert/strict";
const { chromium } = await import(process.env.APK_CLEANER_PLAYWRIGHT || "playwright");
const browser = await chromium.launch({ headless: true, channel: "msedge" });
const base = process.env.APK_CLEANER_DESKTOP_TEST_URL || "http://127.0.0.1:18085/";
let cases = 0;
try {
  for (const theme of ["light", "dark"]) for (const width of [390, 760, 1024, 1200, 1440]) {
    const context = await browser.newContext({ viewport: { width, height: 900 }, colorScheme: theme });
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    let enabled = false, fail = false;
    await context.route("**/*", async route => {
      const request = route.request();
      const url = new URL(request.url());
      if (url.origin !== new URL(base).origin) return route.abort();
      if (url.pathname === "/api/desktop/network") {
        if (request.method() === "POST") {
          if (fail) return route.fulfill({ status: 503, json: { error: "Yerel ağ erişimi açılamadı." } });
          enabled = request.postDataJSON().enabled;
        }
        return route.fulfill({ json: { enabled, url: enabled ? "http://192.168.50.10:8080/" : "",
          secure_url: enabled ? "https://192.168.50.10:8080/" : "" } });
      }
      return route.continue();
    });
    await page.goto(base);
    await page.waitForFunction(() => document.querySelector("#desktopNetworkToggle")?.disabled === false);
    await page.evaluate(value => document.documentElement.dataset.theme = value, theme);
    const button = page.locator("#desktopNetworkToggle");
    assert.equal(await page.locator("#clientCard").isVisible(), false);
    assert.equal(await page.locator("#toolCertificate").isVisible(), false);
    // Dismissing approval never changes access.
    await button.click();
    await page.locator("#appDialogCancel").click();
    assert.equal(enabled, false);
    await button.click();
    await page.locator("#appDialogConfirm").click();
    await page.waitForFunction(() => document.documentElement.dataset.lanEnabled === "true");
    assert.equal(await page.locator("#clientCard").isVisible(), true);
    assert.equal(await page.locator("#toolCertificate").isVisible(), true);
    assert.equal(await page.locator("#desktopNetworkUrl").inputValue(), "http://192.168.50.10:8080/");
    const overflow = await page.locator("#desktopNetworkCard").evaluate(card => {
      const r = card.getBoundingClientRect();
      return card.scrollWidth > card.clientWidth + 1 || r.left < 0 || r.right > innerWidth + 1
        || card.scrollHeight > card.clientHeight + 2;
    });
    assert.equal(overflow, false, `${theme}/${width}: LAN card clipped`);
    await button.click();
    await page.locator("#appDialogConfirm").click();
    await page.waitForFunction(() => document.documentElement.dataset.lanEnabled === "false");
    assert.equal(await page.locator("#clientCard").isVisible(), false);
    fail = true;
    await button.click();
    await page.locator("#appDialogConfirm").click();
    await page.waitForFunction(() => document.querySelector("#desktopNetworkStatus").dataset.error === "true");
    assert.equal(enabled, false);
    assert.equal(await button.isEnabled(), true);
    assert.deepEqual(errors, []);
    cases++;
    await context.close();
  }
  console.log(JSON.stringify({ passed: cases, realLanEnabled: false }));
} finally {
  await browser.close();
}

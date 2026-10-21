// UI-only LAN responses: no real network listener is enabled by this test.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
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
          secure_url: enabled ? "https://192.168.50.10:8080/" : "", pairing_code: enabled ? "123456" : "" } });
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
    assert.equal(await page.locator("#desktopNetworkCode").inputValue(), "123456");
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
  const pairingPage = (await readFile(new URL("../studio/desktop/pair.html", import.meta.url), "utf8")).replace("{{error}}", "");
  for (const theme of ["light", "dark"]) for (const width of [320, 390, 760, 1200]) {
    const context = await browser.newContext({ viewport: { width, height: 700 }, colorScheme: theme });
    const page = await context.newPage();
    let paired = false;
    const requests = [];
    await context.route("**/*", route => {
      const request = route.request(), url = new URL(request.url());
      requests.push([request.method(), url.pathname]);
      if (url.origin !== new URL(base).origin) return route.abort();
      if (request.method() === "POST") {
        assert.equal(url.pathname, "/api/desktop/pair");
        assert.equal(new URLSearchParams(request.postData()).get("code"), "123456");
        paired = true;
        // HTTP redirect/cookie behavior is tested against the real Python
        // listener; this fixture verifies the browser's form submission only.
        return route.fulfill({ contentType: "text/html; charset=utf-8", body: "<h1>Eşleştirildi</h1>" });
      }
      return route.fulfill({ contentType: "text/html; charset=utf-8", body: paired ? "<h1>Eşleştirildi</h1>" : pairingPage });
    });
    await page.goto(base);
    assert.equal(await page.locator("input").getAttribute("inputmode"), "numeric");
    assert.equal(await page.locator("main").evaluate(node => node.scrollWidth > node.clientWidth + 1), false);
    await page.locator("#code").fill("123456");
    await page.getByRole("button", { name: "Bağlan", exact: true }).click();
    if (!paired) {
      console.log(JSON.stringify({ theme, width, requests, page: await page.locator("#code").evaluate(node => ({ valid: node.checkValidity(), value: node.value, validation: node.validationMessage, form: node.form?.outerHTML })) }));
    }
    await page.getByRole("heading", { name: "Eşleştirildi" }).waitFor();
    assert.equal(paired, true);
    cases++;
    await context.close();
  }
  console.log(JSON.stringify({ passed: cases, realLanEnabled: false }));
} finally {
  await browser.close();
}

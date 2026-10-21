// UI fixture only: notification preferences are never changed on the host.
import assert from "node:assert/strict";
const { chromium } = await import(process.env.APK_CLEANER_PLAYWRIGHT || "playwright");
const browser = await chromium.launch({ headless: true, channel: "msedge" });
const base = process.env.APK_CLEANER_DESKTOP_TEST_URL || "http://127.0.0.1:18085/";
let passed = 0;
try {
  for (const theme of ["light", "dark"]) for (const width of [390, 760, 1024, 1440]) {
    const context = await browser.newContext({ viewport: { width, height: 900 }, colorScheme: theme });
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    let mode = "all", fail = false;
    await context.route("**/*", async route => {
      const request = route.request(), url = new URL(request.url());
      if (url.origin !== new URL(base).origin) return route.abort();
      if (url.pathname === "/api/desktop/preferences") {
        if (request.method() === "POST") {
          if (fail) return route.fulfill({ status: 503, json: { error: "Kaydedilemedi." } });
          mode = request.postDataJSON().notifications;
        }
        return route.fulfill({ json: { notifications: mode } });
      }
      return route.continue();
    });
    await page.goto(base);
    await page.waitForFunction(() => document.querySelector("#desktopNotificationChoices")?.disabled === false);
    await page.evaluate(theme => document.documentElement.dataset.theme = theme, theme);
    const choices = page.locator("#desktopNotificationChoices");
    assert.equal(await choices.locator('input[value="all"]').isChecked(), true);
    for (const value of ["errors", "off"]) {
      await choices.locator(`input[value="${value}"]`).check();
      await page.waitForFunction(() => !document.querySelector("#desktopNotificationChoices").disabled);
      assert.equal(mode, value);
      assert.equal(await choices.locator(`input[value="${value}"]`).isChecked(), true);
    }
    fail = true;
    await choices.locator('input[value="all"]').check();
    await page.waitForFunction(() => document.querySelector("#desktopNotificationStatus").dataset.error === "true");
    assert.equal(await choices.locator('input[value="off"]').isChecked(), true);
    await page.reload();
    await page.waitForFunction(() => !document.querySelector("#desktopNotificationChoices")?.disabled);
    assert.equal(await choices.locator('input[value="off"]').isChecked(), true);
    await page.evaluate(theme => document.documentElement.dataset.theme = theme, theme);
    const card = page.locator("#desktopPreferencesCard");
    assert.equal(await card.evaluate(node => {
      const rect = node.getBoundingClientRect();
      return node.scrollWidth > node.clientWidth + 1 || node.scrollHeight > node.clientHeight + 2 || rect.left < 0 || rect.right > innerWidth + 1;
    }), false, `${theme}/${width}: preference card clipped`);
    if (width === 390 && theme === "dark") await card.screenshot({ path: ".codex-temp-dev6/notification-preferences.png" });
    assert.deepEqual(errors, []);
    await context.close();
    passed++;
  }
  console.log(JSON.stringify({ passed, hostPreferencesChanged: false }));
} finally {
  await browser.close();
}

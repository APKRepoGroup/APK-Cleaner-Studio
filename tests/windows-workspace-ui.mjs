// Run against the separate prototype server; no build and no real job needed.
import assert from "node:assert/strict";
const { chromium } = await import(process.env.APK_CLEANER_PLAYWRIGHT || "playwright");
const base = process.env.APK_CLEANER_WORKSPACE_URL || "http://127.0.0.1:18083/";
const browser = await chromium.launch({ headless: true, channel: "msedge" });
const errors = [];
try {
  for (const width of [760, 900, 1200, 1440]) {
    for (const theme of ["light", "dark"]) {
      const context = await browser.newContext({ viewport: { width, height: 800 } });
      await context.route("**/*", route => new URL(route.request().url()).origin === new URL(base).origin ? route.continue() : route.abort());
      const page = await context.newPage();
      page.setDefaultTimeout(10000);
      page.on("pageerror", error => errors.push(error.message));
      await page.goto(base);
      await page.locator(".desktop-workspace-ready").waitFor();
      await page.locator(`[data-theme-choice="${theme}"]`).click();
      await page.locator("#selectButton").waitFor({ state: "visible" });
      const original = await page.locator("#fileInput").evaluate(node => { node.dataset.kept = "same-node"; return node.id; });
      assert.equal(original, "fileInput");
      for (const id of ["history", "storage", "settings", "about", "work"]) {
        await page.locator(`[data-desktop-page="${id}"]`).click();
        await page.locator(`#desktop-${id}`).waitFor({ state: "visible" });
        const geometry = await page.evaluate(() => {
          const shell = document.querySelector(".desktop-shell");
          const scroller = document.querySelector(".desktop-scroll");
          const footer = document.querySelector(".desktop-statusbar").getBoundingClientRect();
          const visible = [...document.querySelectorAll(".desktop-page")].filter(node => !node.hidden);
          const ids = [...document.querySelectorAll("[id]")].map(node => node.id);
          return {
            horizontalOverflow: scroller.scrollWidth > scroller.clientWidth + 1,
            shellWidth: shell.getBoundingClientRect().width, height: innerHeight, width: innerWidth,
            footerBottom: footer.bottom, visible: visible.length,
            duplicateIds: ids.filter((id, index) => ids.indexOf(id) !== index),
            heroVisible: !!document.querySelector(".hero").getClientRects().length,
          };
        });
        assert.equal(geometry.visible, 1, JSON.stringify({ width, theme, id, geometry }));
        assert.equal(geometry.horizontalOverflow, false, JSON.stringify({ width, theme, id, geometry }));
        assert.ok(geometry.shellWidth <= width + 1);
        assert.ok(geometry.footerBottom <= geometry.height + 1);
        assert.equal(geometry.heroVisible, false);
        assert.deepEqual(geometry.duplicateIds, []);
      }
      assert.equal(await page.locator("#fileInput").getAttribute("data-kept"), "same-node");
      await page.locator('[data-desktop-page="history"]').click();
      await page.locator("#historyStatusButton").click();
      await page.locator("#historyStatusDialog").waitFor({ state: "visible" });
      await page.locator('[data-history-status="done"]').click();
      assert.equal(await page.locator("#historyStatusFilter").inputValue(), "done");
      // Simulate a view transition without launching a real process. The
      // adapter must bring history actions back to the same processing panel.
      await page.evaluate(() => {
        document.querySelector("#customAppName").value = "Korunan seçim";
        showView("#workingView");
        updateProgress(48, "Yerel düzen testi");
        state.jobId = "d6d60000000000000000000000000000";
        state.jobRunning = true;
      });
      await page.locator("#desktop-work #workingView").waitFor({ state: "visible" });
      assert.match(await page.locator("#desktopStage").textContent(), /devam ediyor/);
      await page.locator('[data-desktop-page="settings"]').click();
      await page.locator('[data-desktop-page="work"]').click();
      assert.equal(await page.locator("#customAppName").inputValue(), "Korunan seçim");
      assert.equal(await page.locator("#workingView").isVisible(), true);
      await page.locator("#cancelJobButton").click();
      await page.locator("#appDialog").waitFor({ state: "visible" });
      await page.locator("#appDialogCancel").click();
      assert.equal(await page.locator("#workingView").isVisible(), true);
      await context.close();
      console.log(`OK ${width}px ${theme}: navigation, layout, state, filter, cancel confirmation`);
    }
  }
  assert.deepEqual(errors, []);
} finally {
  await browser.close();
}

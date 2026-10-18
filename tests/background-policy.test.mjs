import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import test from 'node:test';

const source = await readFile(new URL('../studio/web/app.js', import.meta.url), 'utf8');
function runtime(embedded = 'android', reduced = true) {
  let hidden = true, requests = 0, active = true;
  const calls = [], animations = [], notice = { inert: false,
    classList: { toggle(name, value) { if (name === 'hidden') hidden = value; }, contains: name => name === 'hidden' && hidden,
      add(name) { if (name === 'hidden') hidden = true; }, remove(name) { if (name === 'hidden') hidden = false; } },
    getBoundingClientRect: () => ({ height: 200 }),
    animate(frames, options) { let finish; const animation = { frames, options, finished: new Promise(resolve => { finish = resolve; }), cancel() {}, finish: () => finish() }; animations.push(animation); return animation; },
  }, fields = new Map();
  const context = vm.createContext({ document: { documentElement: { dataset: { embedded } } },
    $: id => { if (id === '#batteryNotice') return notice; if (!fields.has(id)) fields.set(id, {}); return fields.get(id); }, toast() {}, motionMedia: { matches: reduced }, isUiActive: () => active,
    INLINE_REFLOW_MOTION: { duration: 360, easing: 'cubic-bezier(.22,.61,.36,1)' },
    getComputedStyle: () => ({ paddingTop: '20px', paddingBottom: '20px', marginTop: '20px', marginBottom: '20px', borderTopWidth: '1px', borderBottomWidth: '1px' }),
    AndroidThemeBridge: { requestBackgroundPolicy() { requests++; }, openBatterySettings(...args) { calls.push(args); } },
  });
  vm.runInContext(source.slice(source.indexOf('function requestBackgroundPolicy('), source.indexOf('globalThis.setNativeVisibility =')), context);
  return { context, calls, animations, notice, background() { active = false; context.settleBatteryNoticeDismissal(); }, get hidden() { return hidden; }, get requests() { return requests; } };
}

test('warning clears only when both optimization and background restriction are disabled', () => {
  const ui = runtime();
  for (const backgroundRestricted of [false, true]) for (const ignoringOptimizations of [false, true]) {
    ui.context.onBackgroundPolicy({ known: true, backgroundRestricted, ignoringOptimizations });
    assert.equal(ui.hidden, !backgroundRestricted && ignoringOptimizations);
  }
});

test('unknown, malformed and missing policy never claim unrestricted operation', () => {
  const ui = runtime();
  for (const policy of [null, {}, 'invalid', { known: false }, { known: true, backgroundRestricted: false, ignoringOptimizations: 'true' }]) {
    ui.context.onBackgroundPolicy(policy);
    assert.equal(ui.hidden, false);
  }
});

test('Doze exemption alone never hides an OEM background restriction and changes the action label', () => {
  const ui = runtime();
  ui.context.onBackgroundPolicy({ known: true, ignoringOptimizations: true, backgroundRestricted: true });
  assert.equal(ui.hidden, false);
  assert.equal(ui.context.$('#batterySettingsButton').textContent, 'Arka plan iznini düzenle');
  assert.match(ui.context.$('#batteryLead').textContent, /Pil optimizasyonu kapalı/);
  ui.context.onBackgroundPolicy({ known: true, ignoringOptimizations: false, backgroundRestricted: false });
  assert.equal(ui.hidden, false);
  assert.equal(ui.context.$('#batterySettingsButton').textContent, 'Arka planda çalışmaya izin ver');
});

test('opening settings does not dismiss the warning; only a verified new status can clear it', () => {
  const ui = runtime();
  ui.context.onBackgroundPolicy(JSON.stringify({ known: true, backgroundRestricted: true, ignoringOptimizations: false }));
  ui.context.openBatterySettings();
  ui.context.openBatterySettings(true);
  assert.equal(ui.calls.length, 2);
  assert.equal(ui.calls[0][0], false);
  assert.equal(ui.calls[1][0], true);
  assert.equal(ui.hidden, false);
  ui.context.requestBackgroundPolicy();
  assert.equal(ui.requests, 1);
  ui.context.onBackgroundPolicy({ known: true, backgroundRestricted: false, ignoringOptimizations: true });
  assert.equal(ui.hidden, true);
  ui.context.onBackgroundPolicy({ known: true, backgroundRestricted: false, ignoringOptimizations: false });
  assert.equal(ui.hidden, false);
});

test('desktop browsers never show native policy or launch battery settings', () => {
  const ui = runtime('');
  ui.context.onBackgroundPolicy({ known: true, backgroundRestricted: true, ignoringOptimizations: false });
  ui.context.requestBackgroundPolicy(); ui.context.openBatterySettings();
  assert.equal(ui.hidden, true); assert.equal(ui.requests, 0); assert.equal(ui.calls.length, 0);
});

test('native policy is republished and the user-initiated exemption has its required permission', async () => {
  const activity = await readFile(new URL('../android/app/src/main/java/com/apkcleaner/studio/MainActivity.java', import.meta.url), 'utf8');
  const policy = await readFile(new URL('../android/app/src/main/java/com/apkcleaner/studio/BackgroundPolicy.java', import.meta.url), 'utf8');
  const manifest = await readFile(new URL('../android/app/src/main/AndroidManifest.xml', import.meta.url), 'utf8');
  assert.match(activity.slice(activity.indexOf('@Override protected void onResume()')), /publishBackgroundPolicy\(\)/);
  assert.match(activity.slice(activity.indexOf('onPageFinished')), /publishBackgroundPolicy\(\)/);
  assert.match(policy, /SDK_INT >= 28 && tasks.isBackgroundRestricted\(\)/);
  assert.match(policy, /power.isIgnoringBatteryOptimizations\(activity.getPackageName\(\)\)/);
  assert.match(policy, /ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS/);
  assert.match(manifest, /android.permission.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS/);
  assert.match(policy, /new Intent\(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,/);
  assert.match(activity, /@JavascriptInterface public void requestBatteryExemption\(\)/);
});

test('battery notice uses the approved title and explanation before and after native status arrives', async () => {
  const html = await readFile(new URL('../studio/web/index.html', import.meta.url), 'utf8');
  const text = 'APK Cleaner Studio için arka planda çalışma izni verin.';
  assert.ok(html.includes('<b id="batteryTitle">Pil optimizasyonunu kapat</b>'));
  assert.ok(html.includes(`<p id="batteryLead">${text}</p><p>`));
  assert.ok(html.includes('<span class="battery-phrase">Pil kısıtlamaları,</span>'));
  assert.match(html, /id="batterySettingsButton"[^>]*>Arka planda çalışmaya izin ver<\/button>/);
  const css = await readFile(new URL('../studio/web/theme.css', import.meta.url), 'utf8');
  assert.match(css, /#batteryText p \+ p \{ margin-top: 0; \}/);
  assert.ok(source.includes(`: "${text}";`));
  assert.doesNotMatch(source, /Aksi hâlde Android uzun işlemleri durdurabilir/);
});

const restricted = { known: true, backgroundRestricted: true, ignoringOptimizations: false };
test('dismissal lasts for this opening only, including repeated policy updates and settings returns', () => {
  const ui = runtime(); ui.context.onBackgroundPolicy(restricted); ui.context.dismissBatteryNotice();
  assert.equal(ui.hidden, true);
  ui.context.requestBackgroundPolicy(); ui.context.openBatterySettings();
  for (const policy of [restricted, null, { known: true, backgroundRestricted: false, ignoringOptimizations: true }, restricted]) ui.context.onBackgroundPolicy(policy);
  assert.equal(ui.hidden, true);
  const reopened = runtime(); reopened.context.onBackgroundPolicy(restricted); assert.equal(reopened.hidden, false);
  const helper = source.slice(source.indexOf('function requestBackgroundPolicy('), source.indexOf('globalThis.setNativeVisibility ='));
  assert.doesNotMatch(helper, /localStorage|sessionStorage|document\.cookie/);
});
test('animated close shares update-panel motion and policy polling cannot snap it shut', async () => {
  const ui = runtime('android', false); ui.context.onBackgroundPolicy(restricted);
  ui.context.dismissBatteryNotice(); ui.context.dismissBatteryNotice();
  assert.equal(ui.animations.length, 1); assert.equal(ui.hidden, false); assert.equal(ui.notice.inert, true);
  assert.equal(ui.animations[0].options.duration, 360); assert.equal(ui.animations[0].options.easing, 'cubic-bezier(.22,.61,.36,1)');
  ui.context.onBackgroundPolicy(restricted); assert.equal(ui.hidden, false);
  ui.animations[0].finish(); await Promise.resolve();
  assert.equal(ui.hidden, true); assert.equal(ui.notice.inert, false);
});
test('background settling finishes a pending dismissal without restoring the warning', async () => {
  const ui = runtime('android', false); ui.context.onBackgroundPolicy(restricted); ui.context.dismissBatteryNotice();
  ui.background(); assert.equal(ui.hidden, true); assert.equal(ui.notice.inert, false);
  ui.animations[0].finish(); await Promise.resolve(); ui.context.onBackgroundPolicy(restricted);
  assert.equal(ui.hidden, true);
});
test('battery dismiss uses the same accessible cross icon and CSS as the update notice', async () => {
  const html = await readFile(new URL('../studio/web/index.html', import.meta.url), 'utf8');
  const svg = id => html.match(new RegExp(`<button id="${id}"[^>]*>(<svg[\\s\\S]*?</svg>)</button>`))[1];
  assert.equal(svg('batteryDismiss'), svg('updateDismiss'));
  assert.match(html, /aria-label="Pil uyarısını bu açılış için kapat"/);
  const css = await readFile(new URL('../studio/web/theme.css', import.meta.url), 'utf8');
  assert.match(css, /#updateDismiss, #batteryDismiss/);
});

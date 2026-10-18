import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import vm from 'node:vm';
const source = await readFile(new URL('../studio/web/app.js', import.meta.url), 'utf8');
const selection = () => ({ schema: 1, operation: 'clone', profile: 'deep', patch_ads: true, strip_debug: true, normalize_dex: false,
  optimize_apk: true, restrict_store_updates: true, deobfuscate_resources: false, clone_package_name: 'com.test.clone',
  message_targets: ['classes.dex:chosen'], split_selection: { abis: ['arm64-v8a'], languages: ['tr'] }, app_appearance: { name: '<literal name>' } });
function runtime() {
  const elements = new Map(), choices = { '[data-split-abi]': [{ value: 'arm64-v8a' }, { value: 'armeabi-v7a' }], '[data-split-language]': [{ value: 'tr' }, { value: 'en' }] };
  const get = key => { if (!elements.has(key)) elements.set(key, {}); return elements.get(key); };
  const state = {};
  const context = vm.createContext({ state, $: get, $$: key => choices[key] || [], setOperation: value => { state.operation = value; },
    updateSplitSelection() {}, renderAppearancePreview() {}, updateActionState() {},
  });
  vm.runInContext(source.slice(source.indexOf('function restoreProcessingSelection('), source.indexOf('function renderWorkingSelection(')), context);
  return { context, state, get, choices };
}
test('reconnection restores the actual operation, profile, patches, split subset and explicit app identity', () => {
  const ui = runtime(); assert.equal(ui.context.restoreProcessingSelection(selection()), true);
  assert.equal(ui.state.operation, 'clone'); assert.equal(ui.state.profile, 'deep');
  assert.equal(ui.get('#restrictStoreUpdates').checked, true); assert.equal(ui.get('#normalizeDex').checked, false);
  assert.equal(ui.get('#clonePackageName').value, 'com.test.clone'); assert.equal(ui.get('#customAppName').value, '<literal name>');
  assert.deepEqual(ui.choices['[data-split-abi]'].map(input => input.checked), [true, false]);
  assert.deepEqual(ui.choices['[data-split-language]'].map(input => input.checked), [true, false]);
  assert.equal(ui.state.messageTargets[0], 'classes.dex:chosen');
});
test('legacy or invalid selections are reported as unavailable rather than pretending defaults are the original settings', () => {
  for (const value of [null, {}, { ...selection(), schema: 2 }, { ...selection(), profile: 'unknown' }, { ...selection(), patch_ads: 'true' }]) {
    const ui = runtime(); assert.equal(ui.context.restoreProcessingSelection(value), false); assert.deepEqual(ui.state, {});
  }
});
test('restored images cannot fetch remote or executable content', () => {
  for (const icon of ['https://example.invalid/icon.png', 'data:image/svg+xml,<svg/>', 'javascript:bad']) {
    const ui = runtime(); const value = selection(); value.app_appearance.icon = icon;
    assert.equal(ui.context.restoreProcessingSelection(value), false); assert.deepEqual(ui.state, {});
  }
});
test('job options use the existing shared disclosure animation and never start processing on restore', async () => {
  const html = await readFile(new URL('../studio/web/index.html', import.meta.url), 'utf8');
  assert.match(html, /<details id="workingSelection"/);
  const restore = source.slice(source.indexOf('function restoreProcessingSelection('), source.indexOf('function rememberActiveJob('));
  assert.doesNotMatch(restore, /apiFetch|runJob\(/);
  assert.match(restore, /setInlineDisclosureOpen\(\$\("#workingSelection"\), false\)/);
});

import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import test from 'node:test';

const source = await readFile(new URL('../studio/web/app.js', import.meta.url), 'utf8');
const html = await readFile(new URL('../studio/web/index.html', import.meta.url), 'utf8');
function functionText(name) {
  const start = source.indexOf(`function ${name}(`);
  return source.slice(start, source.indexOf('\n}', start) + 2);
}
function runtime() {
  const elements = new Map();
  const context = vm.createContext({ state: { analysis: { network_count: 0 }, operation: 'patch',
    profile: 'balanced', patchAdsSelected: false, messageTargets: [] }, ACTION_NEXT_ICON: 'icon',
    updateAdProfileAvailability() {}, validClonePackageName: () => true,
    $: selector => {
      if (!elements.has(selector)) elements.set(selector, { checked: false, disabled: false, value: 'fixture',
        classList: { toggle() {} } });
      return elements.get(selector);
    }, $$: () => [], setOperation: operation => { context.state.operation = operation; }, toast() {},
    readSavedPresets: () => [{ id: 'fixture', options: { restrictStoreUpdates: true } }] });
  for (const name of ['updateActionState', 'currentPresetOptions', 'applySavedPreset']) vm.runInContext(functionText(name), context);
  return { context, elements };
}
test('the optional patch defaults off and includes the requested explanation and reinstall warning', () => {
  const input = html.match(/<input id="restrictStoreUpdates"[^>]*>/)[0];
  assert.doesNotMatch(input, /checked/);
  assert.match(html, /Play Store güncellemesini kapat/);
  assert.match(html, /Sürüm kodunu yükselterek mağazada güncelleme olarak gözükmesini sınırlar\./);
  assert.match(html, /Paket adı ve sürüm adı korunur\. Orijinal sürüm kodu içeren uygulamaya geri dönüş yeniden kurulum gerektirir ve üzerine kurulmaz\./);
});
test('the patch can be selected on its own without ad cleaning or cloning', () => {
  const { context, elements } = runtime();
  context.updateActionState();
  assert.equal(elements.get('#cleanButton').disabled, true);
  context.$('#restrictStoreUpdates').checked = true;
  context.updateActionState();
  assert.equal(elements.get('#cleanButton').disabled, false);
  context.$('#restrictStoreUpdates').checked = false;
  context.updateActionState();
  assert.equal(elements.get('#cleanButton').disabled, true);
});
test('saved profiles retain an explicit opt-in but never restore unavailable options', () => {
  const { context } = runtime();
  context.$('#restrictStoreUpdates').checked = true;
  assert.equal(context.currentPresetOptions().restrictStoreUpdates, true);
  context.$('#restrictStoreUpdates').checked = false;
  context.applySavedPreset();
  assert.equal(context.$('#restrictStoreUpdates').checked, true);
  context.$('#restrictStoreUpdates').disabled = true;
  context.applySavedPreset();
  assert.equal(context.$('#restrictStoreUpdates').checked, false);
  context.readSavedPresets = () => [{ id: 'fixture', options: {} }];
  context.applySavedPreset();
  assert.equal(context.$('#restrictStoreUpdates').checked, false);
});
test('fresh analyses and app reset do not silently reuse the version patch', () => {
  for (const name of ['applyAnalysisResult', 'prepareAnalysisView', 'reset']) {
    assert.match(functionText(name), /\$\("#restrictStoreUpdates"\)\.checked = false/);
  }
  assert.match(source, /restrict_store_updates: \$\("#restrictStoreUpdates"\)\.checked/);
  assert.match(source, /result\.cleaning_profile_applied === null \? "İşlenmiş APK kullanıma hazır\."/);
});

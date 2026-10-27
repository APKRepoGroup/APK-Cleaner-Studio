import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import vm from 'node:vm';
const context = vm.createContext({ TextEncoder });
vm.runInContext(await readFile(new URL('../studio/web/processing-presets.js', import.meta.url), 'utf8'), context);
const presets = context.StudioPresets;
const profile = name => ({ name, options: { operation: 'patch', profile: 'balanced', patchAds: true } });
const document = profiles => JSON.stringify({ format: 'apk-cleaner-processing-profiles', version: 1, profiles });
test('roundtrip includes options only, never source identity, icons or local IDs', () => {
  const source = { ...profile('Dengeli'), id: 'local-id', apk: 'private.apk', options: { ...profile('').options,
    package_name: 'private.package', app_icon: 'private-image', message_targets: ['private-method'] } };
  const text = presets.serialize([source]), imported = presets.parse(text);
  assert.doesNotMatch(text, /private|local-id/);
  assert.equal(imported[0].options.patchAds, true);
  assert.equal(imported[0].options.restrictStoreUpdates, false);
  assert.equal(imported[0].name, 'Dengeli');
});
test('invalid schemas, extra fields, string booleans, empty and excessive imports are rejected', () => {
  for (const text of ['{}', '[]', '{', document([]), document(Array.from({ length: 13 }, (_, n) => profile(String(n)))),
    document([{ ...profile('A'), file: 'forbidden.apk' }]),
    document([{ name: 'A', options: { ...profile('').options, patchAds: 'false' } }]),
    document([{ name: 'A', options: { ...profile('').options, clone_package_name: 'private' } }]),
    document([profile('IŞIK'), profile('ışık')]), document([profile('line\nbreak')]), ' '.repeat(16385)]) {
    assert.throws(() => presets.parse(text));
  }
  assert.equal(presets.parse('\ufeff' + document([profile('A')]))[0].name, 'A');
});
test('name collisions add renamed copies, never overwrite existing or apply an imported option', () => {
  const existing = [{ id: 'original', ...profile('İşlem') }];
  const result = presets.merge(existing, presets.parse(document([profile('işlem')])), () => 'new-id');
  assert.equal(result.profiles[0], existing[0]); assert.equal(result.profiles[1].name, 'işlem (2)');
  assert.equal(result.profiles[1].id, 'new-id'); assert.equal(existing.length, 1);
  assert.throws(() => presets.merge(Array.from({ length: 12 }, (_, n) => profile(String(n))), [profile('A')], () => 'id'));
});
test('export uses HTTP attachments on Android rather than unsupported blob downloads', async () => {
  const app = await readFile(new URL('../studio/web/app.js', import.meta.url), 'utf8');
  const native = await readFile(new URL('../android/app/src/main/java/com/apkcleaner/studio/MainActivity.java', import.meta.url), 'utf8');
  const start = app.indexOf('function exportSavedPresets('), end = app.indexOf('function currentPresetOptions(');
  assert.match(app.slice(start, end), /\/api\/profiles\/export\?profiles=/);
  assert.match(app.slice(start, end), /confirmAction\("İşlem profilleri eklensin mi/);
  assert.doesNotMatch(app.slice(start, end), /applySavedPreset\(/);
  assert.match(native, /isTrustedDownloadUri/);
  assert.match(native, /boolean choosingProfiles/);
  assert.match(native, /"application\/json", "text\/json", "text\/plain"/);
  assert.match(native, /"\/api\/profiles\/export"\.equals\(uri.getPath\(\)\)/);
  assert.match(native, /if \(address == null \|\| !isTrustedJobUri/);
});

test('import confirmation is atomic, cancellation and storage errors preserve existing profiles', async () => {
  const app = await readFile(new URL('../studio/web/app.js', import.meta.url), 'utf8');
  const controls = new Map(), original = [{ id: 'existing', ...profile('Dengeli') }];
  let stored = JSON.stringify(original), approved = false, writes = 0, failStorage = false;
  const messages = [], selections = [];
  const ui = vm.createContext({ StudioPresets: presets, $: key => {
    if (!controls.has(key)) controls.set(key, { disabled: false }); return controls.get(key);
  }, readSavedPresets: () => JSON.parse(stored), confirmAction: async () => approved,
  localStorage: { setItem(key, value) { if (failStorage) throw Error('quota'); writes++; stored = value; } },
  SAVED_PRESETS_KEY: 'test', crypto: { randomUUID: () => 'imported' },
  renderSavedPresets: id => selections.push(id), toast: message => messages.push(message), userErrorMessage: error => error.message });
  const start = app.indexOf('let presetImportBusy =');
  vm.runInContext(app.slice(start, app.indexOf('function currentPresetOptions(', start)), ui);
  const file = { size: 200, text: async () => document([profile('Dengeli')]) };
  await ui.importSavedPresets(file); assert.equal(writes, 0);
  approved = true; failStorage = true; await ui.importSavedPresets(file); assert.equal(writes, 0); assert.equal(selections.length, 0);
  failStorage = false; await ui.importSavedPresets(file);
  assert.equal(writes, 1); assert.equal(JSON.parse(stored)[0].id, 'existing');
  assert.equal(JSON.parse(stored)[1].name, 'Dengeli (2)'); assert.equal(selections[0], 'imported');
  assert.match(messages.at(-1), /^1 işlem profili eklendi/);
});

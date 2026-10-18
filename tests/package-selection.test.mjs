import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import vm from 'node:vm';
const source = await readFile(new URL('../studio/web/app.js', import.meta.url), 'utf8');
function runtime() {
  const state = { selectionGeneration: 0, jobRunning: false }, pending = [], applied = [], messages = [];
  const context = vm.createContext({ state, MAX_UPLOAD_BYTES: 1e9, extension: () => '.apk', isSplit: () => false,
    toast: message => messages.push(message), userErrorMessage: error => error.message,
    prepareAnalysisView() {}, applyAnalysisResult: data => applied.push(data),
    reset() { state.selectionGeneration++; state.selectionBusy = false; state.file = null; },
    FormData: class { append() {} }, clientHeaders: () => ({}),
    apiFetch: () => new Promise((resolve, reject) => pending.push({ resolve, reject })),
  });
  vm.runInContext(source.slice(source.indexOf('function beginPackageSelection('), source.indexOf('function prepareAnalysisView(')), context);
  vm.runInContext(source.slice(source.indexOf('globalThis.onInstalledPackageImported ='), source.indexOf('function renderProgress(')), context);
  return { context, state, pending, applied, messages };
}
const reply = name => ({ ok: true, json: async () => ({ job_id: name, analysis: { filename: name } }) });
test('the most recent file wins regardless of response ordering', async () => {
  const ui = runtime();
  const old = ui.context.acceptFile({ name: 'Old.apk', size: 1 });
  const current = ui.context.acceptFile({ name: 'Current.apk', size: 1 });
  ui.pending[1].resolve(reply('Current.apk')); await current;
  ui.pending[0].resolve(reply('Old.apk')); await old;
  assert.equal(ui.applied.length, 1); assert.equal(ui.applied[0].job_id, 'Current.apk');
  assert.equal(ui.state.file.name, 'Current.apk'); assert.equal(ui.state.selectionBusy, false);
});
test('late failures neither reset the new package nor display its predecessor error', async () => {
  const ui = runtime(); const old = ui.context.acceptFile({ name: 'Old.apk', size: 1 });
  const current = ui.context.acceptFile({ name: 'Current.apk', size: 1 });
  ui.pending[0].reject(Error('Old failed')); await old;
  assert.equal(ui.state.file.name, 'Current.apk'); assert.equal(ui.state.selectionBusy, true);
  assert.deepEqual(ui.messages, []);
  ui.pending[1].resolve(reply('Current.apk')); await current;
});
test('reset and history selection invalidate pending file analysis', async () => {
  for (const action of ['reset', 'beginPackageSelection']) {
    const ui = runtime(); const request = ui.context.acceptFile({ name: 'Old.apk', size: 1 });
    ui.context[action](); ui.pending[0].resolve(reply('Old.apk')); await request;
    assert.equal(ui.applied.length, 0);
  }
});
test('active processing cannot be replaced by another upload', async () => {
  const ui = runtime(); ui.state.jobRunning = true;
  await ui.context.acceptFile({ name: 'Other.apk', size: 1 });
  assert.equal(ui.pending.length, 0); assert.equal(ui.messages.length, 1);
});
test('a stale native callback cannot replace a newer file selection', async () => {
  const ui = runtime(); const generation = ui.context.beginPackageSelection();
  ui.state.nativeImportRequest = { generation, requestId: 'old-native' };
  const current = ui.context.acceptFile({ name: 'New.apk', size: 1 });
  ui.context.onInstalledPackageImported(JSON.stringify({ request_id: 'old-native', analysis: {}, native_file: { name: 'Old.apk' } }));
  assert.equal(ui.applied.length, 0); assert.equal(ui.state.file.name, 'New.apk');
  ui.pending[0].resolve(reply('New.apk')); await current;
});
test('native request identity rejects callbacks from earlier page sessions', () => {
  const ui = runtime(); const generation = ui.context.beginPackageSelection();
  ui.state.nativeImportRequest = { generation, requestId: 'current-native' };
  ui.context.onInstalledPackageImported(JSON.stringify({ request_id: 'previous-native', analysis: {} }));
  assert.equal(ui.applied.length, 0); assert.equal(ui.state.nativeImportRequest.requestId, 'current-native');
  ui.context.onInstalledPackageImported(JSON.stringify({ request_id: 'current-native', analysis: {}, native_file: { name: 'Native.apk', size: 3 } }));
  assert.equal(ui.applied.length, 1); assert.equal(ui.state.nativeImportRequest, null);
});
test('native success and failure carry request identity while preserving the legacy bridge', async () => {
  const native = await readFile(new URL('../android/app/src/main/java/com/apkcleaner/studio/MainActivity.java', import.meta.url), 'utf8');
  assert.match(native, /importInstalledPackageWithRequest\(String packageName, String requestId\)/);
  assert.match(native, /payload\.put\("request_id", requestId\)/);
  assert.match(native, /new JSONObject\(\)\.put\("request_id", requestId\)\.put\("error"/);
  assert.match(native, /importInstalledPackageWithRequest\(packageName, ""\)/);
});

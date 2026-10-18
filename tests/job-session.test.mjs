import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import test from 'node:test';
const source = await readFile(new URL('../studio/web/app.js', import.meta.url), 'utf8');
const id = 'a'.repeat(32);
function runtime(job = { status: 'working', progress: 45, message: 'Tarama', events: [] }) {
  const stores = [new Map(), new Map()], calls = [], failures = [], views = [], results = [];
  const storage = index => ({ getItem: key => stores[index].get(key) || null, setItem: (key, value) => stores[index].set(key, value), removeItem: key => stores[index].delete(key) });
  const state = { jobRunning: false, analysis: null, sessionRestoreInFlight: false };
  const context = vm.createContext({ state, clientId: 'owner-client', ACTIVE_JOB_KEY: 'active', sessionStorage: storage(0), localStorage: storage(1),
    $: () => ({ classList: { toggle() {} } }), toast() {}, clientHeaders: () => ({}), clearJobFailure() {}, resetProgress() {}, updateProgress() {}, setStep() {},
    restoreProcessingSelection: () => true, renderWorkingSelection() {},
    prepareAnalysisView() {}, applyAnalysisResult(data) { state.analysis = data.analysis; state.jobId = data.job_id; },
    setJobRunning(value) { state.jobRunning = value; }, showView: view => views.push(view), refreshHistory() {},
    renderJobFailure: error => failures.push(error), renderCompletedJob: async result => results.push(result),
    waitForJobResult: async () => ({ output: 'output.apk', signed: true }),
    apiFetch: async (...args) => { calls.push(args); return { ok: true, status: 200, json: async () => ({ job_id: id, analysis: { filename: 'Source.apk', size: 100 }, job }) }; },
  });
  vm.runInContext(source.slice(source.indexOf('function rememberActiveJob('), source.indexOf('async function renderCompletedJob(')), context);
  return { context, state, stores, calls, failures, views, results };
}

test('only an owner-scoped job pointer is persisted; no APK name, image or processing input', () => {
  const ui = runtime(); ui.context.rememberActiveJob(id);
  const record = JSON.parse(ui.stores[1].get('active'));
  assert.deepEqual(Object.keys(record).sort(), ['jobId', 'owner', 'savedAt']);
  assert.equal(ui.context.rememberedActiveJob(), id);
  ui.context.clientId = 'another-owner'; assert.equal(ui.context.rememberedActiveJob(), null);
});

test('reconnect follows existing work with GET only, never replays clean or upload', async () => {
  const ui = runtime(); ui.context.rememberActiveJob(id);
  await ui.context.restoreJobSession();
  assert.equal(ui.calls.length, 1); assert.equal(ui.calls[0][0], `/api/jobs/${id}/session`);
  assert.ok(!ui.calls[0][1].method || ui.calls[0][1].method === 'GET');
  assert.ok(ui.views.includes('#workingView')); assert.equal(ui.results.length, 1);
  assert.equal(ui.context.rememberedActiveJob(), null); assert.equal(ui.state.jobRunning, false);
});

test('motor interruption shows a recoverable failure rather than restarting or spinning forever', async () => {
  const ui = runtime({ status: 'error', interrupted: true, message: 'İşlem yarıda kaldı.', failure: { stage: 'Tarama' } });
  ui.context.rememberActiveJob(id); await ui.context.restoreJobSession();
  assert.equal(ui.calls.length, 1); assert.equal(ui.results.length, 0);
  assert.equal(ui.failures.length, 1); assert.equal(ui.failures[0].jobStatus, 'error');
  assert.equal(ui.context.rememberedActiveJob(), null);
});

test('denied or deleted sessions clear stale pointers without reading another job', async () => {
  for (const status of [403, 404]) {
    const ui = runtime(); ui.context.rememberActiveJob(id);
    ui.context.apiFetch = async () => ({ status, ok: false, json() { throw Error('Must not read'); } });
    await ui.context.restoreJobSession(); assert.equal(ui.context.rememberedActiveJob(), null);
    assert.equal(ui.state.analysis, null);
  }
});

test('network loss retains a pointer for a later check; restricted storage is harmless', async () => {
  const ui = runtime(); ui.context.rememberActiveJob(id);
  ui.context.apiFetch = async () => { throw Error('network'); };
  await ui.context.restoreJobSession(); assert.equal(ui.context.rememberedActiveJob(), id);
  ui.context.localStorage = ui.context.sessionStorage = { setItem() { throw Error('blocked'); }, getItem() { throw Error('blocked'); } };
  assert.doesNotThrow(() => ui.context.rememberActiveJob(id)); assert.equal(ui.context.rememberedActiveJob(), null);
});

test('an in-flight restore cannot replace a newly selected analysis', async () => {
  const ui = runtime(); let resolve;
  ui.context.apiFetch = () => new Promise(done => { resolve = done; });
  const pending = ui.context.restoreJobSession(id);
  const analysis = { filename: 'New.apk' }; ui.state.analysis = analysis;
  resolve({ ok: true, status: 200, json: async () => ({ job_id: id, analysis: {}, job: { status: 'working' } }) });
  await pending; assert.equal(ui.state.analysis, analysis); assert.equal(ui.views.length, 0);
});

test('an older tab finishing cannot erase a newer job marker', () => {
  const ui = runtime(); const newer = 'b'.repeat(32);
  ui.context.rememberActiveJob(newer); ui.context.forgetActiveJob(id);
  assert.equal(ui.context.rememberedActiveJob(), newer);
});

test('a file selected while reconnect is pending cannot be overwritten before its analysis arrives', async () => {
  const ui = runtime(); let resolve;
  ui.context.apiFetch = () => new Promise(done => { resolve = done; });
  const pending = ui.context.restoreJobSession(id);
  const file = { name: 'New.apk' }; ui.state.file = file;
  resolve({ ok: true, status: 200, json: async () => ({ job_id: id, analysis: {}, job: { status: 'working' } }) });
  await pending; assert.equal(ui.state.file, file); assert.equal(ui.views.length, 0);
});

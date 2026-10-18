import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import vm from 'node:vm';
const source = await readFile(new URL('../studio/web/app.js', import.meta.url), 'utf8');
function runtime() {
  const state = { jobId: 'first', pollInFlight: false }, notices = [], progress = [], timers = new Map();
  let active = true, nextTimer = 0;
  const context = vm.createContext({ state, AbortController, uiReadController: new AbortController(),
    isUiActive: () => active, clientHeaders: () => ({}),
    $: () => ({ classList: { toggle: (_, hidden) => notices.push(!hidden) } }),
    updateProgress: (...args) => progress.push(args), apiFetch: async () => ({ ok: true, status: 200, json: async () => ({ status: 'working', progress: 45 }) }),
    setTimeout: (callback, ms) => { const id = ++nextTimer; timers.set(id, { callback, ms }); return id; }, clearTimeout: id => timers.delete(id),
  });
  vm.runInContext(source.slice(source.indexOf('function showJobConnectionNotice('), source.indexOf('const wait =')), context);
  return { context, state, notices, progress, timers, background() { active = false; context.uiReadController.abort(); } };
}
test('connection failures retain the job and progress; the next successful GET clears the notice', async () => {
  const ui = runtime(); ui.context.apiFetch = async () => { throw Error('offline'); };
  assert.equal(await ui.context.pollJob(), null); assert.deepEqual(ui.notices, [true]);
  assert.equal(ui.state.jobId, 'first'); assert.equal(ui.progress.length, 0); assert.equal(ui.timers.size, 0);
  ui.context.apiFetch = async (_, init) => { assert.equal(init.method, undefined); return { ok: true, status: 200, json: async () => ({ status: 'working', progress: 51 }) }; };
  await ui.context.pollJob(); assert.equal(ui.notices.at(-1), false); assert.equal(ui.progress[0][0], 51);
});
test('hung reads show a delayed notice and time out without resubmitting work', async () => {
  const ui = runtime(); let calls = 0;
  ui.context.apiFetch = (_, init) => new Promise((_, reject) => { calls++; init.signal.addEventListener('abort', () => reject(Error('timeout'))); });
  const pending = ui.context.pollJob();
  [...ui.timers.values()].find(timer => timer.ms === 4000).callback(); assert.equal(ui.notices.at(-1), true);
  [...ui.timers.values()].find(timer => timer.ms === 12000).callback();
  await pending; assert.equal(calls, 1); assert.equal(ui.state.pollInFlight, false); assert.equal(ui.timers.size, 0);
});
test('background suspension and stale responses do not create false connection warnings or overwrite progress', async () => {
  for (const action of ['background', 'newJob']) {
    const ui = runtime(); let resolve;
    ui.context.apiFetch = () => new Promise(done => { resolve = done; });
    const pending = ui.context.pollJob();
    if (action === 'background') ui.background(); else ui.state.jobId = 'second';
    resolve({ ok: true, status: 200, json: async () => ({ status: 'working', progress: 99 }) });
    assert.equal(await pending, null); assert.equal(ui.progress.length, 0); assert.equal(ui.notices.length, 0);
  }
});
test('deleted or unauthorized jobs return terminal explanations rather than endless connection retries', async () => {
  for (const status of [403, 404]) {
    const ui = runtime(); ui.context.apiFetch = async () => ({ status, ok: false, json: async () => ({}) });
    const result = await ui.context.pollJob(); assert.equal(result.status, 'error'); assert.ok(result.message);
    assert.equal(ui.notices.at(-1), false); assert.equal(ui.progress.length, 0);
  }
});

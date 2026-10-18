import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import test from 'node:test';
const source = await readFile(new URL('../studio/web/app.js', import.meta.url), 'utf8');
function runtime(status, answer = false) {
  const elements = new Map(), confirmations = [];
  const get = id => {
    if (!elements.has(id)) elements.set(id, { textContent: '', classList: { toggle() {} }, scrollIntoView() {} });
    return elements.get(id);
  };
  const context = vm.createContext({ state: { jobId: 'job' }, $: get, clientHeaders: () => ({}), humanSize: bytes => `${bytes} B`,
    apiFetch: async () => ({ ok: true, json: async () => ({ status, message: 'Alan uyarısı', free_bytes: 100, recommended_bytes: 200 }) }),
    confirmAction: async (...args) => { confirmations.push(args); return answer; },
  });
  vm.runInContext(source.slice(source.indexOf('async function checkProcessingSpace('), source.indexOf('async function runJob(')), context);
  return { context, confirmations, get };
}

test('adequate storage continues without a dialog; critical shortage cannot be overridden', async () => {
  for (const status of ['ok', 'blocked']) {
    const ui = runtime(status, true); assert.equal(await ui.context.checkProcessingSpace('job'), status === 'ok');
    assert.equal(ui.confirmations.length, 0);
  }
});

test('estimated shortage and unavailable checks require explicit acknowledgement', async () => {
  for (const status of ['warning', 'unknown']) for (const answer of [false, true]) {
    const ui = runtime(status, answer); assert.equal(await ui.context.checkProcessingSpace('job'), answer);
    assert.equal(ui.confirmations.length, 1); assert.match(ui.confirmations[0][1], /yaklaşık/);
    assert.equal(ui.get('#storagePreflightMessage').textContent, 'Alan uyarısı');
  }
});

test('changed jobs cannot consume a previous space check', async () => {
  const ui = runtime('ok'); ui.context.state.jobId = 'new-job';
  assert.equal(await ui.context.checkProcessingSpace('job'), false);
});

test('space checks happen before clean requests, with duplicate and changed-option protection', () => {
  const run = source.slice(source.indexOf('async function runJob('), source.indexOf('async function cancelJob('));
  assert.ok(run.indexOf('await checkProcessingSpace(') < run.indexOf('apiFetch("/api/clean"'));
  assert.match(run, /state.preflightBusy/);
  assert.match(run, /processingSelectionKey\(\) !== checkedSelection/);
});

import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import test from 'node:test';

const source = await readFile(new URL('../studio/web/app.js', import.meta.url), 'utf8');
function runtime() {
  const elements = new Map(), pending = [], renders = [], timers = [];
  const element = id => {
    if (!elements.has(id)) elements.set(id, { value: id === '#historyStatusFilter' ? 'all' : '', innerHTML: '', textContent: '', scrollTop: 0,
      classList: { add() {}, remove() {} }, setAttribute() {} });
    return elements.get(id);
  };
  const state = { historyOffset: 0, historyGeneration: 0 };
  const context = vm.createContext({ state, $: element, isUiActive: () => true, URLSearchParams,
    uiReadController: new AbortController(), clientHeaders: () => ({}),
    apiFetch: (...args) => new Promise(resolve => pending.push({ args, resolve })),
    renderHistory: (jobs, page) => renders.push({ jobs, page }), clearTimeout() {}, setTimeout: fn => timers.push(fn),
  });
  vm.runInContext(source.slice(source.indexOf('function historyFilterKey('), source.indexOf('function renderHistory(')), context);
  vm.runInContext(source.slice(source.indexOf('async function refreshHistory('), source.indexOf('async function refreshStorage(')), context);
  return { context, state, elements, element, pending, renders, timers };
}
const response = (job, total = 1) => ({ ok: true, json: async () => ({ jobs: [job], total }) });
const settle = async () => { for (let index = 0; index < 8; index++) await Promise.resolve(); };

test('history filter changes discard late responses and request the new query once', async () => {
  const ui = runtime(), initial = ui.context.refreshHistory();
  ui.element('#historySearch').value = 'Yeni'; ui.context.changeHistoryFilter();
  assert.equal(ui.pending.length, 1);
  ui.pending[0].resolve(response({ filename: 'Stale.apk' })); await initial; await settle();
  assert.equal(ui.renders.length, 0); assert.equal(ui.pending.length, 2);
  assert.equal(new URL(ui.pending[1].args[0], 'http://localhost').searchParams.get('q'), 'Yeni');
  ui.pending[1].resolve(response({ filename: 'Yeni.apk' })); await settle();
  assert.equal(ui.renders.length, 1); assert.equal(ui.renders[0].jobs[0].filename, 'Yeni.apk');
});

test('query and status changes reset paging, debounce typing, and never submit processing requests', async () => {
  const ui = runtime(); ui.state.historyOffset = 40;
  ui.element('#historySearch').value = 'a&b'; ui.element('#historyStatusFilter').value = 'error';
  ui.context.changeHistoryFilter(true);
  assert.equal(ui.state.historyOffset, 0); assert.equal(ui.pending.length, 0);
  ui.timers[0](); assert.equal(ui.pending.length, 1);
  const query = new URL(ui.pending[0].args[0], 'http://localhost').searchParams;
  assert.equal(query.get('q'), 'a&b'); assert.equal(query.get('status'), 'error');
  assert.equal(ui.pending[0].args[1].method, undefined);
  ui.pending[0].resolve(response({})); await settle();
});

test('failed history fetch keeps retry available without treating history as an empty result', async () => {
  const ui = runtime(), request = ui.context.refreshHistory();
  ui.pending[0].resolve({ ok: false, json: async () => ({}) }); await request;
  assert.equal(ui.renders.length, 0);
  assert.match(ui.element('#historySearchState').textContent, /yüklenemedi/);
  assert.equal(ui.element('#historyList').inert, false);
});

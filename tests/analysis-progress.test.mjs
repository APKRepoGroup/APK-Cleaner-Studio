import assert from 'node:assert/strict';
import { webcrypto } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import vm from 'node:vm';
const source = await readFile(new URL('../studio/web/app.js', import.meta.url), 'utf8');

function runtime() {
  const state = { selectionGeneration: 1 }, timers = new Map(), requests = [], messages = [], native = [];
  const nodes = Object.fromEntries(['analysisScanProgress', 'analysisScanMessage', 'analysisScanCount', 'cancelAnalysisButton'].map(id => [id, { removeAttribute(name) { delete this[name]; } }]));
  let counter = 0;
  const context = vm.createContext({ state, crypto: webcrypto, Uint8Array, AbortController,
    $: selector => nodes[selector.slice(1)],
    isCurrentPackageSelection: generation => generation === state.selectionGeneration,
    setTimeout: fn => { timers.set(++counter, fn); return counter; }, clearTimeout: id => timers.delete(id),
    clientHeaders: extra => ({ 'X-Client-ID': 'owner', ...extra }), toast: message => messages.push(message), userErrorMessage: error => error.message,
    AndroidThemeBridge: { cancelInstalledPackageImport: id => native.push(id) },
    apiFetch: (url, init) => new Promise((resolve, reject) => requests.push({ url, init, resolve, reject })),
  });
  vm.runInContext(source.slice(source.indexOf('function renderAnalysisProgress('), source.indexOf('function beginPackageSelection(')), context);
  return { context, state, nodes, timers, requests, messages, native };
}

test('analysis polls measured progress and bounds the visible percentage', async () => {
  const ui = runtime(), task = ui.context.startAnalysisTracking(1);
  assert.match(task.id, /^[a-f0-9]{32}$/);
  const poll = ui.timers.get(task.timer)();
  ui.requests[0].resolve({ ok: true, json: async () => ({ message: 'classes2.dex tarandı (2/4)', progress: 37 }) });
  await poll;
  assert.equal(ui.nodes.analysisScanProgress.value, 37);
  assert.equal(ui.nodes.analysisScanMessage.textContent, 'classes2.dex tarandı (2/4)');
  ui.context.renderAnalysisProgress({ message: '<literal>', progress: 1000 });
  assert.equal(ui.nodes.analysisScanProgress.value, 100);
  assert.equal(ui.nodes.analysisScanCount.textContent, 'Analiz aşamaları · %100');
  ui.context.renderAnalysisProgress({ progress: null });
  assert.equal(ui.nodes.analysisScanProgress.value, undefined);
  ui.context.finishAnalysisTracking(task);
  assert.equal(ui.state.analysisTask, null);
  assert.equal(task.pollController.signal.aborted, true);
});

test('finishing or changing the selection prevents stale progress repaint', async () => {
  const ui = runtime(), task = ui.context.startAnalysisTracking(1);
  const poll = ui.timers.get(task.timer)();
  ui.state.selectionGeneration = 2;
  ui.context.finishAnalysisTracking(task);
  ui.requests[0].resolve({ ok: true, json: async () => ({ message: 'old file', progress: 90 }) });
  await poll;
  assert.equal(ui.nodes.analysisScanMessage.textContent, undefined);
  assert.equal(ui.state.analysisTask, null);
});

test('cancellation is idempotent, preserves an in-flight scan and waits for the server', async () => {
  const ui = runtime(), task = ui.context.startAnalysisTracking(1);
  task.snapshot = { progress: 37 };
  const request = ui.context.cancelAnalysis();
  await ui.context.cancelAnalysis();
  assert.equal(ui.requests.length, 1);
  assert.match(ui.requests[0].url, new RegExp(`/api/analysis/${task.id}/cancel$`));
  assert.equal(ui.nodes.cancelAnalysisButton.disabled, true);
  assert.equal(task.controller.signal.aborted, false);
  ui.requests[0].resolve({ ok: true }); await request;
  assert.equal(ui.state.analysisTask, task);
  assert.deepEqual(ui.native, [task.id]);
});

test('accepted cancellation interrupts a partial browser upload; failed requests allow retry', async () => {
  const ui = runtime(), task = ui.context.startAnalysisTracking(1);
  const first = ui.context.cancelAnalysis();
  ui.requests[0].resolve({ ok: false }); await first;
  assert.equal(task.cancelRequested, false);
  assert.equal(ui.nodes.cancelAnalysisButton.disabled, false);
  assert.equal(ui.messages.length, 1);
  const retry = ui.context.cancelAnalysis();
  ui.requests[1].resolve({ ok: true }); await retry;
  assert.equal(task.controller.signal.aborted, true);
});

test('new selections cancel the old request without cancelling another native import', () => {
  const ui = runtime(), task = ui.context.startAnalysisTracking(1);
  ui.context.stopAnalysisTracking();
  assert.equal(task.controller.signal.aborted, true);
  assert.equal(ui.state.analysisTask, null);
  assert.deepEqual(ui.native, [task.id]);
});

test('native imports forward the analysis token and use request-scoped cancellation', async () => {
  const native = await readFile(new URL('../android/app/src/main/java/com/apkcleaner/studio/MainActivity.java', import.meta.url), 'utf8');
  assert.match(native, /cancelInstalledPackageImport\(String requestId\)/);
  assert.match(native, /installedAnalysisCancellations\.get\(requestId\)/);
  assert.match(native, /setRequestProperty\("X-Analysis-ID", requestId\)/);
  assert.match(native, /installedAnalysisCancellations\.remove\(requestId, cancelled\)/);
  assert.match(native, /checkAnalysisCancellation\(cancelled\);\s+output.write/);
});

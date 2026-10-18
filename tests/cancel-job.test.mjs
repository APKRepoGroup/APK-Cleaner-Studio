import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import test from 'node:test';

const source = await readFile(new URL('../studio/web/app.js', import.meta.url), 'utf8');
function runtime() {
  const button = { disabled: false, textContent: 'İşlemi iptal et' }, calls = [], dialogs = [], notices = [];
  let answer;
  const context = vm.createContext({
    state: { jobId: 'original', jobRunning: true, displayedProgress: 53 }, activeDialog: {},
    $: () => button, confirmAction(...args) { dialogs.push(args); return new Promise(resolve => { answer = resolve; }); },
    clientHeaders: () => ({}), apiFetch: async (...args) => { calls.push(args); return { ok: true, json: async () => ({}) }; },
    updateProgress() {}, toast: message => notices.push(message),
  });
  vm.runInContext(source.slice(source.indexOf('async function cancelJob('), source.indexOf('function reset()')), context);
  return { context, calls, dialogs, button, notices, answer(value) { answer(value); } };
}

test('cancel requires confirmation and declining leaves the current job untouched', async () => {
  const ui = runtime(); const pending = ui.context.cancelJob();
  assert.equal(ui.calls.length, 0); assert.equal(ui.dialogs.length, 1);
  assert.equal(ui.button.disabled, false);
  ui.answer(false); await pending;
  assert.equal(ui.calls.length, 0); assert.equal(ui.context.state.jobRunning, true);
});

test('accepting issues one cancellation, repeated clicks cannot open overlapping dialogs', async () => {
  const ui = runtime(); const pending = ui.context.cancelJob(); await ui.context.cancelJob();
  assert.equal(ui.dialogs.length, 1); ui.answer(true); await pending;
  assert.equal(ui.calls.length, 1); assert.equal(ui.calls[0][0], '/api/jobs/original/cancel');
  assert.equal(ui.button.disabled, true); await ui.context.cancelJob(); assert.equal(ui.calls.length, 1);
});

test('finished and replaced jobs cannot be cancelled by an old confirmation', async () => {
  for (const replace of [false, true]) {
    const ui = runtime(); const pending = ui.context.cancelJob();
    if (replace) ui.context.state.jobId = 'new'; else ui.context.state.jobRunning = false;
    ui.answer(true); await pending; assert.equal(ui.calls.length, 0);
  }
});

test('cancellation request failure restores the button and permits another attempt', async () => {
  const ui = runtime(); ui.context.apiFetch = async () => { throw new Error('Bağlantı kurulamadı'); };
  const pending = ui.context.cancelJob(); ui.answer(true); await pending;
  assert.equal(ui.button.disabled, false); assert.equal(ui.notices[0], 'Bağlantı kurulamadı');
  assert.equal(ui.context.state.cancelPromptOpen, false);
});

test('completed work closes only its own pending confirmation', () => {
  const ui = runtime(); let closed = 0;
  ui.context.document = { documentElement: { dataset: {} } };
  ui.context.$ = function missingElement() { return null; }; ui.context.closeAppDialog = () => { closed++; };
  vm.runInContext(source.slice(source.indexOf('function setJobRunning('), source.indexOf('const httpFallback')), ui.context);
  ui.context.state.cancelDialog = ui.context.activeDialog;
  ui.context.setJobRunning(false); assert.equal(closed, 1);
  ui.context.state.cancelDialog = {}; ui.context.setJobRunning(false); assert.equal(closed, 1);
});

import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import vm from 'node:vm';

const source = await readFile(new URL('../studio/desktop/output.js', import.meta.url), 'utf8');
const first = 'a'.repeat(32), second = 'b'.repeat(32), origin = 'http://127.0.0.1:8081';
const url = job => `${origin}/api/jobs/${job}/download`;
const settle = () => new Promise(resolve => setImmediate(resolve));

function runtime(api) {
  const handlers = {}, messages = [], toasts = [];
  const button = { disabled: true, hidden: true, classList: { toggle: (_, value) => button.hidden = value },
    addEventListener: (name, callback) => { handlers[name] = callback; } };
  const download = { href: url(first) };
  const context = vm.createContext({ URL, location: { origin, href: origin + '/' }, pywebview: api ? { api } : undefined,
    document: { querySelector: selector => selector === '#downloadButton' ? download : button },
    MutationObserver: class { constructor(callback) { handlers.change = callback; } observe() {} },
    addEventListener: (name, callback) => { handlers[name] = callback; },
    chrome: { webview: { addEventListener: (_, callback) => messages.push(callback) } }, toast: text => toasts.push(text) });
  vm.runInContext(source, context);
  return { context, button, download, handlers, toasts,
    saved: job => messages[0]({ data: { type: 'apk-cleaner-output-saved', job } }) };
}

test('desktop output is unavailable before save and reveals only the current job ID', async () => {
  let saved = false;
  const opened = [];
  const ui = runtime({ saved_output_exists: async () => saved, reveal_saved_output: async job => {
    opened.push(job); return { opened: true };
  } });
  assert.equal(ui.button.hidden, false);
  await ui.handlers.click();
  assert.equal(opened.length, 0);
  saved = true; ui.saved(first); await settle();
  assert.equal(ui.button.disabled, false);
  await ui.handlers.click();
  assert.deepEqual(opened, [first]);
});

test('an old result cannot enable the button for a newly selected job', async () => {
  const pending = [];
  const ui = runtime({ saved_output_exists: job => new Promise(resolve => pending.push({ job, resolve })) });
  ui.download.href = url(second); const refresh = ui.handlers.change();
  pending[1].resolve(false); await refresh;
  pending[0].resolve(true); await settle();
  ui.saved(first);
  assert.equal(pending.length, 2);
  assert.equal(ui.button.disabled, true);
});

test('missing native bridge keeps the action hidden and moved outputs show a useful error', async () => {
  const browser = runtime();
  assert.equal(browser.button.hidden, true);
  let saved = true;
  const ui = runtime({ saved_output_exists: async () => saved, reveal_saved_output: async () => {
    saved = false; return { opened: false, error: 'Dosyayı yeniden indir.' };
  } });
  await settle();
  await ui.handlers.click(); await settle();
  assert.deepEqual(ui.toasts, ['Dosyayı yeniden indir.']);
  assert.equal(ui.button.disabled, true);
});

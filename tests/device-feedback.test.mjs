import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import test from 'node:test';

const source = await readFile(new URL('../studio/web/app.js', import.meta.url), 'utf8');

test('primary battery action asks the native system and never hides the warning optimistically', () => {
  let requested = 0, settings = 0;
  const context = vm.createContext({ document: { documentElement: { dataset: { embedded: 'android' } } },
    AndroidThemeBridge: { requestBatteryExemption: () => requested++ }, openBatterySettings: () => settings++, toast() {},
  });
  vm.runInContext(source.slice(source.indexOf('function requestBatteryExemption('), source.indexOf('function openBatterySettings(')), context);
  context.requestBatteryExemption(); assert.equal(requested, 1); assert.equal(settings, 0);
  delete context.AndroidThemeBridge.requestBatteryExemption;
  context.requestBatteryExemption(); assert.equal(settings, 1);
  context.document.documentElement.dataset.embedded = '';
  context.requestBatteryExemption(); assert.equal(requested, 1);
});

test('history picker selection and dismissal share app modal motion without a native select', async () => {
  const html = await readFile(new URL('../studio/web/index.html', import.meta.url), 'utf8');
  assert.doesNotMatch(html, /<select id="historyStatusFilter"/);
  assert.match(html, /id="historyStatusButton"[^>]*aria-haspopup="dialog"/);
  const elements = new Map(), events = [];
  function element(id) {
    if (!elements.has(id)) elements.set(id, { value: 'all', classList: { contains: () => false }, setAttribute() {}, focus() {} });
    return elements.get(id);
  }
  const context = vm.createContext({ $: element, $$: () => [], requestAnimationFrame() {},
    modalMotion: { close: (_dialog, done) => { events.push('close'); done(); } },
    lockPageScroll() {}, unlockPageScroll() {}, changeHistoryFilter: () => events.push('filter'),
  });
  vm.runInContext(source.slice(source.indexOf('function openHistoryStatus('), source.indexOf('function historyFilterKey(')), context);
  context.closeHistoryStatus(); assert.deepEqual(events, ['close']); events.length = 0;
  context.chooseHistoryStatus({ matches: () => true, dataset: { historyStatus: 'error' }, textContent: 'Hata' });
  assert.equal(element('#historyStatusFilter').value, 'error');
  assert.equal(element('#historyStatusLabel').textContent, 'Hata');
  assert.deepEqual(events, ['close', 'filter']);
});

test('the long tester name keeps the same type size as its peers with extra inline room', async () => {
  const css = await readFile(new URL('../studio/web/theme.css', import.meta.url), 'utf8');
  const html = await readFile(new URL('../studio/web/index.html', import.meta.url), 'utf8');
  assert.equal((html.match(/tester-label--muharrem/g) || []).length, 1);
  assert.match(html, /tester-label--muharrem"><b>@muharrem0001<\/b>/);
  assert.match(css, /\.tester-label--muharrem b \{ white-space: nowrap/);
  assert.match(css, /\.tester-label--muharrem \{ align-self: stretch; margin-inline: -2px;/);
  assert.match(css, /\.tester-label--muharrem b \{[^}]*font-size: inherit; line-height: inherit; letter-spacing: inherit;/);
  assert.doesNotMatch(css, /12\.6cqi|font-size: min\(10px/);
});

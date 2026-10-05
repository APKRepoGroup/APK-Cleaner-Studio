import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import test from 'node:test';

const source = await readFile(new URL('../studio/web/app.js', import.meta.url), 'utf8');
const html = await readFile(new URL('../studio/web/index.html', import.meta.url), 'utf8');
function runtime() {
  const elements = new Map();
  const get = selector => {
    if (!elements.has(selector)) elements.set(selector, {
      children: [], textContent: '', style: { setProperty() {} }, scrollTop: 0, scrollHeight: 240, clientHeight: 240,
      writes: 0, replaceChildren(...items) { this.children = items; this.writes++; },
    });
    return elements.get(selector);
  };
  const context = vm.createContext({
    state: { progressEvents: [], progressLogSignature: '', displayedProgress: 0, targetProgress: 0 },
    $: get, progressElements: { log: get('#liveLog'), phase: get('#phaseText'), ring: get('#ring'), value: get('#value'), bar: get('#bar') },
    document: { createElement() { return { children: [], append(...items) { this.children.push(...items); },
      set innerHTML(_) { throw Error('Events must remain text'); } }; } },
    motionMedia: { matches: true }, isUiActive: () => true, cancelAnimationFrame() {},
    setInlineDisclosureOpen(element, open) { element.open = open; },
  });
  vm.runInContext(source.slice(source.indexOf('function renderProgress('), source.indexOf('function waitForProgress(')), context);
  return { context, get };
}
const events = (count = 8) => Array.from({ length: count }, (_, i) => ({ id: i + 1, message: `Adım ${i + 1}`, elapsed_seconds: i * 2 }));
test('one poll retains fast engine events; only four recent entries occupy the compact view', () => {
  const { context, get } = runtime();
  context.updateProgress(53, 'classes8.dex işlendi (9/10) · 17 reklam yaması', events());
  assert.equal(get('#liveLog').children.length, 4);
  assert.equal(get('#liveLog').children[0].children[1].textContent, 'Adım 5');
  assert.equal(get('#workingFullLog').children.length, 8);
  assert.equal(get('#phaseText').textContent, 'classes8.dex işlendi (9/10)');
  assert.equal(get('#liveLog').children.at(-1).children[0].textContent, '0:14');
});
test('identical polls preserve DOM nodes and reading position', () => {
  const { context, get } = runtime();
  context.updateProgress(30, 'Adım 8', events());
  const first = get('#liveLog').children[0], writes = get('#workingFullLog').writes;
  context.updateProgress(30, 'Adım 8', events());
  assert.equal(get('#liveLog').children[0], first);
  assert.equal(get('#workingFullLog').writes, writes);
  Object.assign(get('#workingFullLog'), { scrollTop: 40, scrollHeight: 1000, clientHeight: 240 });
  context.updateProgress(35, 'Adım 9', events(9));
  assert.equal(get('#workingFullLog').scrollTop, 40);
});
test('bounded snapshots, malformed entries and untrusted markup are safe', () => {
  const { context, get } = runtime();
  const data = [...events(200), null, { message: 42 }, { message: '<img onerror=x>' }];
  context.updateProgress(50, 'Tarama', data);
  assert.ok(context.state.progressEvents.length <= 120);
  assert.equal(get('#workingFullLog').children.at(-1).children[1].textContent, '<img onerror=x>');
  assert.match(get('#workingLogNote').textContent, /son 120/);
  assert.equal(context.activityTime(NaN), '—');
  assert.equal(context.activityTime(-1), '—');
  assert.equal(context.activityTime(74.2), '1:14');
});
test('old engines get deduplicated observed history without invented elapsed times', () => {
  const { context, get } = runtime();
  context.updateProgress(4, 'Hazırlanıyor'); context.updateProgress(4, 'Hazırlanıyor');
  context.updateProgress(12, 'DEX hazırlanıyor');
  assert.equal(context.state.progressEvents.length, 2);
  assert.equal(get('#liveLog').children[0].children[0].textContent, '—');
});
test('a new job clears earlier events, scroll and disclosure state', () => {
  const { context, get } = runtime();
  context.updateProgress(53, 'Tarama', events()); get('#workingDetails').open = true;
  context.resetProgress();
  assert.equal(context.state.progressEvents.length, 0);
  assert.equal(get('#workingFullLog').children.length, 0);
  assert.equal(get('#liveLog').children.length, 0);
  assert.equal(get('#workingDetails').open, false);
  assert.equal(get('#workingFullLog').scrollTop, 0);
});
test('details reuse the delegated animation and do not announce every file repeatedly', () => {
  assert.match(html, /<details id="workingDetails"><summary>İşlem ayrıntıları<\/summary>/);
  const block = html.slice(html.indexOf('<section class="working-activity"'), html.indexOf('<button id="cancelJobButton"'));
  assert.doesNotMatch(block, /aria-live/);
  assert.match(source, /else toggleInlineDisclosure\(details, event\)/);
});

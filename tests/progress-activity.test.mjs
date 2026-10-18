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
      classList: { toggle() {}, add() {} },
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
test('one scrollable journal retains all fast engine events without duplicating recent entries', () => {
  const { context, get } = runtime();
  context.updateProgress(53, 'classes8.dex işlendi (9/10) · 17 reklam yaması', events());
  assert.equal(get('#liveLog').children.length, 8);
  assert.equal(get('#liveLog').children[0].children[1].textContent, 'Adım 1');
  assert.equal(get('#phaseText').textContent, 'classes8.dex işlendi (9/10)');
  assert.equal(get('#liveLog').children.at(-1).children[0].textContent, '0:14');
});
test('identical polls preserve DOM nodes and reading position', () => {
  const { context, get } = runtime();
  context.updateProgress(30, 'Adım 8', events());
  const first = get('#liveLog').children[0], writes = get('#liveLog').writes;
  context.updateProgress(30, 'Adım 8', events());
  assert.equal(get('#liveLog').children[0], first);
  assert.equal(get('#liveLog').writes, writes);
  Object.assign(get('#liveLog'), { scrollTop: 40, scrollHeight: 1000, clientHeight: 240 });
  context.updateProgress(35, 'Adım 9', events(9));
  assert.equal(get('#liveLog').scrollTop, 40);
});
test('bounded snapshots, malformed entries and untrusted markup are safe', () => {
  const { context, get } = runtime();
  const data = [...events(200), null, { message: 42 }, { message: '<img onerror=x>' }];
  context.updateProgress(50, 'Tarama', data);
  assert.ok(context.state.progressEvents.length <= 120);
  assert.equal(get('#liveLog').children.at(-1).children[1].textContent, '<img onerror=x>');
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
test('a new job clears earlier events and scroll state', () => {
  const { context, get } = runtime();
  context.updateProgress(53, 'Tarama', events());
  context.resetProgress();
  assert.equal(context.state.progressEvents.length, 0);
  assert.equal(get('#liveLog').children.length, 0);
  assert.equal(get('#liveLog').scrollTop, 0);
});
test('one keyboard-scrollable journal replaces the two old sections and avoids noisy announcements', () => {
  assert.doesNotMatch(html, /id="workingDetails"|id="workingFullLog"/);
  assert.match(html, /id="liveLog"[^>]*tabindex="0"/);
  assert.match(html, /id="liveLog" class="activity-list activity-history auto-hide-scrollbar"/);
  const block = html.slice(html.indexOf('<section class="working-activity"'), html.indexOf('<button id="cancelJobButton"'));
  assert.doesNotMatch(block, /aria-live/);
  assert.match(source, /progressElements.log.addEventListener\("scroll", syncProgressLogFollow/);
});

function scrollbarRuntime() {
  const handlers = {}, globalHandlers = {}, timers = new Map(), classes = new Set(); let nextId = 0;
  const element = { dataset: {}, classList: { add: name => classes.add(name), remove: name => classes.delete(name) },
    addEventListener(name, handler) { assert.equal(handlers[name], undefined); handlers[name] = handler; } };
  const context = vm.createContext({ setTimeout(callback, delay) { assert.equal(delay, 650); timers.set(++nextId, callback); return nextId; },
    clearTimeout(id) { timers.delete(id); }, window: { addEventListener(name, handler) { globalHandlers[name] = handler; } } });
  vm.runInContext(source.slice(source.indexOf('function enableAutoHideScrollbar('), source.indexOf("$$('.auto-hide-scrollbar')")), context);
  context.enableAutoHideScrollbar(element); context.enableAutoHideScrollbar(element);
  return { handlers, globalHandlers, timers, classes };
}

test('journal shares the same reveal events and 650ms inactivity timer as other auto-hide scrollbars', () => {
  const { handlers, timers, classes } = scrollbarRuntime();
  assert.equal(classes.size, 0);
  for (const event of ['scroll', 'scrollend', 'wheel', 'keydown']) {
    handlers[event](); assert.equal(classes.has('is-scrollbar-active'), true);
  }
  assert.equal(timers.size, 1);
  [...timers.values()][0]();
  assert.equal(classes.has('is-scrollbar-active'), false);
});

test('held mouse and touch gestures cannot expire before release; release outside restarts the full delay', () => {
  const { handlers, globalHandlers, timers, classes } = scrollbarRuntime();
  handlers.wheel(); assert.equal(timers.size, 1);
  handlers.pointerdown(); handlers.touchstart();
  assert.equal(timers.size, 0);
  handlers.scroll(); assert.equal(timers.size, 0);
  globalHandlers.pointerup(); assert.equal(timers.size, 0);
  assert.equal(classes.has('is-scrollbar-active'), true);
  globalHandlers.touchend(); assert.equal(timers.size, 1);
  [...timers.values()][0](); assert.equal(classes.has('is-scrollbar-active'), false);
});

test('cancelled gestures and window focus loss cannot leave a permanently visible scrollbar', () => {
  for (const end of ['pointercancel', 'blur']) {
    const { handlers, globalHandlers, timers } = scrollbarRuntime();
    handlers.pointerdown(); globalHandlers[end](); assert.equal(timers.size, 1);
  }
  const { handlers, globalHandlers, timers } = scrollbarRuntime();
  handlers.touchstart(); globalHandlers.touchcancel(); assert.equal(timers.size, 1);
});

test('readers can return to the live tail without affecting progress', () => {
  const { context, get } = runtime();
  context.updateProgress(53, 'Tarama', events());
  Object.assign(get('#liveLog'), { scrollTop: 40, scrollHeight: 1000, clientHeight: 240 });
  context.scrollProgressLogToEnd();
  assert.equal(get('#liveLog').scrollTop, 1000);
  assert.equal(context.state.displayedProgress, 53);
});

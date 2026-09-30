import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import test from 'node:test';

const boot = await readFile(new URL('../studio/web/boot.js', import.meta.url), 'utf8');
const positioning = boot.slice(0, boot.indexOf('\n\n(() => {'));

test('a failed app startup cannot leave the known-update reload invisible', async () => {
  const css = await readFile(new URL('../studio/web/boot.css', import.meta.url), 'utf8');
  assert.match(css, /html\.update-launch-pending body\s*\{\s*visibility: hidden;/);
  assert.match(boot, /setTimeout\(\(\) => \{[\s\S]*?classList\.remove\("update-launch-pending"\);[\s\S]*?\}, 800\)/);
});

function start({ type = 'reload', hint = '/?embedded=android', restricted = false, restoration = 'auto' } = {}) {
  const scrolls = [], frames = [], listeners = {};
  const history = { scrollRestoration: restoration };
  const classes = new Set();
  const context = vm.createContext({
    location: { pathname: '/', search: '?embedded=android' }, history,
    document: { documentElement: { classList: { add: name => classes.add(name) } } },
    performance: { getEntriesByType: () => type ? [{ type }] : [] },
    sessionStorage: { getItem() { if (restricted) throw new Error('restricted'); return hint; } },
    window: { scrollTo: options => scrolls.push(options) },
    addEventListener: (type, callback, options) => { listeners[type] = { callback, options }; },
    requestAnimationFrame: callback => frames.push(callback),
  });
  vm.runInContext(positioning, context);
  return { history, scrolls, frames, listeners, classes };
}

test('known-update reload suppresses restoration before any animation frame or API response', () => {
  const app = start();
  assert.equal(app.history.scrollRestoration, 'manual');
  assert.equal(app.classes.has('update-launch-pending'), true);
  assert.equal(app.scrolls.length, 1);
  assert.equal(app.scrolls[0].top, 0);
  assert.equal(app.frames.length, 0);
  assert.equal(app.listeners.pageshow.options.once, true);
  app.listeners.pageshow.callback();
  assert.equal(app.scrolls.length, 2);
  assert.equal(app.history.scrollRestoration, 'manual');
  assert.equal(app.frames.length, 0);
  app.listeners.pagehide.callback();
  assert.equal(app.history.scrollRestoration, 'auto');
});

test('unrelated pages, ordinary navigation and back/forward keep their scroll behavior', () => {
  for (const options of [{ hint: null }, { hint: '/other' }, { type: 'navigate' }, { type: 'back_forward' }, { type: null }, { restricted: true }]) {
    const app = start(options);
    assert.equal(app.history.scrollRestoration, 'auto');
    assert.equal(app.scrolls.length, 0);
    assert.equal(app.listeners.pageshow, undefined);
    assert.equal(app.classes.size, 0);
  }
});

test('an existing manual-restoration preference is preserved after page launch', () => {
  const app = start({ restoration: 'manual' });
  app.listeners.pageshow.callback(); app.listeners.pagehide.callback();
  assert.equal(app.history.scrollRestoration, 'manual');
});

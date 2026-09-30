import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import test from 'node:test';

const source = await readFile(new URL('../studio/web/app.js', import.meta.url), 'utf8');
const helpers = source.slice(source.indexOf('const INLINE_REFLOW_MOTION ='), source.indexOf('function openUpdateLink('));
const nativeVisibility = source.slice(source.indexOf('globalThis.setNativeVisibility ='), source.indexOf('document.addEventListener("visibilitychange"'));
const pageShow = source.slice(source.indexOf('window.addEventListener("pageshow"'), source.indexOf('let embeddedNativeTheme ='));

class Element {
  constructor(tag = 'div') {
    this.tag = tag; this.children = []; this.value = ''; this.dataset = {}; this.open = false;
    const classes = new Set(['hidden']);
    this.classList = {
      add: value => classes.add(value), remove: value => classes.delete(value), contains: value => classes.has(value),
      toggle(value, active) { if (active) classes.add(value); else classes.delete(value); },
    };
  }
  set textContent(value) { this.value = String(value); this.children = []; }
  get textContent() { return this.value + this.children.map(child => child.textContent).join(''); }
  set innerHTML(_value) { throw new Error('External release notes must never become HTML'); }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; this.value = ''; }
  querySelector() { return this.summary ||= new Element('summary'); }
  setAttribute(name, value) { (this.attributes ||= {})[name] = value; }
  getBoundingClientRect() {
    return { height: this.animation?.running && this.animation.currentHeight !== undefined
      ? this.animation.currentHeight : (this.open ? 300 : 45) };
  }
}

const update = {
  latest_version: '0.6.3-dev.2', automatic: true, install_mode: 'android',
  notes: 'Yeni test sürümü kullanıma hazır. Güncelleme notlarına aşağıdan ulaşabilirsiniz.',
  release_notes: '## 0.6.3-dev.2\n\n### Yeni özellikler\n- **Hata raporu** eklendi.\n- `APK` kontrolü iyileştirildi.',
  download_url: 'https://example.test/update.apk',
};

function runtime({ animated = false, reduced = false } = {}) {
  const elements = new Map();
  const state = { update: null, updateBusy: false, updateCheckInFlight: false, dismissedUpdateVersion: '' };
  let reply = { available: true, update };
  let requests = 0;
  const frames = []; const scrolls = []; const listeners = {};
  const pageScrollLocks = new Set();
  const context = vm.createContext({
    state, URL, motionMedia: { matches: reduced }, pageScrollLocks,
    requestAnimationFrame: callback => frames.push(callback),
    window: { scrollTo: options => scrolls.push(options), addEventListener: (type, callback) => { listeners[type] = callback; } },
    getComputedStyle: () => ({ paddingTop: '18px', paddingBottom: '18px', marginTop: '16px', marginBottom: '-12px', borderTopWidth: '1px', borderBottomWidth: '1px' }),
    $: selector => {
      if (!elements.has(selector)) {
        const element = new Element();
        if (animated) element.animate = (frames, options) => {
          let resolve; let reject;
          const animation = {
            frames, options, running: true,
            finished: new Promise((yes, no) => { resolve = yes; reject = no; }),
            finish() { resolve(); },
            cancel() { this.running = false; reject(new Error('animation cancelled')); },
          };
          element.animation = animation;
          return animation;
        };
        elements.set(selector, element);
      }
      return elements.get(selector);
    },
    document: { readyState: 'complete', createElement: tag => new Element(tag), createTextNode: value => ({ tag: '#text', textContent: value }) },
    apiFetch: async () => { requests++; return { ok: true, json: async () => reply }; },
    clientHeaders: () => ({}), syncUiActivity() {}, isUiActive: () => true,
    // A previous release saved permanent dismissal here. New code must ignore it.
    localStorage: { getItem: () => update.latest_version, setItem() { throw new Error('Dismissal must not persist'); } },
  });
  vm.runInContext('let nativeUiVisible = true;\n' + helpers + nativeVisibility + pageShow, context);
  return {
    context, state, pageScrollLocks, scrolls,
    flushFrames() { while (frames.length) frames.shift()(); },
    pageShow: persisted => listeners.pageshow({ persisted }),
    get: selector => context.$(selector), reply: value => { reply = value; }, requests: () => requests,
  };
}

// Text nodes have no children.
function flatten(element) { return (element.children || []).flatMap(child => [child, ...flatten(child)]); }

test('dismissal lasts for this opening only, even with an old persistent dismissal', async () => {
  const first = runtime();
  await first.context.checkForUpdates();
  assert.equal(first.get('#updateNotice').classList.contains('hidden'), false);
  first.context.dismissUpdateNotice();
  await first.context.checkForUpdates();
  assert.equal(first.get('#updateNotice').classList.contains('hidden'), true);
  const reopened = runtime();
  await reopened.context.checkForUpdates();
  assert.equal(reopened.get('#updateNotice').classList.contains('hidden'), false);
  assert.equal(reopened.get('#updateReleaseNotes').open, false);
});

test('returning to the Android app reopens a dismissed notice with notes collapsed', async () => {
  const app = runtime();
  await app.context.checkForUpdates();
  app.get('#updateReleaseNotes').open = true;
  app.context.dismissUpdateNotice();
  app.context.setNativeVisibility(false);
  app.context.setNativeVisibility(true);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(app.get('#updateNotice').classList.contains('hidden'), false);
  assert.equal(app.get('#updateReleaseNotes').open, false);
});

test('a newer version appears in the same session and notes follow the selected release', async () => {
  const app = runtime();
  await app.context.checkForUpdates(); app.context.dismissUpdateNotice();
  app.reply({ available: true, update: { ...update, latest_version: '0.6.3-dev.3', release_notes: '- Dev.3 düzeltmesi.' } });
  await app.context.checkForUpdates();
  assert.equal(app.get('#updateNotice').classList.contains('hidden'), false);
  assert.equal(app.get('#updateTitle').textContent, 'APK Cleaner Studio v0.6.3-dev.3');
  assert.match(app.get('#updateReleaseNotesBody').textContent, /Dev.3 düzeltmesi/);
});

test('polling preserves the open notes, and an up-to-date installation hides the notice', async () => {
  const app = runtime(); await app.context.checkForUpdates();
  app.get('#updateReleaseNotes').open = true;
  await app.context.checkForUpdates();
  assert.equal(app.get('#updateReleaseNotes').open, true);
  app.reply({ available: false, update: null });
  await app.context.checkForUpdates();
  assert.equal(app.get('#updateNotice').classList.contains('hidden'), true);
  assert.equal(app.state.update, null);
});

test('release headings, lists, emphasis and code are built as safe DOM nodes', () => {
  const app = runtime(); app.context.renderAvailableUpdate(update);
  const nodes = flatten(app.get('#updateReleaseNotesBody'));
  assert.equal(nodes.filter(node => node.tag === 'h3').length, 2);
  assert.equal(nodes.filter(node => node.tag === 'li').length, 2);
  assert.equal(nodes.find(node => node.tag === 'strong').textContent, 'Hata raporu');
  assert.equal(nodes.find(node => node.tag === 'code').textContent, 'APK');
  assert.equal(app.get('#updateDownload').textContent, 'İndir ve yükle');
});

test('external markup and unsafe links cannot become executable HTML', () => {
  const app = runtime();
  app.context.renderUpdateReleaseNotes('<img src=x onerror=alert(1)>\n\n[Bad](javascript:evil) [Good](https://example.test/notes) [Bad2](http://example.test)');
  const body = app.get('#updateReleaseNotesBody');
  const nodes = flatten(body);
  assert.match(body.textContent, /<img src=x onerror=alert\(1\)>/);
  assert.equal(nodes.some(node => node.tag === 'img' || node.tag === 'script'), false);
  const links = nodes.filter(node => node.tag === 'a');
  assert.equal(links.length, 1);
  assert.equal(links[0].href, 'https://example.test/notes');
  assert.equal(links[0].rel, 'noopener noreferrer');
});

test('missing notes have a clear fallback and oversized notes are bounded', () => {
  const app = runtime(); app.context.renderUpdateReleaseNotes('');
  assert.match(app.get('#updateReleaseNotesBody').textContent, /sürüm notları bulunmuyor/);
  app.context.renderUpdateReleaseNotes('x'.repeat(40000));
  assert.equal(app.get('#updateReleaseNotesBody').textContent.length, 32000);
});

test('notification descriptions use the approved test and stable wording', () => {
  const app = runtime();
  app.context.renderAvailableUpdate(update);
  assert.equal(app.get('#updateText').textContent, update.notes);
  app.context.renderAvailableUpdate({ ...update, notes: '' });
  assert.equal(app.get('#updateText').textContent, update.notes);
  app.context.renderAvailableUpdate({ ...update, notes: '', latest_version: '0.6.3' });
  assert.equal(app.get('#updateText').textContent, 'Yeni sürüm kullanıma hazır. Güncelleme notlarına aşağıdan ulaşabilirsiniz.');
});

test('a launch shows the update at the top once, while polling preserves scroll position', async () => {
  const app = runtime();
  await app.context.checkForUpdates();
  assert.equal(app.scrolls.length, 0);
  app.flushFrames();
  assert.equal(app.scrolls.length, 1);
  assert.equal(app.scrolls[0].top, 0);
  assert.equal(app.scrolls[0].behavior, 'instant');
  await app.context.checkForUpdates(); app.flushFrames();
  assert.equal(app.scrolls.length, 1);
  app.context.dismissUpdateNotice();
  app.context.restoreUpdateNotice(); app.flushFrames();
  assert.equal(app.scrolls.length, 2);
});

test('an early update response waits for pageshow before overriding restored scroll', async () => {
  const app = runtime();
  app.context.document.readyState = 'loading';
  await app.context.checkForUpdates(); app.flushFrames();
  assert.equal(app.scrolls.length, 0);
  app.context.document.readyState = 'complete';
  app.pageShow(false); app.flushFrames();
  assert.equal(app.scrolls.length, 1);
  app.pageShow(true); app.flushFrames();
  assert.equal(app.scrolls.length, 2);
});

test('no update or a dismissal before the launch frame never scrolls the page', async () => {
  const app = runtime();
  app.reply({ available: false, update: null });
  await app.context.checkForUpdates(); app.flushFrames();
  assert.equal(app.scrolls.length, 0);
  app.reply({ available: true, update });
  await app.context.checkForUpdates(); app.flushFrames();
  assert.equal(app.scrolls.length, 0);
  const fresh = runtime();
  await fresh.context.checkForUpdates();
  fresh.context.dismissUpdateNotice(); fresh.flushFrames();
  assert.equal(fresh.scrolls.length, 0);
});

test('a failed launch check does not scroll when a later background check succeeds', async () => {
  const app = runtime();
  const fetch = app.context.apiFetch;
  app.context.apiFetch = async () => { throw new Error('network unavailable'); };
  await app.context.checkForUpdates();
  app.context.apiFetch = fetch;
  await app.context.checkForUpdates(); app.flushFrames();
  assert.equal(app.scrolls.length, 0);
});

test('launch positioning does not disturb an open dialog or running job', async () => {
  for (const guard of ['dialog', 'job']) {
    const app = runtime();
    await app.context.checkForUpdates();
    if (guard === 'dialog') app.pageScrollLocks.add('installed-apps');
    else app.state.jobRunning = true;
    app.flushFrames();
    assert.equal(app.scrolls.length, 0);
    app.pageScrollLocks.clear(); app.state.jobRunning = false;
    await app.context.checkForUpdates(); app.flushFrames();
    assert.equal(app.scrolls.length, 0);
  }
});

test('dismissal collapses the panel before hiding it and does not snap open notes shut', async () => {
  const app = runtime({ animated: true });
  app.context.renderAvailableUpdate(update);
  const notice = app.get('#updateNotice');
  const details = app.get('#updateReleaseNotes');
  details.open = true;
  app.context.dismissUpdateNotice();
  assert.equal(notice.classList.contains('hidden'), false);
  assert.equal(details.open, true);
  assert.equal(notice.inert, true);
  assert.equal(notice.animation.frames[1].height, '0px');
  assert.equal(notice.animation.options.duration, 360);
  assert.equal(notice.animation.options.easing, 'cubic-bezier(.22,.61,.36,1)');
  const animation = notice.animation;
  app.context.dismissUpdateNotice();
  assert.equal(notice.animation, animation);
  animation.finish(); await Promise.resolve();
  assert.equal(notice.classList.contains('hidden'), true);
  assert.equal(notice.inert, false);
  assert.equal(details.open, false);
});

test('resuming or receiving a new version cancels an unfinished panel dismissal', async () => {
  for (const resume of [true, false]) {
    const app = runtime({ animated: true });
    app.context.renderAvailableUpdate(update);
    app.context.dismissUpdateNotice();
    const previous = app.get('#updateNotice').animation;
    if (resume) app.context.restoreUpdateNotice();
    else app.context.renderAvailableUpdate({ ...update, latest_version: '0.6.3-dev.3' });
    previous.finish(); await Promise.resolve();
    assert.equal(app.get('#updateNotice').classList.contains('hidden'), false);
    assert.equal(app.get('#updateNotice').inert, false);
  }
});

test('release notes animate both ways and rapid reversals use the current height', async () => {
  const app = runtime({ animated: true });
  const details = app.get('#updateReleaseNotes');
  const event = { preventDefault() {} };
  app.context.toggleUpdateNotes(event);
  assert.equal(details.animation.frames[0].height, '45px');
  assert.equal(details.animation.frames[1].height, '300px');
  assert.equal(details.animation.options.duration, 360);
  assert.equal(details.animation.options.easing, 'cubic-bezier(.22,.61,.36,1)');
  details.animation.currentHeight = 110;
  const opening = details.animation;
  app.context.toggleUpdateNotes(event);
  assert.equal(opening.running, false);
  assert.equal(details.animation.frames[0].height, '110px');
  assert.equal(details.animation.frames[1].height, '45px');
  assert.equal(details.open, true);
  details.animation.currentHeight = 80;
  app.context.toggleUpdateNotes(event);
  assert.equal(details.animation.frames[0].height, '80px');
  details.animation.finish(); await Promise.resolve();
  assert.equal(details.open, true);
  assert.equal(details.classList.contains('is-animating'), false);
  app.context.toggleUpdateNotes(event);
  details.animation.finish(); await Promise.resolve();
  assert.equal(details.open, false);
  assert.equal(details.querySelector('summary').attributes['aria-expanded'], 'false');
});

test('reduced motion skips panel and disclosure animation', () => {
  const app = runtime({ animated: true, reduced: true });
  app.context.renderAvailableUpdate(update);
  const details = app.get('#updateReleaseNotes');
  app.context.toggleUpdateNotes({ preventDefault() {} });
  assert.equal(details.open, true);
  assert.equal(details.animation, undefined);
  app.context.toggleUpdateNotes({ preventDefault() {} });
  assert.equal(details.open, false);
  app.context.dismissUpdateNotice();
  assert.equal(app.get('#updateNotice').classList.contains('hidden'), true);
  assert.equal(app.get('#updateNotice').animation, undefined);
});

test('certificate disclosure shares update timing without sharing its animation state', async () => {
  const app = runtime({ animated: true });
  const certificate = app.get('#toolCertificate');
  const notes = app.get('#updateReleaseNotes');
  const event = { preventDefault() {} };
  app.context.toggleInlineDisclosure(certificate, event);
  app.context.toggleUpdateNotes(event);
  assert.equal(certificate.animation.options.duration, notes.animation.options.duration);
  assert.equal(certificate.animation.options.easing, notes.animation.options.easing);
  app.context.resetUpdateNotes();
  assert.equal(certificate.animation.running, true);
  certificate.animation.finish(); await Promise.resolve();
  assert.equal(certificate.open, true);
  app.context.toggleInlineDisclosure(certificate, event);
  assert.equal(certificate.open, true);
  certificate.animation.finish(); await Promise.resolve();
  assert.equal(certificate.open, false);
});

function summaryClick(details, { prevented = false, control = false } = {}) {
  details.tagName = 'DETAILS';
  const summary = details.querySelector('summary');
  summary.parentElement = details;
  return {
    defaultPrevented: prevented,
    target: { closest: selector => selector === 'summary' ? summary : (control ? {} : null) },
    preventDefault() { this.defaultPrevented = true; },
  };
}

test('all page disclosures use the same delegated animation, including late-created menus', async () => {
  const app = runtime({ animated: true });
  for (const selector of ['#updateReleaseNotes', '#toolCertificate', '.supporter-disclosure', '#storageCard', '#installHistoryCard', '.mobile-https-banner details', '.late-created-call-trace']) {
    const details = app.get(selector);
    app.context.handleInlineDisclosureClick(summaryClick(details));
    assert.equal(details.animation.options.duration, 360);
    assert.equal(details.animation.options.easing, 'cubic-bezier(.22,.61,.36,1)');
    details.animation.finish(); await Promise.resolve();
    assert.equal(details.open, true);
    app.context.handleInlineDisclosureClick(summaryClick(details));
    assert.equal(details.open, true);
    details.animation.finish(); await Promise.resolve();
    assert.equal(details.open, false);
  }
});

test('prevented desktop disclosure clicks and summary links retain their own behavior', () => {
  const app = runtime({ animated: true });
  const desktopSupporters = app.get('.supporter-disclosure');
  desktopSupporters.open = true;
  app.context.handleInlineDisclosureClick(summaryClick(desktopSupporters, { prevented: true }));
  assert.equal(desktopSupporters.open, true);
  assert.equal(desktopSupporters.animation, undefined);
  const details = app.get('#storageCard');
  app.context.handleInlineDisclosureClick(summaryClick(details, { control: true }));
  assert.equal(details.animation, undefined);
  app.context.handleInlineDisclosureClick({ defaultPrevented: false, target: { closest: () => null } });
});

test('a desktop breakpoint cancels a mobile supporter close and leaves the list open', async () => {
  const app = runtime({ animated: true });
  const details = app.get('.supporter-disclosure');
  details.open = true;
  app.context.handleInlineDisclosureClick(summaryClick(details));
  const closing = details.animation;
  app.context.setInlineDisclosureOpen(details, true);
  closing.finish(); await Promise.resolve();
  assert.equal(details.open, true);
  assert.equal(details.classList.contains('is-animating'), false);
  assert.equal(details.querySelector('summary').attributes['aria-expanded'], 'true');
});

test('delegated disclosure clicks honor reduced motion', () => {
  const app = runtime({ animated: true, reduced: true });
  const details = app.get('#storageCard');
  app.context.handleInlineDisclosureClick(summaryClick(details));
  assert.equal(details.open, true);
  assert.equal(details.animation, undefined);
  app.context.handleInlineDisclosureClick(summaryClick(details));
  assert.equal(details.open, false);
});

test('checks and Android resume do not interrupt an active update', async () => {
  const app = runtime(); await app.context.checkForUpdates();
  app.state.updateBusy = true;
  app.get('#updateDownload').disabled = true;
  const before = app.requests();
  app.context.setNativeVisibility(false); app.context.setNativeVisibility(true);
  await app.context.checkForUpdates();
  assert.equal(app.requests(), before);
  assert.equal(app.get('#updateDownload').disabled, true);
});

test('Android resume retries a still-unwinding suspended update check', async () => {
  const app = runtime();
  let calls = 0;
  let rejectFirst;
  app.context.apiFetch = async () => {
    calls++;
    if (calls === 1) await new Promise((_resolve, reject) => { rejectFirst = reject; });
    return { ok: true, json: async () => ({ available: true, update }) };
  };
  const pending = app.context.checkForUpdates();
  app.context.setNativeVisibility(false); app.context.setNativeVisibility(true);
  rejectFirst(new Error('read aborted while backgrounded'));
  await pending;
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(calls, 2);
  assert.equal(app.get('#updateNotice').classList.contains('hidden'), false);
});

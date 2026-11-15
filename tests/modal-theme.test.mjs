import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

test('all scroll-locked popups preserve the active theme on the viewport canvas', async () => {
  const [css, app] = await Promise.all(['theme.css', 'app.js'].map(name =>
    readFile(new URL(`../studio/web/${name}`, import.meta.url), 'utf8')));
  assert.match(app, /document\.body\.classList\.add\("modal-scroll-locked"\)/);
  assert.match(app, /document\.body\.classList\.remove\("modal-scroll-locked"\)/);
  assert.match(css, /html:has\(> body\.modal-scroll-locked\)\s*\{\s*background-color:\s*var\(--paper\)/);
  assert.match(css, /html\[data-theme="light"\] \.app-dialog,\s*html\[data-theme="light"\] \.report-viewer\s*\{\s*background:\s*rgba\(224,232,228,\.28\)/);
});

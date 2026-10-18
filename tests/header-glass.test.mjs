import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

test('header glass restores the requested original palette and filter', async () => {
  const css = await readFile(new URL('../studio/web/theme.css', import.meta.url), 'utf8');
  const glass = css.slice(css.indexOf('/* Sade buzlu/sıvı cam dengesi:'), css.indexOf('/* İlk durum sorgusunda'));
  assert.match(glass, /inset: -4px -12px;/);
  assert.match(glass, /transform: scale\(1.045, 1.14\);/);
  assert.match(glass, /saturate\(116%\) brightness\(102%\) blur\(clamp\(6px, .55vw, 10px\)\)/);
  assert.match(glass, /rgba\(250,252,249,.43\), rgba\(240,247,243,.33\)/);
  assert.match(glass, /rgba\(18,30,25,.43\), rgba\(8,18,14,.33\)/);
});

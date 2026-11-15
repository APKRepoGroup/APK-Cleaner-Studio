import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const read = path => readFile(new URL(`../${path}`, import.meta.url), 'utf8');

test('both footers use the exact Patreon address and the same local brand icon', async () => {
  const [studio, landing, icon, mirror] = await Promise.all([
    read('studio/web/index.html'), read('app/page.tsx'), read('studio/web/icons/patreon.svg'), read('public/icons/patreon.svg'),
  ]);
  for (const html of [studio, landing]) {
    const footer = html.slice(html.indexOf('<footer'), html.indexOf('</footer>'));
    assert.match(footer, /href="https:\/\/www\.patreon\.com\/cw\/APKRepo" target="_blank" rel="noopener noreferrer"/);
    assert.match(footer, /<small>PATREON<\/small><b>Destek ol<\/b>/);
    assert.equal(footer.match(/<a\s/g).length, 4);
  }
  assert.equal(icon, mirror);
  assert.match(icon, /<svg\b[^>]*viewBox="0 0 38 42"/);
});

test('footer card grids fit four across on desktop and two across on narrow screens', async () => {
  for (const [file, selector] of [['studio/web/theme.css', '.footer-links'], ['app/theme.css', '.community-links']]) {
    const css = await read(file);
    const grid = count => new RegExp(`${selector.replace('.', '\\.')}\\s*\\{[^}]*grid-template-columns:\\s*repeat\\(${count}, minmax\\(0, 1fr\\)\\)`);
    assert.match(css, grid(4));
    assert.match(css, grid(2));
    assert.match(css, new RegExp(`${selector.replace('.', '\\.')} a\\s*\\{[^}]*min-height:\\s*48px;`));
    assert.match(css, /(?:patreon-icon|span\.patreon)::before\s*\{[^}]*mask:\s*url\(["'][^"']*icons\/patreon\.svg/);
  }
});

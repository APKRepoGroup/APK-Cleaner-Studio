import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

test('processing cards and the progress bar share the full application-card width', async () => {
  const css = await readFile(new URL('../studio/web/theme.css', import.meta.url), 'utf8');
  for (const selector of ['working-activity', 'working-selection', 'job-connection-notice']) {
    assert.match(css, new RegExp(`\\.${selector} \\{ width: 100%; min-width: 0;`));
    assert.doesNotMatch(css, new RegExp(`\\.${selector} \\{[^}]*625px`));
  }
  assert.match(css, /\.working > \.bar \{ width: 100%; \}/);
  assert.match(css, /\.activity-history \{ height: 240px; overflow-y: auto;/);
});

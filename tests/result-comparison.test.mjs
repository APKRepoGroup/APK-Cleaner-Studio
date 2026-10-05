import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import test from 'node:test';

const source = await readFile(new URL('../studio/web/app.js', import.meta.url), 'utf8');
const html = await readFile(new URL('../studio/web/index.html', import.meta.url), 'utf8');
const elements = new Map();
const context = vm.createContext({ humanSize: value => `${value} B`,
  $: id => {
    if (!elements.has(id)) elements.set(id, { children: [], replaceChildren(...items) { this.children = items; } });
    return elements.get(id);
  }, document: { createElement: tag => ({ tag, children: [], attributes: {},
    setAttribute(key, value) { this.attributes[key] = value; },
    append(...items) { this.children.push(...items); },
    set innerHTML(_) { throw Error('Metadata must remain text'); } }) }
});
for (const name of ['jobResultComparison', 'renderResultComparison']) {
  const start = source.indexOf(`function ${name}(`);
  vm.runInContext(source.slice(start, source.indexOf('\n}', start) + 2), context);
}
const identity = (package_name, version_code) => ({ package_name, version_code });

test('shows measured source and output changes together with actual identity snapshots', () => {
  const rows = context.jobResultComparison({ source_size_bytes: 1000, output_size_bytes: 900,
    identity_comparison: { before: identity('com.example.app', '42'), after: identity('com.example.clone', '2100000000') } });
  assert.equal(rows.length, 3);
  assert.equal(rows[0].before, '1000 B'); assert.equal(rows[0].after, '900 B');
  assert.ok(rows.every(row => row.status === 'Değişti' && row.changed));
  assert.equal(rows[1].after, 'com.example.clone'); assert.equal(rows[2].before, '42');
});
test('unchanged identities are distinguished from missing or one-sided information', () => {
  let rows = context.jobResultComparison({ identity_comparison: { before: identity('com.example.app', '0'), after: identity('com.example.app', '0') } });
  assert.equal(rows[0].status, 'Bilgi eksik'); assert.equal(rows[1].status, 'Değişmedi');
  assert.equal(rows[2].status, 'Değişmedi'); assert.equal(rows[2].after, '0');
  rows = context.jobResultComparison({ identity_comparison: { before: identity('com.example.app', '4') },
    clone: { new_package: 'com.requested.clone' }, store_updates: { version_code_after: 2100000000 } });
  assert.equal(rows[1].after, '—'); assert.equal(rows[2].after, '—');
  assert.ok(rows.every(row => !row.changed));
});
test('64-bit codes remain exact strings and unsafe numeric values are not rounded into facts', () => {
  const rows = context.jobResultComparison({ identity_comparison: {
    before: identity('com.example.app', '9223372036854775806'), after: identity('com.example.app', '9223372036854775807') } });
  assert.equal(rows[2].before, '9223372036854775806'); assert.equal(rows[2].after, '9223372036854775807');
  for (const value of [Infinity, NaN, -1, 9223372036854775807, '9223372036854775808', '1.5', 'NaN']) {
    assert.equal(context.jobResultComparison({ identity_comparison: { after: identity(null, value) } })[2].after, '—');
  }
});
test('comparison safely renders text, clears stale rows and describes missing data', () => {
  context.renderResultComparison({ identity_comparison: { before: identity('<img onerror=x>', '1'), after: identity('com.example.app', '2') } });
  const row = elements.get('#resultComparisonRows').children[1];
  assert.equal(row.children[1].textContent, '<img onerror=x>'); assert.equal(row.children[0].attributes.scope, 'row');
  context.renderResultComparison({});
  assert.equal(elements.get('#resultComparisonRows').children.length, 3);
  assert.ok(elements.get('#resultComparisonRows').children.every(row => row.children[1].textContent === '—' && row.children[2].textContent === '—'));
  assert.match(elements.get('#resultComparisonNote').textContent, /okunamadığını/);
});
test('comparison is an accessible table and does not introduce another disclosure', () => {
  assert.match(html, /<table class="result-comparison" aria-labelledby="resultComparisonTitle">/);
  assert.match(html, /<th scope="col">Önce<\/th><th scope="col">Sonra<\/th>/);
  assert.match(html, /id="resultComparisonRows"/);
});

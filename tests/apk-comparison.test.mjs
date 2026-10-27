import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import vm from 'node:vm';
const helpers = vm.createContext({});
vm.runInContext(await readFile(new URL('../studio/web/apk-comparison.js', import.meta.url), 'utf8'), helpers);
const { compare } = helpers.StudioComparison;
const apk = overrides => ({ package_name: 'com.example.app', sha256: 'a'.repeat(64), size: 100, dex_count: 2,
  package_info: { version_name: '1.0', version_code: 10, permissions: ['android.permission.INTERNET'], abis: ['arm64-v8a'] }, detections: [], ...overrides });
test('independent APKs show identity, version, architecture and real content differences', () => {
  const result = compare(apk(), apk({ package_name: 'other.app', sha256: 'b'.repeat(64), package_info: { version_name: '2.0', version_code: 20, version_code_major: 1, abis: ['x86_64'] } }));
  assert.equal(result.samePackage, false); assert.equal(result.sameContent, false);
  assert.equal(result.rows.find(row => row.label === 'Sürüm kodu').right, '1:20');
  assert.equal(result.rows.find(row => row.label === 'Paket adı').changed, true);
  assert.equal(result.rows.find(row => row.label === 'İşlemci mimarileri').changed, true);
});
test('same permission counts can still contain different permissions; duplicates are removed', () => {
  const result = compare(apk(), apk({ package_info: { permissions: ['android.permission.CAMERA', 'android.permission.CAMERA'] }, detections: [{ id: 'new', label: '<Network>' }] }));
  assert.deepEqual([...result.permissions.added], ['android.permission.CAMERA']);
  assert.deepEqual([...result.permissions.removed], ['android.permission.INTERNET']);
  assert.deepEqual([...result.networks.added], ['<Network>']);
});
test('unknown hashes do not imply identical files and unknown fields stay unknown', () => {
  const result = compare({}, {});
  assert.equal(result.sameContent, false); assert.equal(result.samePackage, false);
  assert.equal(result.rows.find(row => row.label === 'Sürüm kodu').left, 'Okunamadı');
  assert.equal(result.rows.find(row => row.label === 'İşlemci mimarileri').left, 'Okunamadı');
  assert.equal(compare(apk(), apk()).sameContent, true);
});
test('out-of-order uploads and closing the comparison cannot replace the latest result', async () => {
  const source = await readFile(new URL('../studio/web/app.js', import.meta.url), 'utf8');
  const pending = [], slot = { generation: 0 }, activeJob = { jobId: 'existing-job' };
  const context = vm.createContext({ packageComparison: { Left: slot }, state: activeJob, MAX_UPLOAD_BYTES: 1024,
    renderPackageComparison() {}, userErrorMessage: error => error.message, AbortController,
    FormData: class { append() {} }, clientHeaders: () => ({}), apiFetch: () => new Promise(resolve => pending.push(resolve)) });
  const start = source.indexOf('async function selectComparisonFile(');
  vm.runInContext(source.slice(start, source.indexOf('\nfunction packageInfoRows(', start)), context);
  const first = context.selectComparisonFile('Left', { name: 'old.apk', size: 10 });
  const second = context.selectComparisonFile('Left', { name: 'new.apk', size: 10 });
  pending[1]({ ok: true, json: async () => ({ analysis: { filename: 'new.apk' } }) }); await second;
  pending[0]({ ok: true, json: async () => ({ analysis: { filename: 'old.apk' } }) }); await first;
  assert.equal(slot.report.filename, 'new.apk'); assert.equal(activeJob.jobId, 'existing-job');
  const closing = context.selectComparisonFile('Left', { name: 'closing.apk', size: 10 }); slot.generation++; slot.report = null;
  pending[2]({ ok: true, json: async () => ({ analysis: { filename: 'closing.apk' } }) }); await closing;
  assert.equal(slot.report, null);
  await context.selectComparisonFile('Left', { name: 'split.apks', size: 10 }); assert.equal(pending.length, 3);
});

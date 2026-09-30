import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import test from 'node:test';

const source = await readFile(new URL('../studio/web/app.js', import.meta.url), 'utf8');
const helpers = source.slice(source.indexOf('function clearJobFailure()'), source.indexOf('async function pollJob()'));
function runtime() {
  const elements = new Map();
  const disclosures = [];
  const context = vm.createContext({ humanSize: bytes => `${bytes} B`, state: { jobId: 'fixture' },
    document: { createElement: tag => ({ tag, textContent: '', children: [], append(...children) { this.children.push(...children); } }) },
    setInlineDisclosureOpen: (element, expanded) => disclosures.push([element, expanded]), $: id => {
    if (!elements.has(id)) {
      const classes = new Set(['hidden']);
      elements.set(id, { textContent: '', attributes: {}, children: [], replaceChildren(...children) { this.children = children; }, setAttribute(k, v) { this.attributes[k] = v; },
        set innerHTML(_) { throw new Error('Job messages must not be interpreted as HTML'); },
        classList: { add: c => classes.add(c), remove: c => classes.delete(c), contains: c => classes.has(c),
          toggle(c, yes) { if (yes) classes.add(c); else classes.delete(c); } } });
    }
    return elements.get(id);
  } });
  vm.runInContext(helpers, context);
  return { context, elements, disclosures };
}
test('failure remains visible with the actual phase and unmodified safe explanation', () => {
  const { context, elements } = runtime();
  context.renderJobFailure({ message: 'fallback', jobFailure: { message: '<b>Çıktı doğrulanamadı</b>', stage: 'Çıktı APK doğrulanıyor' } });
  assert.equal(elements.get('#jobFailure').classList.contains('hidden'), false);
  assert.equal(elements.get('#jobFailureMessage').textContent, '<b>Çıktı doğrulanamadı</b>');
  assert.equal(elements.get('#jobFailureStage').textContent, 'Son işlem aşaması: Çıktı APK doğrulanıyor');
  assert.equal(elements.get('#diagnosticAfterFailure').classList.contains('hidden'), false);
  context.clearJobFailure();
  assert.equal(elements.get('#jobFailure').classList.contains('hidden'), true);
  assert.equal(elements.get('#diagnosticAfterFailure').classList.contains('hidden'), true);
});
test('cancellation is information, not a diagnosed error', () => {
  const { context, elements } = runtime();
  context.renderJobFailure({ jobStatus: 'cancelled', message: 'İşlem kullanıcı tarafından iptal edildi.' });
  assert.equal(elements.get('#jobFailure').attributes.role, 'status');
  assert.equal(elements.get('#jobFailureTitle').textContent, 'İşlem iptal edildi');
  assert.equal(elements.get('#jobFailureStage').textContent, '');
  assert.equal(elements.get('#diagnosticAfterFailure').classList.contains('hidden'), true);
});
test('actionable guidance does not guess a profile change or automatically retry', () => {
  const { context } = runtime();
  assert.match(context.jobFailureAdvice('Yerel işlem alanı dolu.'), /Depolama Yönetimi/);
  assert.match(context.jobFailureAdvice('DEX bileşenleri hazır değil.'), /Yerel İşlem Motoru/);
  assert.match(context.jobFailureAdvice('Çıktı doğrulanamadı: native kütüphanesi eksik.'), /güvenlik kontrolünü/);
  assert.match(context.jobFailureAdvice('Bilinmeyen hata'), /Hata raporundaki açıklamayı/);
  assert.doesNotMatch(context.jobFailureAdvice('native'), /Dengeli|otomatik/i);
});
test('terminal job states carry failure metadata through polling', async () => {
  const context = vm.createContext({ state: { jobRunning: true, jobId: 'fixture' },
    waitForUiActive: async () => {}, wait: async () => {},
    pollJob: async () => ({ status: 'error', message: 'Güvenli hata', failure: { stage: 'İmzalama', message: 'Güvenli hata' } }) });
  vm.runInContext(source.slice(source.indexOf('async function waitForJobResult('), source.indexOf('async function runJob()')), context);
  await assert.rejects(context.waitForJobResult(), error => error.jobStatus === 'error' && error.jobFailure.stage === 'İmzalama');
});
test('result summary uses measured sizes and distinguishes growth from reduction', () => {
  const { context } = runtime();
  const base = { source_size_bytes: 1000, output_size_bytes: 800, duration_seconds: 74.2,
    cleaning_profile_applied: 'deep', signed: true,
    verification: { passed: true, archive_crc: 'ok', manifest: 'ok', signature: 'ok' }, removed_files: ['one', 'two'] };
  const summary = context.jobResultSummary(base);
  assert.equal(summary.rows[2][1], '1 dk 14 sn');
  assert.equal(summary.rows[3][1], 'Gelişmiş');
  assert.equal(summary.verified, true);
  assert.match(summary.sizeChange, /200 B.*%20.*daha küçük/);
  assert.match(summary.removed, /^2 dosya/);
  assert.match(context.jobResultSummary({ ...base, output_size_bytes: 1200 }).sizeChange, /daha büyük/);
  assert.match(context.jobResultSummary({ ...base, output_size_bytes: 1000 }).sizeChange, /değişmedi/);
  assert.match(context.jobResultSummary({ ...base, split_merged: true }).sizeChange, /split paketi/);
});
test('missing, nonfinite, negative or zero metadata never produces misleading summaries', () => {
  const { context } = runtime();
  const missing = context.jobResultSummary({ mode: 'deep' });
  assert.equal(missing.rows[0][1], '—');
  assert.equal(missing.rows[2][1], '—');
  assert.equal(missing.rows[3][1], 'Bilgi kaydedilmedi');
  assert.equal(missing.verified, false);
  assert.match(missing.verification, /kaydedilmedi/);
  const invalid = context.jobResultSummary({ source_size_bytes: -1, output_size_bytes: Infinity, duration_seconds: NaN });
  assert.equal(invalid.rows[1][1], '—');
  const zero = context.jobResultSummary({ source_size_bytes: 0, output_size_bytes: 2 });
  assert.match(zero.sizeChange, /daha büyük/);
  assert.doesNotMatch(zero.sizeChange, /Infinity|NaN|%/);
  assert.equal(context.formatJobDuration(3600), '1 sa 0 dk 0 sn');
  assert.equal(context.formatJobDuration(0.1), '1 sn’den kısa');
  assert.equal(context.formatJobDuration(59.9), '1 dk 0 sn');
});
test('conversion does not claim a cleaning profile; signing alone is not verification', () => {
  const { context } = runtime();
  const converted = context.jobResultSummary({ mode: 'deep', cleaning_profile_applied: null, signed: true });
  assert.equal(converted.rows[3][1], 'Reklam temizliği uygulanmadı');
  assert.equal(converted.verified, false);
  assert.equal(context.jobResultSummary({ signed: false, verification: { passed: true } }).verified, false);
  assert.equal(context.jobResultSummary({ signed: true, verification: { passed: true, signature: 'ok' } }).verified, false);
});
test('summary is rendered as text and every result starts with its shared disclosure closed', () => {
  const { context, elements, disclosures } = runtime();
  context.renderResultSummary({ source_size_bytes: 1, output_size_bytes: 2, cleaning_profile_applied: '<img onerror=x>' });
  assert.equal(elements.get('#resultOverview').children.length, 4);
  assert.equal(elements.get('#resultOverview').children[3].children[1].textContent, 'Bilgi kaydedilmedi');
  assert.equal(disclosures[0][0], elements.get('#resultDetails'));
  assert.equal(disclosures[0][1], false);
});

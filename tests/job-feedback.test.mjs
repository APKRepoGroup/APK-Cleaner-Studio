import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import test from 'node:test';

const source = await readFile(new URL('../studio/web/app.js', import.meta.url), 'utf8');
const helpers = source.slice(source.indexOf('function clearJobFailure()'), source.indexOf('async function pollJob()'));
function runtime() {
  const elements = new Map();
  const context = vm.createContext({ state: { jobId: 'fixture' }, $: id => {
    if (!elements.has(id)) {
      const classes = new Set(['hidden']);
      elements.set(id, { textContent: '', attributes: {}, setAttribute(k, v) { this.attributes[k] = v; },
        set innerHTML(_) { throw new Error('Job messages must not be interpreted as HTML'); },
        classList: { add: c => classes.add(c), remove: c => classes.delete(c), contains: c => classes.has(c),
          toggle(c, yes) { if (yes) classes.add(c); else classes.delete(c); } } });
    }
    return elements.get(id);
  } });
  vm.runInContext(helpers, context);
  return { context, elements };
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

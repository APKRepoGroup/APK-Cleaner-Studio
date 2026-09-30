import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import test from 'node:test';

const source = await readFile(new URL('../studio/web/app.js', import.meta.url), 'utf8');
const context = vm.createContext({});
vm.runInContext(source.slice(source.indexOf('function userErrorMessage('), source.indexOf('function jobFailureAdvice(')), context);
test('network, ZIP, tool and unknown errors use Turkish messages', () => {
  for (const [raw, expected] of [
    ['Failed to fetch', 'Bağlantı'], ['No space left on device', 'depolama alanı'],
    ['Permission denied', 'erişim izni'], ['unexpected token', 'yanıtı okunamadı'],
    ['unknown vendor problem', 'beklenmeyen'],
    ['Gömülü bileşen başarısız oldu: java.lang.IllegalStateException', 'Gömülü bileşen başarısız oldu.'],
  ]) assert.ok(context.userErrorMessage({message: raw}).includes(expected), raw);
  assert.equal(context.userErrorMessage('Çıktı doğrulanamadı: gerekli DEX eksik.'), 'Çıktı doğrulanamadı: gerekli DEX eksik.');
  assert.match(context.userErrorMessage("There is no item named 'assets/audience_network/classes.dex' in the archive"), /APK arşivinde beklenen dosya/);
});
test('Turkish success notices and original technical file identifiers are preserved', () => {
  for (const text of ['İşlem kaydı silindi.', 'Profil kaydedildi.', 'Güncelleme doğrulandı; Android kurulum ekranı açıldı.',
    'APK arşivinde beklenen dosya bulunamadı: "assets/audience_network/classes.dex".'])
    assert.equal(context.userErrorMessage(text), text);
  assert.match(source, /element.textContent = userErrorMessage\(message\)/);
  assert.match(source, /const message = userErrorMessage\(error.jobFailure/);
});

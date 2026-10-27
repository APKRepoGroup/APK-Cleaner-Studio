import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import vm from 'node:vm';
const context = vm.createContext({});
vm.runInContext(await readFile(new URL('../studio/web/permissions.js', import.meta.url), 'utf8'), context);
const describe = context.StudioPermissions.describe;
const scopeText = context.StudioPermissions.scopeText;

test('manifest API bounds remain distinct from runtime grants and absent legacy metadata', () => {
  assert.match(scopeText(undefined), /kaydedilmemiş/);
  const declaration = (min, max, known = true) => ({ min_sdk: min, max_sdk: max, bounds_known: known });
  assert.equal(scopeText([declaration(1, null)]), 'Ek API sınırı belirtilmemiş');
  assert.match(scopeText([declaration(1, 32)]), /En fazla Android 12L \(API 32\)/);
  assert.match(scopeText([declaration(23, null)]), /Android 6 \(API 23\) ve sonrası/);
  assert.match(scopeText([declaration(23, 32)]), /Android 6.*Android 12L/);
  assert.match(scopeText([declaration(1, null, false)]), /okunamadı/);
  assert.match(scopeText([declaration(23, 22)]), /Geçerli bir API aralığı/);
  assert.match(scopeText([declaration(1, 32), declaration(23, null)]), /veya/);
  assert.match(scopeText([declaration(37, null)]), /API 37 ve sonrası/);
});
test('personal and special permissions have clear descriptions without malware verdicts', () => {
  assert.equal(describe('android.permission.CAMERA').category, 'Hassas erişim');
  assert.match(describe('android.permission.CAMERA').description, /İzin verildiğinde/);
  assert.equal(describe('android.permission.SYSTEM_ALERT_WINDOW').category, 'Özel erişim');
  assert.equal(describe('android.permission.INTERNET').category, 'Standart erişim');
  assert.match(describe('android.permission.READ_EXTERNAL_STORAGE').description, /Eski Android/);
});
test('unknown and inherited names preserve literal identifiers without invented claims', () => {
  for (const name of ['__proto__', 'constructor', '<img onerror=x>', 'com.example.PRIVATE']) {
    assert.equal(describe(name).name, name);
    assert.equal(describe(name).category, 'Açıklama bulunamadı');
  }
  assert.equal(describe('android.permission.UNKNOWN').title, 'Sistem izni');
});
test('permission view explains declaration versus grant and uses safe text nodes', async () => {
  const app = await readFile(new URL('../studio/web/app.js', import.meta.url), 'utf8');
  const html = await readFile(new URL('../studio/web/index.html', import.meta.url), 'utf8');
  assert.match(html, /izinlerin cihazda verildiğini veya kullanıldığını kanıtlamaz/);
  const render = app.slice(app.indexOf('function renderPackageInfo('), app.indexOf('function resetAppAppearance('));
  assert.match(render, /StudioPermissions.describe/); assert.doesNotMatch(render, /innerHTML/);
});

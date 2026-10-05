import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import test from 'node:test';

const source = await readFile(new URL('../studio/web/app.js', import.meta.url), 'utf8');
const html = await readFile(new URL('../studio/web/index.html', import.meta.url), 'utf8');
function fn(name) { const start = source.indexOf(`function ${name}(`); return source.slice(start, source.indexOf('\n}', start) + 2); }

test('compatibility metadata is explicit about missing and unverified information', () => {
  const context = vm.createContext({}); vm.runInContext(fn('packageInfoRows'), context);
  const rows = Object.fromEntries(context.packageInfoRows({ package_name: 'com.example', package_info: {
    min_sdk: 26, target_sdk: 37, version_name: '1.2', abis: ['arm64-v8a'], signature_schemes: ['V2'] } }));
  assert.equal(rows['En düşük Android'], 'Android 8.0 (API 26)');
  assert.match(rows['İşlemci desteği'], /ARM64/);
  assert.match(rows['İmza kayıtları'], /doğrulanmadı/);
  assert.equal(Object.fromEntries(context.packageInfoRows({}))['İşlemci desteği'], 'Okunamadı');
});

test('appearance is independent of ads and filenames and is not stored in presets', () => {
  assert.match(fn('updateActionState'), /customAppName/);
  assert.match(fn('updateActionState'), /appearanceLoading/);
  assert.match(source, /app_appearance: \{ name:.*customAppName.*icon: state.appearanceIcon/);
  assert.doesNotMatch(fn('currentPresetOptions'), /appearance|customAppName|customAppIcon/);
  for (const name of ['prepareAnalysisView', 'applyAnalysisResult', 'reset']) assert.match(fn(name), /resetAppAppearance\(\)/);
});

test('preview uses literal text and file decoding is bounded with stale-event protection', () => {
  assert.match(fn('renderAppearancePreview'), /\.textContent =/);
  assert.doesNotMatch(fn('renderAppearancePreview'), /innerHTML/);
  const body = source.slice(source.indexOf('async function selectAppearanceIcon()'), source.indexOf('\nfunction updateDirectSplitInstall('));
  assert.match(body, /5 \* 1024 \* 1024/); assert.match(body, /4096/);
  assert.match(body, /canvas.width = canvas.height = 256/);
  assert.match(body, /generation === state.appearanceGeneration/);
  assert.match(body, /URL.revokeObjectURL/);
});

test('new disclosures default closed and use the existing shared animation delegation', () => {
  for (const id of ['appAppearance', 'packageInfo', 'packagePermissions']) {
    const tag = html.match(new RegExp(`<details id="${id}"[^>]*>`))[0]; assert.doesNotMatch(tag, / open/);
  }
  assert.match(html, /maxlength="80"/);
  assert.match(html, /İmza kayıtlarının bulunması.*geçerli olduğu anlamına gelmez/);
  assert.match(fn('handleInlineDisclosureClick'), /toggleInlineDisclosure/);
});

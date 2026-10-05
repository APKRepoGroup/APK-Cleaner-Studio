import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import test from 'node:test';

const source = await readFile(new URL('../studio/web/app.js', import.meta.url), 'utf8');
const html = await readFile(new URL('../studio/web/index.html', import.meta.url), 'utf8');
function functionText(name) {
  const start = source.indexOf(`function ${name}(`);
  return source.slice(start, source.indexOf('\n}', start) + 2);
}
function runtime() {
  const elements = new Map();
  const get = selector => {
    if (!elements.has(selector)) elements.set(selector, {
      checked: false, disabled: false, value: '', dataset: {}, children: [], writes: 0,
      replaceChildren(...children) { this.children = children; this.writes++; },
      classList: { toggle() {} },
    });
    return elements.get(selector);
  };
  const context = vm.createContext({ $: get, ACTION_NEXT_ICON: '',
    state: { analysis: { network_count: 18 }, operation: 'patch', profile: 'balanced', patchAdsSelected: true,
      splitSelection: { abis: [], languages: [] }, messageTargets: [] },
    updateAdProfileAvailability() {}, validClonePackageName: () => true,
    document: { createElement() { return { children: [], append(...items) { this.children.push(...items); },
      set innerHTML(_) { throw Error('Summary must be safe text'); } }; } },
  });
  for (const name of ['processingSelectionSummary', 'renderSelectionSummary', 'currentPresetOptions', 'updateActionState']) {
    vm.runInContext(functionText(name), context);
  }
  return { context, get };
}
const base = { operation: 'patch', profile: 'balanced', patchAds: true, canRun: true, abis: [], languages: [] };
const rowMap = summary => Object.fromEntries(summary.rows);
test('summary identifies the actual ad operation, profile and selected extras', () => {
  const { context } = runtime();
  const rows = rowMap(context.processingSelectionSummary({ ...base, profile: 'deep', stripDebug: true, messageCount: 3 }));
  assert.equal(rows['İşlem'], 'Reklam izlerini temizle');
  assert.equal(rows['Reklam temizliği'], 'Gelişmiş profil');
  assert.match(rows['Ek işlemler'], /DEX hata ayıklama verilerini kaldır.*3 başlangıç çağrısını kaldır/);
  assert.doesNotMatch(rows['Ek işlemler'], /Play Store|optimize|RES/);
});
test('a remembered profile is not presented as active when ad cleaning is off or unsupported', () => {
  const { context, get } = runtime();
  context.state.profile = 'deep'; context.state.patchAdsSelected = false;
  get('#restrictStoreUpdates').checked = true;
  context.updateActionState();
  assert.equal(get('#cleanButton').disabled, false);
  assert.equal(get('#selectionSummaryRows').children[1].children[1].textContent, 'Uygulanmayacak');
  assert.match(get('#selectionSummaryRows').children.at(-1).children[1].textContent, /Play Store/);
  context.state.patchAdsSelected = true; context.state.analysis.network_count = 0;
  context.updateActionState();
  assert.equal(get('#selectionSummaryRows').children[1].children[1].textContent, 'Uygulanmayacak');
});
test('clone and conversion show combined cleaning only when explicitly selected', () => {
  const { context, get } = runtime();
  context.state.operation = 'clone'; get('#clonePackageName').value = 'com.example.clone';
  context.updateActionState();
  const rows = () => get('#selectionSummaryRows').children.map(row => row.children[1].textContent);
  assert.ok(rows().includes('APK’yı klonla')); assert.ok(rows().includes('com.example.clone'));
  assert.ok(rows().includes('Uygulanmayacak'));
  get('#patchAds').checked = true; context.updateActionState();
  assert.ok(rows().includes('Dengeli profil'));
  context.state.operation = 'convert'; get('#patchAds').checked = false; context.updateActionState();
  assert.ok(rows().includes('Tek APK oluştur')); assert.ok(!rows().includes('com.example.clone'));
});
test('split choices reflect deselection, with no invented ABI or language defaults', () => {
  const { context } = runtime();
  let rows = rowMap(context.processingSelectionSummary({ ...base, split: true, hasAbiChoices: true,
    hasLanguageChoices: true, abis: ['arm64-v8a'], languages: ['Türkçe'] }));
  assert.equal(rows['İşlemci'], 'ARM64'); assert.equal(rows['Dil paketleri'], 'Türkçe');
  assert.equal(rows['Split paketi'], 'Tek APK’ya birleştirilecek');
  rows = rowMap(context.processingSelectionSummary({ ...base, split: true, hasAbiChoices: true,
    hasLanguageChoices: true }));
  assert.equal(rows['İşlemci'], 'Seçim yapılmadı'); assert.equal(rows['Dil paketleri'], 'Ek dil seçilmedi');
  assert.ok(!Object.hasOwn(rowMap(context.processingSelectionSummary(base)), 'İşlemci'));
});
test('no selection and invalid clone display actionable notes matching button availability', () => {
  const { context, get } = runtime();
  context.state.patchAdsSelected = false; context.updateActionState();
  assert.equal(get('#cleanButton').disabled, true);
  assert.match(get('#selectionSummaryNote').textContent, /en az bir işlem/);
  context.state.operation = 'clone'; context.validClonePackageName = () => false; context.updateActionState();
  assert.equal(get('#cleanButton').disabled, true);
  assert.match(get('#selectionSummaryNote').textContent, /geçerli.*paket adı/);
});
test('raw clone identifiers remain literal and repeated status checks preserve summary nodes', () => {
  const { context, get } = runtime();
  context.state.operation = 'clone'; get('#clonePackageName').value = '<img onerror=x>'.repeat(20);
  context.updateActionState();
  const list = get('#selectionSummaryRows'), writes = list.writes, first = list.children[0];
  assert.ok(list.children.some(row => row.children[1].textContent === get('#clonePackageName').value));
  context.updateActionState(); assert.equal(list.writes, writes); assert.equal(list.children[0], first);
  get('#normalizeDex').checked = true; context.updateActionState();
  assert.match(list.children.at(-1).children[1].textContent, /DEX yapısını yeniden düzenle/);
  get('#normalizeDex').checked = false; context.updateActionState();
  assert.equal(list.children.at(-1).children[1].textContent, 'Seçilmedi');
});
test('summary is next to the final action, and all dynamic selection paths refresh it', () => {
  const start = html.indexOf('id="selectionSummary"'), end = html.indexOf('id="cleanButton"');
  assert.ok(start > html.indexOf('id="analysisSummary"') && start < end);
  assert.match(functionText('updateSplitSelection'), /updateActionState\(\)/);
  assert.match(functionText('renderTools'), /updateActionState\(\)/);
  assert.match(functionText('applySavedPreset'), /updateActionState\(\)/);
  assert.match(source, /#clonePackageName"\)\.addEventListener\("input", updateActionState\)/);
  assert.match(functionText('renderSelectionSummary'), /state\.messageTargets\.length/);
});

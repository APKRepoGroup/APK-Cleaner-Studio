import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import test from 'node:test';

const source = await readFile(new URL('../studio/web/app.js', import.meta.url), 'utf8');
const html = await readFile(new URL('../studio/web/index.html', import.meta.url), 'utf8');
const css = await readFile(new URL('../studio/web/theme.css', import.meta.url), 'utf8');
const helpers = source.slice(source.indexOf('function showView('), source.indexOf('function setStep('));

test('real icons have rounded square frames, without the old dark rectangular file badge', () => {
  assert.match(css, /html\[data-theme\] \.file-card \.apk\.has-app-icon\s*\{[^}]*height: 46px[^}]*border-radius: 14px[^}]*overflow: hidden[^}]*background: transparent/s);
  assert.match(css, /\.working-package-icon\.has-app-icon\s*\{[^}]*height: 40px[^}]*border-radius: 12px[^}]*overflow: hidden/s);
  assert.match(css, /\.package-app-icon\s*\{[^}]*object-fit: contain[^}]*border-radius: inherit/s);
});

function runtime() {
  const elements = new Map();
  const events = [];
  const images = [];
  const get = (id) => {
    if (!elements.has(id)) {
      const classes = new Set(['hidden']);
      let text = '';
      elements.set(id, {
        dataset: {},
        children: [],
        querySelector() { return this.children.find(child => child.className === 'package-app-icon') || null; },
        append(child) { this.children.push(child); child.parentElement = this; },
        get textContent() { return text; },
        set textContent(value) { text = value; events.push(`text:${id}`); },
        set innerHTML(_) { throw new Error('Package identity must not be interpreted as HTML'); },
        classList: {
          add: name => classes.add(name),
          remove(name) { classes.delete(name); events.push(`show:${id}`); },
          contains: name => classes.has(name),
          toggle(name, on) { if (on) classes.add(name); else classes.delete(name); },
        },
      });
    }
    return elements.get(id);
  };
  const context = vm.createContext({ state: { analysis: null, file: null }, $: get, $$: () => [], document: {
    createElement: tag => {
      const image = { tag, parentElement: null, remove() {
        if (this.parentElement) this.parentElement.children = this.parentElement.children.filter(child => child !== this);
        this.parentElement = null;
      } };
      images.push(image);
      return image;
    },
  } });
  vm.runInContext(helpers, context);
  return { context, get, events, images };
}

test('processing bar identifies the analyzed source rather than a stale selected file', () => {
  const { context, get, events } = runtime();
  context.state.analysis = { filename: 'Uygulama.apks', package_name: 'com.example.app' };
  context.state.file = { name: 'Eski uygulama.apk' };
  context.showView('#workingView');
  assert.equal(get('#workingPackageName').textContent, 'Uygulama.apks');
  assert.equal(get('#workingPackageId').textContent, 'com.example.app');
  assert.equal(get('#workingPackageId').classList.contains('hidden'), false);
  assert.ok(events.indexOf('text:#workingPackageName') < events.indexOf('show:#workingView'));
});

test('subsequent jobs replace identity and clear absent package metadata', () => {
  const { context, get } = runtime();
  context.state.analysis = { filename: 'Birinci.apk', package_name: 'com.first' };
  context.showView('#workingView');
  context.state.analysis = { filename: 'İkinci.apk' };
  context.showView('#workingView');
  assert.equal(get('#workingPackageName').textContent, 'İkinci.apk');
  assert.equal(get('#workingPackageId').textContent, '');
  assert.equal(get('#workingPackageId').classList.contains('hidden'), true);
});

test('missing or malformed metadata uses meaningful safe fallbacks', () => {
  const { context, get } = runtime();
  context.state.file = { name: ' Yerel dosya.apk ' };
  context.state.analysis = { filename: 42, package_name: false };
  context.renderWorkingPackage();
  assert.equal(get('#workingPackageName').textContent, 'Yerel dosya.apk');
  context.state.file = null;
  context.state.analysis = { package_name: 'com.example.package' };
  context.renderWorkingPackage();
  assert.equal(get('#workingPackageName').textContent, 'com.example.package');
  context.state.analysis = null;
  context.renderWorkingPackage();
  assert.equal(get('#workingPackageName').textContent, 'Seçilen paket');
  assert.equal(get('#workingPackageId').classList.contains('hidden'), true);
});

test('filenames and package identifiers stay literal and untruncated', () => {
  const { context, get } = runtime();
  const filename = '<img src=x onerror=alert(1)> Çok uzun uygulama adı '.repeat(8) + '.apk';
  const packageName = 'com.example.' + 'verylongsegment.'.repeat(10);
  context.state.analysis = { filename, package_name: packageName };
  context.renderWorkingPackage();
  assert.equal(get('#workingPackageName').textContent, filename);
  assert.equal(get('#workingPackageId').textContent, packageName);
});

test('identity bar stays inside the processing view and precedes its progress ring', () => {
  const view = html.slice(html.indexOf('<section id="workingView"'), html.indexOf('<section id="resultView"'));
  assert.ok(view.indexOf('class="working-package"') < view.indexOf('id="progressRing"'));
  assert.match(view, /aria-label="İşlenen uygulama"/);
  assert.equal((html.match(/id="workingPackageName"/g) || []).length, 1);
  assert.equal((html.match(/id="workingPackageId"/g) || []).length, 1);
});

test('analysis and progress reuse the same safe image while retaining fallback until load', () => {
  const { context, get, images } = runtime();
  const icon = 'data:image/png;base64,aGVsbG8=';
  context.state.analysis = { filename: 'app.apk', app_icon: icon };
  context.renderPackageIcon('#fileCard .apk', icon);
  context.renderWorkingPackage();
  assert.equal(images.length, 2);
  assert.equal(images[0].src, images[1].src);
  assert.equal(images[0].alt, '');
  assert.equal(get('#fileCard .apk').classList.contains('has-app-icon'), false);
  images[0].onload();
  images[1].onload();
  assert.equal(get('#fileCard .apk').classList.contains('has-app-icon'), true);
  assert.equal(get('.working-package-icon').classList.contains('has-app-icon'), true);
});

test('a missing or failed icon keeps the package fallback without disrupting processing', () => {
  const { context, get, images } = runtime();
  context.renderPackageIcon('#fileCard .apk', 'data:image/png;base64,aGVsbG8=');
  images[0].onerror();
  assert.equal(get('#fileCard .apk').children.length, 0);
  assert.equal(get('#fileCard .apk').classList.contains('has-app-icon'), false);
  context.state.analysis = { filename: 'No icon.apk' };
  context.showView('#workingView');
  assert.equal(get('#workingPackageName').textContent, 'No icon.apk');
  assert.equal(get('.working-package-icon').children.length, 0);
});

test('old image completion events cannot change the next package icon', () => {
  const { context, get, images } = runtime();
  context.renderPackageIcon('#fileCard .apk', 'data:image/png;base64,aGVsbG8=');
  const first = images[0];
  context.renderPackageIcon('#fileCard .apk', 'data:image/png;base64,d29ybGQ=');
  first.onload();
  assert.equal(get('#fileCard .apk').classList.contains('has-app-icon'), false);
  images[1].onload();
  first.onerror();
  assert.equal(get('#fileCard .apk').classList.contains('has-app-icon'), true);
  context.renderPackageIcon('#fileCard .apk', '');
  images[1].onload();
  assert.equal(get('#fileCard .apk').children.length, 0);
  assert.equal(get('#fileCard .apk').classList.contains('has-app-icon'), false);
});

test('image previews cannot fetch remote URLs or use scriptable SVG/HTML', () => {
  const { context, images } = runtime();
  for (const icon of ['https://example.invalid/icon.png', 'javascript:alert(1)', 'data:image/svg+xml;base64,YQ==',
    'data:text/html;base64,YQ==', 'data:image/png;base64,YQ==" onerror="alert(1)', 'data:image/png;base64,' + 'a'.repeat(700000)]) {
    context.renderPackageIcon('#fileCard .apk', icon);
  }
  assert.equal(images.length, 0);
});

test('new analyses and reused history jobs both update the analysis icon', () => {
  assert.match(source, /renderPackageIcon\("#fileCard \.apk", data\.analysis\.app_icon\)/);
  assert.match(source, /renderPackageIcon\("#fileCard \.apk", analysis\.app_icon\)/);
  assert.match(source, /renderPackageIcon\("\.working-package-icon", state\.analysis\?\.app_icon\)/);
});

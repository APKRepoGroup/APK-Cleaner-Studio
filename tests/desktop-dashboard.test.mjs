import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const theme = await readFile(new URL('../studio/web/theme.css', import.meta.url), 'utf8');
const script = await readFile(new URL('../studio/web/app.js', import.meta.url), 'utf8');
const html = await readFile(new URL('../studio/web/index.html', import.meta.url), 'utf8');

test('cloning fills the second column only when APK conversion is hidden', () => {
  assert.match(html, /id="convertOperation"[^>]*>[\s\S]*?<\/button>\s*<button id="cloneOperation"/);
  assert.match(theme, /#cloneOperation\s*\{\s*grid-column: 1 \/ -1;/);
  assert.match(theme, /#convertOperation\.hidden \+ #cloneOperation\s*\{\s*grid-column: auto;/);
  assert.match(theme, /@media \(max-width: 720px\)[\s\S]*?\.operation-grid,\s*\.option-grid\s*\{\s*grid-template-columns: 1fr;/);
});

test('the certificate stays in the expanding engine card without shrinking its list', () => {
  const engine = html.match(/<section id="toolCard"[\s\S]*?<\/section>/)[0];
  assert.match(engine, /<details id="toolCertificate" class="mobile-cert">/);
  assert.equal((engine.match(/class="tools-row pending"/g) || []).length, 6);
  assert.doesNotMatch(engine, /id="toolCertificate"[^>]*side-card/);
  assert.match(theme, /#toolCard\s*\{\s*max-height: none;/);
  assert.match(theme, /#toolCard > #toolList\s*\{\s*flex: 0 0 auto;/);
  assert.match(theme, /\.mobile-cert\s*\{\s*flex: 0 0 auto;[^}]*max-height: none;/);
  assert.match(script, /document\.addEventListener\("click", handleInlineDisclosureClick\)/);
});

test('desktop stages keep the sidebar and the compact feature strip, without the full guide during analysis', () => {
  assert.match(theme, /@media \(min-width:\s*901px\)[\s\S]*?\.workspace\s*\{\s*grid-template-columns:\s*minmax\(0, 1fr\) 340px/);
  assert.match(theme, /\.workspace > aside\s*\{\s*position:\s*sticky;\s*top:\s*94px/);
  assert.doesNotMatch(theme, /\.workspace\[data-stage="working"\][\s\S]{0,200}?grid-template-columns/);
  assert.match(script, /const showStartGuide = id === "#selectView" \|\| id === "#workingView" \|\| id === "#resultView"/);
  assert.match(script, /\$\("#startGuide"\)\.classList\.toggle\("hidden", !showStartGuide\)/);
  assert.match(script, /\.workspace-primary > \.features[\s\S]*?#analysisView/);
});

test('desktop header controls share a height while the motor action stays compact and single-line', () => {
  assert.match(theme, /@media \(min-width: 721px\)\s*\{\s*\.topbar :is\(\.connection, \.theme-switcher, \.tool-button\)\s*\{\s*height: 40px;/);
  assert.match(theme, /\.topbar \.tool-button\s*\{[\s\S]*?width: 148px;[\s\S]*?min-width: 148px;/);
  assert.match(theme, /\.topbar \.connection,\s*\.topbar \.tool-button\s*\{\s*white-space: nowrap;/);
  assert.match(theme, /@media \(min-width: 721px\) and \(max-width: 840px\)\s*\{\s*\.topbar\s*\{\s*grid-template-columns: minmax\(0, 1fr\) auto auto;/);
  assert.match(theme, /\.topbar \.theme-switcher\s*\{\s*grid-template-columns: repeat\(3, minmax\(0, 1fr\)\)/);
});

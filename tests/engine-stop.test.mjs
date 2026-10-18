import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import test from 'node:test';

const source = await readFile(new URL('../studio/web/app.js', import.meta.url), 'utf8');
const java = await readFile(new URL('../android/app/src/main/java/com/apkcleaner/studio/MainActivity.java', import.meta.url), 'utf8');
const service = await readFile(new URL('../android/app/src/main/java/com/apkcleaner/studio/EngineService.java', import.meta.url), 'utf8');

function runtime() {
  const calls = [], prompts = [];
  const context = vm.createContext({
    AndroidThemeBridge: { resolveEngineStop: (...args) => calls.push(args) },
    confirmAction: (...args) => new Promise(resolve => prompts.push({ args, resolve })),
    $: () => ({ getAnimations: () => [] }),
    closeAppDialog: value => prompts.at(-1)?.resolve(value),
  });
  vm.runInContext(source.slice(source.indexOf('let engineStopPrompt ='), source.indexOf('function promptAction(')), context);
  return { context, calls, prompts };
}

test('notification stop waits for explicit approval and cancellation never stops the engine', async () => {
  for (const approved of [false, true, null]) {
    const ui = runtime(), pending = ui.context.onEngineStopRequested('unique-token');
    assert.equal(ui.prompts.length, 1); assert.equal(ui.calls.length, 0);
    assert.match(ui.prompts[0].args[1], /uygulama kapatılacak/);
    ui.prompts[0].resolve(approved); await pending;
    assert.deepEqual(ui.calls, [['unique-token', Boolean(approved)]]);
  }
});

test('repeated notification taps do not duplicate the confirmation', async () => {
  const ui = runtime(), pending = ui.context.onEngineStopRequested('same-token');
  await ui.context.onEngineStopRequested('same-token');
  assert.equal(ui.prompts.length, 1);
  ui.prompts[0].resolve(false); await pending;
  assert.equal(ui.calls.length, 1);
});

test('Android Back declines a pending stop rather than closing the application', async () => {
  const ui = runtime(), pending = ui.context.onEngineStopRequested('back-token');
  ui.context.cancelEngineStopPrompt(); await pending;
  assert.deepEqual(ui.calls, [['back-token', false]]);
  const back = java.slice(java.indexOf('private void handleBack()'), java.indexOf('private final class ThemeBridge'));
  assert.match(back, /if \(pendingEngineStop != null\)/);
  assert.match(back, /cancelEngineStopPrompt/);
  assert.match(back, /return;[\s\S]*webView.canGoBack\(\)/);
});

test('stop uses a direct immutable Activity intent, never a service trampoline or unchecked shutdown', () => {
  const legacy = service.slice(service.indexOf('if (intent != null && ACTION_STOP'), service.indexOf('private void ensureEngineRunning'));
  assert.doesNotMatch(legacy, /stopEngine\(\)|stopSelf\(/);
  assert.match(service, /PendingIntent.getActivity\(this, 2, stop/);
  assert.doesNotMatch(service, /PendingIntent.getService|startActivity\(/);
  const resolution = java.slice(java.indexOf('private void resolveEngineStop('), java.indexOf('// Results from native work'));
  assert.match(resolution, /!pendingEngineStop.equals\(token\)/);
  assert.match(resolution, /if \(!confirmed\) return;[\s\S]*finishAndRemoveTask\(\)/);
  assert.match(java, /new AlertDialog.Builder\(this\)/);
  assert.match(java, /pending_engine_stop/);
  assert.match(java, /onPageStarted[\s\S]*?bridgeReady = false/);
});

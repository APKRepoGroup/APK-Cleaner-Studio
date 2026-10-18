import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import test from 'node:test';

const source = await readFile(new URL('../studio/web/app.js', import.meta.url), 'utf8');
const id = 'a'.repeat(32);
function runtime() {
  const restored = [], focused = [], messages = [];
  const state = {};
  const context = vm.createContext({ state, restoreJobSession: async job => restored.push(job),
    focusProcessingView: view => focused.push(view), toast: text => messages.push(text),
    $: () => ({ scrollIntoView() {} }), motionMedia: { matches: true },
    AndroidThemeBridge: { consumeNotificationJob: () => id },
  });
  vm.runInContext(source.slice(source.indexOf('globalThis.onJobNotification ='), source.indexOf('async function renderCompletedJob(')), context);
  return { context, state, restored, focused, messages };
}

test('cold notification launch restores the specified job instead of the remembered pointer', async () => {
  const ui = runtime(); await ui.context.restoreInitialJobSession();
  assert.deepEqual(ui.restored, [id]);
});

test('ordinary launch preserves existing session recovery and invalid notification IDs are rejected', async () => {
  const ui = runtime(); ui.context.AndroidThemeBridge.consumeNotificationJob = () => '../invalid';
  await ui.context.restoreInitialJobSession();
  assert.deepEqual(ui.restored, [undefined]);
  await ui.context.onJobNotification('../invalid'); assert.equal(ui.restored.length, 1);
});

test('notification cannot replace another working job, pending selection or recovery', async () => {
  for (const flag of ['jobRunning', 'selectionBusy', 'sessionRestoreInFlight']) {
    const ui = runtime(); ui.state[flag] = true; ui.state.jobId = 'b'.repeat(32);
    await ui.context.onJobNotification(id);
    assert.deepEqual(ui.restored, []); assert.equal(ui.messages.length, 1);
  }
  const ui = runtime(); ui.state.jobRunning = true; ui.state.jobId = id;
  await ui.context.onJobNotification(id); assert.deepEqual(ui.focused, ['#workingView']);
});

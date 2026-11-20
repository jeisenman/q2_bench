import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import { mountNewAgent } from '../src/new-agent.js';
const tick = () => new Promise(resolve => setTimeout(resolve, 0));
test('new agent form validates, retains failed input and retries', async () => {
  const dom = new JSDOM('<details open><summary>+ New Agent</summary></details>');
  Object.assign(globalThis, { document: dom.window.document, window: dom.window });
  const row = document.querySelector('details')!; let calls = 0; let completed = 0;
  const dispose = mountNewAgent(row, () => { completed++; }, async () => { if (++calls === 1) throw new Error('offline'); return {}; });
  const form = row.querySelector('form')!;
  const field = (name: string) => form.querySelector<HTMLInputElement>(`[name=${name}]`)!;
  for (const [name, value] of Object.entries({ id: 'bad id', name: 'Test', purpose: 'Purpose', instructions: 'Instructions' })) field(name).value = value;
  form.dispatchEvent(new dom.window.Event('submit', { cancelable: true })); assert.equal(calls, 0);
  field('id').value = 'test-agent'; form.dispatchEvent(new dom.window.Event('submit', { cancelable: true })); await tick();
  assert.equal(calls, 1); assert.equal(field('name').value, 'Test'); assert.match(form.textContent!, /could not be confirmed/);
  form.dispatchEvent(new dom.window.Event('submit', { cancelable: true })); await tick(); assert.equal(completed, 1);
  dispose(); dom.window.close();
});

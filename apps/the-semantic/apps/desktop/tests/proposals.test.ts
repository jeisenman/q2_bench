import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import { route, saveProposalAPI, validateResponse } from '../src/api.js';
import { mountProposals } from '../src/proposal-view.js';

const input = { title: 'Title', question: 'Question', hypothesis: 'Hypothesis', plan: 'Plan', idempotency_key: 'key' };
const record = { proposal_id: 'p1', title: 'Title', question: 'Question', hypothesis: 'Hypothesis', plan: 'Plan', status: 'DRAFT', created_at: '2026-11-18T12:00:00Z', updated_at: '2026-11-18T12:00:00Z' };
const tick = () => new Promise(resolve => setTimeout(resolve, 0));
test('proposal routes and finite save validate payload and response', async () => {
  assert.equal(route({ operation: 'proposals.list', order: 'oldest' }), '/api/research/v1/proposals?order=oldest');
  assert.equal(route({ operation: 'proposals.get', id: 'p1' }), '/api/research/v1/proposals/p1');
  assert.throws(() => route({ operation: 'proposals.get', id: '../secret' }));
  assert.throws(() => validateResponse('proposals.get', { ...record, status: 'FINISHED' }));
  const original = globalThis.fetch; let calls = 0;
  globalThis.fetch = async (url, init) => {
    calls++; assert.equal(url, 'http://127.0.0.1:5056/api/research/v1/proposals'); assert.equal(init?.method, 'POST');
    assert.deepEqual(JSON.parse(String(init?.body)), input); return new Response(JSON.stringify(record), { status: 201 });
  };
  try {
    assert.deepEqual(await saveProposalAPI(input, 'http://127.0.0.1:5056'), record);
    await assert.rejects(saveProposalAPI({ ...input, plan: ' ' }, 'http://127.0.0.1:5056'));
    await assert.rejects(saveProposalAPI({ ...input, model: 'other' }, 'http://127.0.0.1:5056'));
    assert.equal(calls, 1);
  } finally { globalThis.fetch = original; }
});
test('draft form retries with the same key and shows saved detail', async () => {
  const dom = new JSDOM('<div id="host"></div>', { url: 'http://127.0.0.1:4175' });
  Object.assign(globalThis, { document: dom.window.document });
  const keys: string[] = []; let fail = true;
  const reader = async (req: any) => req.operation === 'proposals.list' ? { proposals: [record] } : record;
  const saver = async (payload: any) => { keys.push(payload.idempotency_key); if (fail) throw Error('uncertain'); return record; };
  const host = document.querySelector<HTMLElement>('#host')!; const dispose = mountProposals(host, reader, saver); await tick();
  assert.match(host.textContent!, /Title/);
  [...host.querySelectorAll('button')].find(b => b.textContent === 'New proposal')!.click();
  for (const name of ['title', 'question', 'hypothesis', 'plan']) {
    const field = host.querySelector<HTMLInputElement>(`[name=${name}]`)!; field.value = name; field.dispatchEvent(new dom.window.Event('input'));
  }
  const form = host.querySelector('form')!; form.dispatchEvent(new dom.window.Event('submit', { cancelable: true })); await tick();
  assert.match(host.textContent!, /Save could not be confirmed/); fail = false;
  form.dispatchEvent(new dom.window.Event('submit', { cancelable: true })); await tick(); await tick();
  assert.equal(keys.length, 2); assert.equal(keys[0], keys[1]); assert.match(host.textContent!, /Draft saved/); assert.match(host.textContent!, /NOT ACCEPTED/);
  dispose(); dom.window.close();
});
test('saved proposal lists and detail hide embedded execution metadata and internal proposal references',async()=>{
  const dom=new JSDOM('<main></main>');Object.assign(globalThis,{document:dom.window.document});
  const source={...record,title:'Question\nresearch_id: private-run',question:'Public question\ntrace_id: private-trace',proposal_id:'native-reference'};const snapshot=JSON.stringify(source);
  const host=document.querySelector('main')!;const dispose=mountProposals(host,async request=>request.operation==='proposals.list'?{proposals:[source]}:source);
  await tick();host.querySelector<HTMLButtonElement>('.session-row')!.click();await tick();
  assert.match(host.textContent!,/Public question/);assert.doesNotMatch(host.textContent!,/private-run|private-trace|native-reference|Proposal ID/);assert.equal(JSON.stringify(source),snapshot);dispose();dom.window.close();
});

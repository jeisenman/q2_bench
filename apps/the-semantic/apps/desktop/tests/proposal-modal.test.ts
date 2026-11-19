import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import { openProposalModal } from '../src/proposal-modal.js';

const proposal = {
  proposal_id: 'p1', title: 'Source title', question: 'Source question',
  hypothesis: 'Source hypothesis', plan: 'Source plan', status: 'DRAFT' as const,
  created_at: '2026-11-18T12:00:00Z', updated_at: '2026-11-18T12:00:00Z',
};
const source = {
  kind: 'proposal' as const, id: 'p1', version: 2,
  content: { title: 'Latest title', question: 'Latest question', hypothesis: 'Latest hypothesis', plan: 'Latest plan' },
  updated_at: '2026-11-19T12:00:00Z',
};
const tick = () => new Promise(resolve => setTimeout(resolve, 0));
function setup() {
  const dom = new JSDOM('<button id="attachment">Open</button>', { url: 'http://127.0.0.1:4175' });
  Object.assign(globalThis, { document: dom.window.document });
  const dialogPrototype = dom.window.HTMLDialogElement.prototype;
  dialogPrototype.showModal = function() { this.setAttribute('open', ''); };
  dialogPrototype.close = function() { this.removeAttribute('open'); };
  let uuid = 0;
  Object.defineProperty(dom.window.crypto, 'randomUUID', { value: () => `123e4567-e89b-42d3-a456-${String(++uuid).padStart(12, '0')}` });
  const trigger = dom.window.document.querySelector<HTMLButtonElement>('#attachment')!;
  trigger.focus();
  const dialog = () => dom.window.document.querySelector<HTMLDialogElement>('dialog')!;
  const click = (label: string) => [...dialog().querySelectorAll('button')].find(item => item.textContent === label)!.click();
  return { dom, trigger, dialog, click };
}

test('reads latest document before enabling edit; tabs retain one set of read-only fields', async () => {
  const { dom, dialog, click } = setup(); let reads = 0;
  const dispose = openProposalModal(proposal, undefined, { reader: async request => { reads++; assert.equal(request.operation, 'documents.get'); return source; } });
  const modal = dialog();
  assert.equal(modal.open, true); assert.equal(reads, 1);
  assert.equal(modal.querySelector('[name=title]')?.getAttribute('readonly'), '');
  assert.equal(modal.querySelectorAll('[name=question]').length, 1);
  await tick();
  assert.equal((modal.querySelector<HTMLInputElement>('[name=title]')!).value, 'Latest title');
  assert.equal(modal.querySelector<HTMLTextAreaElement>('[name=plan]')!.readOnly, true);
  assert.equal(dom.window.document.activeElement?.getAttribute('aria-label'), 'Edit proposal');
  click('Plan'); assert.equal(modal.querySelector<HTMLElement>('.proposal-modal-field-question')?.hidden, true);
  click('Question & hypothesis'); assert.equal(modal.querySelector<HTMLElement>('.proposal-modal-field-plan')?.hidden, true);
  click('🖊️');
  assert.equal([...modal.querySelectorAll<HTMLInputElement | HTMLTextAreaElement>('input,textarea')].every(field => !field.readOnly), true);
  assert.equal(dom.window.document.activeElement?.getAttribute('aria-label'), 'Edit proposal');
  dispose(); dom.window.close();
});

test('cancel resets all fields without writing; save uses exact versioned payload and returns proposal identity', async () => {
  const { dom, dialog, click } = setup(); let writes = 0; let result: any;
  const savedContent = { title: 'Saved title', question: 'Saved question', hypothesis: 'Saved hypothesis', plan: 'Saved plan' };
  const dispose = openProposalModal(proposal, value => { result = value; }, {
    reader: async () => source,
    saver: async payload => { writes++; assert.deepEqual(payload, { kind: 'proposal', id: 'p1', base_version: 2, content: savedContent, idempotency_key: '123e4567-e89b-42d3-a456-000000000001' }); return { ...source, version: 3, content: savedContent, updated_at: '2026-11-19T13:00:00Z' }; },
  });
  await tick(); click('🖊️');
  (dialog().querySelector('[name=title]') as HTMLInputElement).value = 'Discard me';
  (dialog().querySelector('[name=title]') as HTMLInputElement).dispatchEvent(new dom.window.Event('input'));
  click('Cancel'); assert.equal(writes, 0); assert.equal((dialog().querySelector('[name=title]') as HTMLInputElement).value, 'Latest title');
  click('🖊️');
  for (const [name, value] of Object.entries(savedContent)) {
    const field = dialog().querySelector<HTMLInputElement | HTMLTextAreaElement>(`[name=${name}]`)!;
    field.value = value; field.dispatchEvent(new dom.window.Event('input'));
  }
  dialog().querySelector('form')!.dispatchEvent(new dom.window.Event('submit', { cancelable: true }));
  await tick();
  assert.equal(writes, 1); assert.equal(result.title, 'Saved title'); assert.equal(result.proposal_id, proposal.proposal_id);
  assert.equal(result.status, proposal.status); assert.equal(result.created_at, proposal.created_at);
  assert.equal(result.updated_at, '2026-11-19T13:00:00Z');
  assert.equal((dialog().querySelector('[name=title]') as HTMLInputElement).readOnly, true);
  dispose(); dom.window.close();
});

test('save failures retain edits, reuse retry key, and prevent duplicate submissions', async () => {
  const { dom, dialog, click } = setup(); const keys: string[] = [];
  const dispose = openProposalModal(proposal, undefined, {
    reader: async () => source,
    saver: async payload => { keys.push((payload as any).idempotency_key); throw new Error('conflict'); },
  });
  await tick(); click('🖊️');
  const field = dialog().querySelector<HTMLInputElement>('[name=title]')!;
  field.value = 'Keep this text'; field.dispatchEvent(new dom.window.Event('input'));
  const submit = () => dialog().querySelector('form')!.dispatchEvent(new dom.window.Event('submit', { cancelable: true }));
  submit(); submit(); await tick();
  assert.equal(keys.length, 1); assert.equal(field.value, 'Keep this text');
  assert.match(dialog().textContent!, /Your text is retained/);
  submit(); await tick(); assert.equal(keys.length, 2); assert.equal(keys[0], keys[1]);
  field.value = 'Changed text'; field.dispatchEvent(new dom.window.Event('input')); submit(); await tick();
  assert.notEqual(keys[2], keys[1]);
  dispose(); dom.window.close();
});

test('dirty and busy close guards block X, Escape and backdrop; clean close restores trigger focus', async () => {
  const { dom, trigger, dialog, click } = setup(); let finish!: (value: unknown) => void;
  const dispose = openProposalModal(proposal, undefined, {
    reader: async () => source,
    saver: async () => new Promise(resolve => { finish = resolve; }),
  });
  await tick(); click('🖊️');
  const field = dialog().querySelector<HTMLInputElement>('[name=title]')!;
  field.value = 'Changed'; field.dispatchEvent(new dom.window.Event('input'));
  click('×'); assert.equal(dialog().open, true); assert.match(dialog().textContent!, /Choose Save or Cancel/);
  dialog().dispatchEvent(new dom.window.Event('cancel', { cancelable: true })); assert.equal(dialog().open, true);
  dialog().dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true })); assert.equal(dialog().open, true);
  click('Cancel'); click('🖊️');
  dialog().querySelector('form')!.dispatchEvent(new dom.window.Event('submit', { cancelable: true })); await tick();
  assert.equal(typeof finish, 'function');
  dialog().dispatchEvent(new dom.window.Event('cancel', { cancelable: true })); assert.equal(dialog().open, true);
  finish({ ...source, version: 3, updated_at: '2026-11-19T13:00:00Z' }); await tick();
  click('×'); assert.equal(dom.window.document.querySelector('dialog'), null); assert.equal(dom.window.document.activeElement, trigger);
  dispose(); dom.window.close();
});

test('invalid fetch and mismatched saved identity fail closed', async () => {
  const first = setup();
  const dispose = openProposalModal(proposal, undefined, { reader: async () => ({ ...source, id: 'other' }) });
  await tick(); assert.equal(first.dialog().querySelector<HTMLButtonElement>('[aria-label="Edit proposal"]')!.disabled, true);
  assert.match(first.dialog().textContent!, /Cannot read the latest/); dispose(); first.dom.window.close();

  const second = setup();
  const close = openProposalModal(proposal, undefined, {
    reader: async () => source,
    saver: async payload => ({ ...source, id: 'other', version: (payload as any).base_version + 1 }),
  });
  await tick(); second.click('🖊️');
  second.dialog().querySelector('form')!.dispatchEvent(new second.dom.window.Event('submit', { cancelable: true }));
  await tick(); assert.match(second.dialog().textContent!, /Your text is retained/);
  assert.equal(second.dialog().open, true); close(); second.dom.window.close();
});

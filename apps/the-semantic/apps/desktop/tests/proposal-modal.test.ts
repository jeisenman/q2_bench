import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import { openProposalModal } from '../src/proposal-modal.js';
import { DocumentSaveSchema } from '../../../packages/runtime/src/documents.js';

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
test('masked proposal fields retain original source values when another field changes and history stays projected',async()=>{
  const {dom,dialog,click}=setup();let payload:any;
  const record={...source,content:{...source.content,title:'Title\nresearch_id: private-run',question:'Question\ntrace_id: private-trace',hypothesis:'{"finding":"Unverified","metrics":{"duration_seconds":12}}'}};const snapshot=JSON.stringify(record);
  const dispose=openProposalModal(proposal,undefined,{reader:async request=>request.operation==='documents.history'?{versions:[record]}:record,saver:async value=>{payload=DocumentSaveSchema.parse(value);return {...record,version:3,updated_at:'2026-11-20T12:00:00Z',content:payload.content};}});
  await tick();
  const assertHidden=()=>{assert.doesNotMatch(dialog().textContent!,/private-run|private-trace|duration_seconds/);for(const field of dialog().querySelectorAll<HTMLTextAreaElement>('textarea'))assert.doesNotMatch(field.value,/private-run|private-trace|duration_seconds/);};
  assertHidden();click('🖊️');assertHidden();
  const plan=dialog().querySelector<HTMLTextAreaElement>('[name=plan]')!;plan.value='Changed plan';plan.dispatchEvent(new dom.window.Event('input'));
  dialog().querySelector('form')!.dispatchEvent(new dom.window.Event('submit',{cancelable:true}));await tick();
  assert.deepEqual(payload.content,{...record.content,plan:'Changed plan'});assert.equal(JSON.stringify(record),snapshot);assertHidden();
  click('Version history');await tick();assertHidden();
  click('🖊️');assert.equal(dialog().querySelector<HTMLTextAreaElement>('[name=plan]')!.value,'Changed plan');click('Cancel');assertHidden();dispose();dom.window.close();
});

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
  assert.equal(modal.querySelector<HTMLButtonElement>('[aria-label="Edit proposal"]')!.getAttribute('aria-pressed'), 'true');
  click('🖊️');
  assert.equal([...modal.querySelectorAll<HTMLInputElement | HTMLTextAreaElement>('input,textarea')].every(field => !field.readOnly), true);
  assert.equal(dom.window.document.activeElement?.getAttribute('aria-label'), 'Edit proposal');
  dispose(); dom.window.close();
});

test('read mode renders safe Markdown and Cancel restores exact source text', async () => {
  const { dom, dialog, click } = setup();
  const questionText = '- **Agent:** Hypothesis v1, Sol 6.1.\n<img src=x onerror=alert(1)>';
  const record = { ...source, content: { ...source.content, question: questionText } };
  const dispose = openProposalModal(proposal, undefined, { reader: async () => record });
  await tick();
  const modal = dialog();
  const preview = modal.querySelector<HTMLElement>('[aria-label="Question preview"]')!;
  assert.equal(preview.querySelector('ul li strong')?.textContent, 'Agent:');
  assert.equal(preview.querySelector('img'), null);
  assert.ok(preview.textContent!.includes('<img src=x onerror=alert(1)>'));
  const field = modal.querySelector<HTMLTextAreaElement>('[name=question]')!;
  assert.equal(field.value, questionText);
  click('🖊️');
  assert.equal(modal.querySelector<HTMLButtonElement>('[aria-label="Edit proposal"]')!.hidden, false);
  assert.equal(modal.querySelector<HTMLButtonElement>('[aria-label="Edit proposal"]')!.getAttribute('aria-pressed'), 'true');
  field.value = 'Temporary edit'; field.dispatchEvent(new dom.window.Event('input'));
  click('🖊️'); assert.equal(field.value, 'Temporary edit');
  click('Cancel');
  assert.equal(field.value, questionText);
  assert.equal(modal.querySelector<HTMLButtonElement>('[aria-label="Edit proposal"]')!.getAttribute('aria-pressed'), 'false');
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

test('footer Save click submits once through the associated form', async () => {
  const { dom, dialog, click } = setup(); let writes = 0; let saved: any;
  const dispose = openProposalModal(proposal, value => { saved = value; }, {
    reader: async () => source,
    saver: async payload => { const request = payload as any; writes++; return { ...source, version: request.base_version + 1, content: request.content, updated_at: '2026-11-19T13:00:00Z' }; },
  });
  await tick(); click('🖊️'); click('Save'); await tick();
  assert.equal(writes, 1); assert.equal(saved.title, 'Latest title'); assert.equal(saved.updated_at, '2026-11-19T13:00:00Z');
  assert.equal(dialog().querySelector<HTMLTextAreaElement>('[name=title]')!.readOnly, true);
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

test('outside dismissal requires a matching primary pointer down and up fully outside the panel', async () => {
  const { dom, dialog } = setup();
  const dispose = openProposalModal(proposal, undefined, { reader: async () => source });
  await tick();
  const modal = dialog(); const panel = modal.querySelector<HTMLElement>('.proposal-modal-panel')!;
  panel.getBoundingClientRect = () => ({ left: 20, right: 480, top: 20, bottom: 480, width: 460, height: 460, x: 20, y: 20, toJSON() {} });
  const pointer = (target: EventTarget, type: string, x: number, y: number, id = 7) => {
    const event = new dom.window.Event(type, { bubbles: true, cancelable: true });
    Object.assign(event, { clientX: x, clientY: y, pointerId: id, isPrimary: true, button: 0 }); target.dispatchEvent(event);
  };
  pointer(modal, 'pointerdown', 10, 10); pointer(panel, 'pointerup', 10, 10);
  assert.equal(modal.open, true, 'up inside does not close');
  pointer(panel, 'pointerdown', 30, 30); pointer(modal, 'pointerup', 10, 10);
  assert.equal(modal.open, true, 'down inside does not close');
  pointer(modal, 'pointerdown', 10, 10); pointer(modal, 'pointerup', 10, 10, 8);
  assert.equal(modal.open, true, 'a different pointer does not close');
  pointer(modal, 'pointerdown', 10, 10); pointer(modal, 'pointercancel', 10, 10); pointer(modal, 'pointerup', 10, 10);
  assert.equal(modal.open, true, 'cancelled sequences do not close');
  pointer(modal, 'pointerdown', 10, 10); pointer(modal, 'pointerup', 10, 10);
  assert.equal(dom.window.document.querySelector('dialog'), null);
  dispose(); dom.window.close();
});

test('outside dismissal invokes dirty and busy close guards without losing fields', async () => {
  const { dom, dialog, click } = setup(); let finish!: (value: unknown) => void;
  const dispose = openProposalModal(proposal, undefined, {
    reader: async () => source,
    saver: async () => new Promise(resolve => { finish = resolve; }),
  });
  await tick();
  const modal = dialog(); const panel = modal.querySelector<HTMLElement>('.proposal-modal-panel')!;
  panel.getBoundingClientRect = () => ({ left: 20, right: 480, top: 20, bottom: 480, width: 460, height: 460, x: 20, y: 20, toJSON() {} });
  const outsideClick = () => {
    for (const type of ['pointerdown', 'pointerup']) {
      const event = new dom.window.Event(type, { bubbles: true });
      Object.assign(event, { clientX: 10, clientY: 10, pointerId: 9, isPrimary: true, button: 0 }); modal.dispatchEvent(event);
    }
  };
  click('🖊️');
  const title = modal.querySelector<HTMLTextAreaElement>('[name=title]')!;
  title.value = 'Keep this edit'; title.dispatchEvent(new dom.window.Event('input'));
  outsideClick(); assert.equal(modal.open, true); assert.equal(title.value, 'Keep this edit');
  assert.match(modal.textContent!, /Choose Save or Cancel/);
  click('Cancel'); click('🖊️');
  modal.querySelector('form')!.dispatchEvent(new dom.window.Event('submit', { cancelable: true })); await tick();
  outsideClick(); assert.equal(modal.open, true); assert.match(modal.textContent!, /save is in progress/i);
  finish({ ...source, version: 3, updated_at: '2026-11-19T13:00:00Z' }); await tick();
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

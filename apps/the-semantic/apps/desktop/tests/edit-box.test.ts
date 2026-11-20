import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import { mountDocumentEditor } from '../src/document-editor.js';
import { DocumentSaveSchema } from '../../../packages/runtime/src/documents.js';

const tick = () => new Promise(resolve => setTimeout(resolve, 0));
test('in-place fields keep document order, cancel restores source and save updates one view', async () => {
  const dom = new JSDOM('<h2>Title</h2><h3>Question</h3><p id="question">Question</p><div id="editor"></div>');
  Object.assign(globalThis, { document: dom.window.document, window: dom.window });
  const title = document.querySelector('h2')!; const question = document.querySelector<HTMLElement>('#question')!;
  const host = document.querySelector<HTMLElement>('#editor')!;
  const source = { kind: 'proposal' as const, id: 'p1', version: 0, updated_at: null, content: { title: 'Title', question: 'Question', hypothesis: 'Hypothesis', plan: 'Plan' } };
  let writes = 0;
  const dispose = mountDocumentEditor(host, { kind: 'proposal', id: 'p1', fieldTargets: { title, question }, onSaved: saved => { title.textContent = String(saved.content.title); } }, async () => source, async payload => {
    writes++; return { ...source, version: 1, updated_at: '2026-11-19T12:00:00Z', content: DocumentSaveSchema.parse(payload).content };
  });
  const click = (text: string) => [...host.querySelectorAll('button')].find(b => b.textContent === text)!.click();
  click('Edit'); await tick();
  const input = title.nextElementSibling as HTMLInputElement;
  assert.equal(input.name, 'title'); assert.ok(title.hidden); assert.ok(question.hidden);
  assert.equal(input.form, host.querySelector('form')); assert.ok(input.classList.contains('edit-box'));
  input.value = 'Discard'; input.dispatchEvent(new dom.window.Event('input'));
  click('Cancel'); assert.equal(writes, 0); assert.equal(title.hidden, false); assert.equal(title.textContent, 'Title');
  assert.equal(document.querySelector('[name=title]'), null);
  click('Edit'); await tick();
  const savedInput = title.nextElementSibling as HTMLInputElement; savedInput.value = 'Saved title';
  host.querySelector('form')!.dispatchEvent(new dom.window.Event('submit', { cancelable: true })); await tick();
  assert.equal(writes, 1); assert.equal(title.textContent, 'Saved title'); assert.equal(title.hidden, false);
  assert.equal(document.querySelector('[name=title]'), null);
  click('Edit'); await tick(); dispose(); assert.equal(title.hidden, false); assert.equal(document.querySelector('[name=title]'), null);
  dom.window.close();
});

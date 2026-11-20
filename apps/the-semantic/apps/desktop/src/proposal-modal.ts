import { DocumentHistorySchema, DocumentSaveSchema, DocumentSchema, type SavedDocument } from '../../../packages/runtime/src/documents.js';
import { ProposalRecordSchema, type ProposalRecord } from '../../../packages/runtime/src/proposals.js';
import { read, saveDocument } from './client.js';
import { el, button, utc } from './dom.js';
import { styleEditBox } from './edit-box.js';

type Dependencies = { reader?: typeof read; saver?: typeof saveDocument };
type FieldName = 'title' | 'question' | 'hypothesis' | 'plan';
type ProposalContent = Pick<ProposalRecord, FieldName>;

/** Opens an editable, versioned proposal document in a native dialog. */
export function openProposalModal(
  proposal: ProposalRecord,
  onSaved?: (proposal: ProposalRecord) => void,
  deps: Dependencies = {},
): () => void {
  const reader = deps.reader ?? read;
  const saver = deps.saver ?? saveDocument;
  const doc = document;
  const win = doc.defaultView!;
  const returnFocus = doc.activeElement instanceof win.HTMLElement ? doc.activeElement as HTMLElement : undefined;
  const dialog = el('dialog', '', 'proposal-modal');
  dialog.setAttribute('aria-label', 'Proposal details');
  const panel = el('section', '', 'proposal-modal-panel');
  const header = el('header', '', 'proposal-modal-header');
  const status = el('p', 'Reading saved proposal…', 'proposal-modal-status');
  status.setAttribute('role', 'status');
  const edit = button('🖊️', () => { if (current && !busy) setEditing(true); }, 'proposal-modal-edit');
  edit.setAttribute('aria-label', 'Edit proposal');
  edit.title = 'Edit proposal';
  const close = button('×', () => requestClose(), 'proposal-modal-close');
  close.setAttribute('aria-label', 'Close proposal');
  header.append(edit, close);
  const title = el('textarea', '', 'proposal-modal-title'); title.rows = 2;
  styleEditBox(title, true);
  title.name = 'title'; title.maxLength = 1000; title.readOnly = true; title.setAttribute('aria-label', 'Title');
  const tabs = el('div', '', 'proposal-modal-tabs');
  tabs.setAttribute('role', 'tablist'); tabs.setAttribute('aria-label', 'Proposal sections');
  const content = el('div', '', 'proposal-modal-content');
  const questionTab = button('Question & hypothesis', () => selectTab('question'), 'proposal-modal-tab');
  const planTab = button('Plan', () => selectTab('plan'), 'proposal-modal-tab');
  questionTab.setAttribute('role', 'tab'); planTab.setAttribute('role', 'tab');
  tabs.append(questionTab, planTab);
  const question = field('question', 'Question');
  const hypothesis = field('hypothesis', 'Hypothesis');
  const plan = field('plan', 'Plan');
  const form = el('form', '', 'proposal-modal-form');
  const actions = el('div', '', 'proposal-modal-actions edit-box-actions');
  const save = el('button', 'Save', 'proposal-modal-save'); save.type = 'submit';
  const cancel = button('Cancel', () => cancelEdit(), 'proposal-modal-cancel');
  actions.append(save, cancel);
  const historyButton = button('Version history', () => { void showHistory(); }, 'proposal-modal-history-button');
  const history = el('section', '', 'proposal-modal-history');
  form.append(title, content, actions);
  content.append(question.section, hypothesis.section, plan.section);
  panel.append(header, tabs, form, historyButton, history, status);
  dialog.append(panel);
  doc.body.append(dialog);

  let current: SavedDocument | undefined;
  let original: ProposalContent | undefined;
  let busy = false;
  let editing = false;
  let disposed = false;
  let dirty = false;
  let key: string | undefined;
  let keyContent: ProposalContent | undefined;
  const fields: Record<FieldName, HTMLInputElement | HTMLTextAreaElement> = { title, question: question.input, hypothesis: hypothesis.input, plan: plan.input };

  function field(name: Exclude<FieldName, 'title'>, labelText: string): { section: HTMLElement; input: HTMLTextAreaElement } {
    const section = el('section', '', `proposal-modal-field proposal-modal-field-${name}`);
    const label = el('label', labelText, 'proposal-modal-label');
    const input = el('textarea'); input.name = name; input.readOnly = true; input.maxLength = 16000;
    styleEditBox(input);
    input.setAttribute('aria-label', labelText); label.htmlFor = `proposal-${name}`; input.id = `proposal-${name}`;
    section.append(label, input);
    return { section, input };
  }

  function selectTab(tab: 'question' | 'plan'): void {
    const questionActive = tab === 'question';
    questionTab.setAttribute('aria-selected', String(questionActive));
    planTab.setAttribute('aria-selected', String(!questionActive));
    questionTab.classList.toggle('active', questionActive);
    planTab.classList.toggle('active', !questionActive);
    questionTab.tabIndex = questionActive ? 0 : -1;
    planTab.tabIndex = questionActive ? -1 : 0;
    question.section.hidden = !questionActive;
    hypothesis.section.hidden = !questionActive;
    plan.section.hidden = questionActive;
  }

  function fieldValues(): ProposalContent {
    return { title: title.value, question: question.input.value, hypothesis: hypothesis.input.value, plan: plan.input.value };
  }

  function markDirty(): void {
    const values = fieldValues();
    dirty = !!original && (Object.keys(original) as FieldName[]).some(name => values[name] !== original![name]);
    if (key && keyContent && (Object.keys(keyContent) as FieldName[]).some(name => values[name] !== keyContent![name])) {
      key = undefined; keyContent = undefined;
    }
  }

  function setEditing(value: boolean): void {
    editing = value;
    dialog.classList.toggle('proposal-modal-editing', value);
    for (const field of Object.values(fields)) field.readOnly = !value;
    edit.hidden = value;
    actions.hidden = !value;
    status.textContent = current ? versionLabel(current) : status.textContent;
  }

  function versionLabel(record: SavedDocument): string {
    return `Version ${record.version}${record.updated_at ? ` · Saved ${utc(record.updated_at)}` : ' · Original document'}`;
  }

  function restore(record: SavedDocument): void {
    const values = record.content as ProposalContent;
    for (const name of ['title', 'question', 'hypothesis', 'plan'] as const) fields[name].value = values[name];
  }

  function requestClose(): void {
    if (busy || (editing && dirty)) {
      status.textContent = busy ? 'A save is in progress. Wait for it to finish.' : 'Unsaved changes. Choose Save or Cancel before closing.';
      return;
    }
    dialog.close();
    dispose();
  }

  function cancelEdit(): void {
    if (busy || !current) return;
    restore(current); original = fieldValues(); dirty = false; key = undefined; keyContent = undefined;
    setEditing(false);
  }

  async function showHistory(): Promise<void> {
    if (busy) return;
    historyButton.disabled = true;
    try {
      const result = DocumentHistorySchema.parse(await reader({ operation: 'documents.history', kind: 'proposal', id: proposal.proposal_id }));
      for (const record of result.versions) {
        if (record.kind !== 'proposal' || record.id !== proposal.proposal_id) throw new Error('Document identity mismatch.');
      }
      if (disposed) return;
      history.replaceChildren(el('h3', 'Version history'));
      for (const record of [...result.versions].sort((a, b) => b.version - a.version)) {
        const item = el('details');
        item.append(el('summary', versionLabel(record)));
        for (const name of ['title', 'question', 'hypothesis', 'plan'] as const) {
          item.append(el('h4', name), el('p', String(record.content[name] ?? ''), 'proposal-modal-history-text'));
        }
        history.append(item);
      }
    } catch {
      if (!disposed) status.textContent = 'Version history is unavailable. Your current edits are still here.';
    } finally { if (!disposed) historyButton.disabled = false; }
  }

  for (const field of Object.values(fields)) field.addEventListener('input', markDirty);
  form.onsubmit = event => {
    event.preventDefault();
    if (busy || !current || !editing) return;
    const values = fieldValues();
    key ??= win.crypto.randomUUID();
    if (!keyContent) keyContent = values;
    const parsed = DocumentSaveSchema.safeParse({
      kind: 'proposal', id: proposal.proposal_id, base_version: current.version,
      content: values, idempotency_key: key,
    });
    if (!parsed.success) {
      status.textContent = 'Enter a nonblank title (up to 1,000 characters) and nonblank text in each field (up to 16,000 characters).';
      return;
    }
    busy = true; save.disabled = true; cancel.disabled = true; close.disabled = true; edit.disabled = true;
    for (const field of Object.values(fields)) field.disabled = true;
    status.textContent = 'Saving version…';
    void (async () => {
      try {
        const saved = DocumentSchema.parse(await saver(parsed.data));
        if (saved.kind !== 'proposal' || saved.id !== proposal.proposal_id) throw new Error('Saved document identity mismatch.');
        if (saved.version !== parsed.data.base_version + 1) throw new Error('Unexpected saved version.');
        const next = ProposalRecordSchema.parse({
          ...proposal, ...(saved.content as ProposalContent), updated_at: saved.updated_at,
        });
        if (disposed) return;
        current = saved; restore(saved); original = fieldValues(); dirty = false; key = undefined; keyContent = undefined;
        setEditing(false); status.textContent = versionLabel(saved); onSaved?.(next);
      } catch {
        if (!disposed) status.textContent = 'Save failed or the document changed. Your text is retained. Retry unchanged to reuse the save key; if a newer version exists, copy your text, Cancel, and reopen the proposal.';
      } finally {
        busy = false;
        if (!disposed) {
          save.disabled = false; cancel.disabled = false; close.disabled = false; edit.disabled = false;
          for (const field of Object.values(fields)) field.disabled = false;
        }
      }
    })();
  };

  const cancelDialog = (event: Event) => {
    if (busy || (editing && dirty)) {
      event.preventDefault();
      status.textContent = busy ? 'A save is in progress. Wait for it to finish.' : 'Unsaved changes. Choose Save or Cancel before closing.';
    } else {
      queueMicrotask(() => { if (!disposed) dispose(); });
    }
  };
  dialog.addEventListener('cancel', cancelDialog);
  dialog.addEventListener('click', event => {
    if (event.target === dialog && !busy && !(editing && dirty)) requestClose();
  });

  function dispose(): void {
    if (disposed) return;
    disposed = true;
    dialog.removeEventListener('cancel', cancelDialog);
    win.removeEventListener('beforeunload', beforeUnload);
    dialog.close(); dialog.remove();
    if (returnFocus?.isConnected) returnFocus.focus();
  }
  const beforeUnload = (event: BeforeUnloadEvent) => { if (busy || dirty) { event.preventDefault(); event.returnValue = ''; } };
  win.addEventListener('beforeunload', beforeUnload);
  selectTab('question');
  setEditing(false);
  dialog.showModal();
  edit.focus();
  void (async () => {
    try {
      const record = DocumentSchema.parse(await reader({ operation: 'documents.get', kind: 'proposal', id: proposal.proposal_id }));
      if (record.kind !== 'proposal' || record.id !== proposal.proposal_id) throw new Error('Document identity mismatch.');
      if (disposed) return;
      current = record; original = record.content as ProposalContent; restore(record);
      status.textContent = versionLabel(record); edit.disabled = false; historyButton.disabled = false;
    } catch {
      if (!disposed) { status.textContent = 'Cannot read the latest proposal document. Refresh and try again.'; edit.disabled = true; }
    }
  })();
  edit.disabled = true;
  historyButton.disabled = true;
  return dispose;
}

import { ProposalInputSchema, ProposalListSchema, ProposalRecordSchema, type ProposalRecord } from '../../../packages/runtime/src/proposals.js';
import { read, saveProposal } from './client.js';
import { mountDocumentEditor } from './document-editor.js';
import { el, button, utc } from './dom.js';
import { createEditBox } from './edit-box.js';

/** Displays and saves drafts without accepting or executing research. */
export function mountProposals(host: HTMLElement, reader: typeof read = read, saver: typeof saveProposal = saveProposal): () => void {
  let disposeEditor = () => {};
  let disposed = false; let generation = 0; let order: 'newest' | 'oldest' = 'newest'; let records: ProposalRecord[] = [];
  let key: string | undefined; let selected: ProposalRecord | undefined; let creating = false;
  const intro = el('section', '', 'intro');
  intro.append(el('p', 'PROPOSALS / DRAFTS', 'eyebrow'), el('h1', 'Prepare a question.'), el('p', 'Save a question, hypothesis and plan for review. Saving a draft does not run research.', 'lead'));
  const toolbar = el('div', '', 'toolbar'); const search = el('input'); search.type = 'search'; search.placeholder = 'Search proposals'; search.setAttribute('aria-label', 'Search proposals');
  const sort = el('select'); sort.setAttribute('aria-label', 'Sort proposals');
  for (const [value, label] of [['newest', 'Newest first'], ['oldest', 'Oldest first']]) { const option = el('option', label); option.value = value!; sort.append(option); }
  const status = el('p', '', 'caption'); status.setAttribute('role', 'status');
  const grid = el('div', '', 'session-grid'); const list = el('section', '', 'session-list'); const detail = el('section', '', 'session-detail');
  list.setAttribute('aria-label', 'Draft proposals'); detail.setAttribute('aria-label', 'Proposal detail');
  toolbar.append(search, sort, button('Refresh ↻', () => { void load(); }, 'refresh'), button('New proposal', () => { generation++; creating = true; selected = undefined; key = undefined; drawDetail(); }));
  grid.append(list, detail); host.append(intro, toolbar, status, grid);
  function drawList(): void {
    const query = search.value.toLowerCase();
    const filtered = records.filter(r => [r.title, r.question, r.hypothesis, r.plan, r.proposal_id].join(' ').toLowerCase().includes(query));
    list.replaceChildren(el('div', `${filtered.length} DRAFTS`, 'rule-title'));
    if (!filtered.length) list.append(el('p', records.length ? 'No proposals match this search.' : 'No draft proposals are saved.', 'empty'));
    for (const record of filtered) {
      const row = button('', () => { void open(record.proposal_id); }, `session-row${selected?.proposal_id === record.proposal_id ? ' selected' : ''}`);
      row.append(el('p', 'DRAFT', 'eyebrow'), el('h3', record.title), el('p', utc(record.created_at), 'caption')); list.append(row);
    }
  }
  function drawDetail(): void {
    disposeEditor(); detail.replaceChildren();
    if (creating) { form(); return; }
    if (!selected) { detail.append(el('h2', 'Select a proposal.'), el('p', 'Open a draft or create one for review.')); return; }
    detail.append(el('p', 'DRAFT · NOT ACCEPTED', 'eyebrow'), el('h2', selected.title), el('p', `Created ${utc(selected.created_at)}`, 'caption'));
    const text = el('div');
    const fieldTargets: Record<string, HTMLElement> = { title: detail.querySelector('h2')! };
    for (const name of ['question', 'hypothesis', 'plan'] as const) {
      fieldTargets[name] = el('p', selected[name], 'pre-line');
      text.append(el('h3', name[0]!.toUpperCase() + name.slice(1)), fieldTargets[name]!);
    }
    const drawText = () => { for (const name of ['question', 'hypothesis', 'plan'] as const) fieldTargets[name]!.textContent = selected![name]; };
    const heading = detail.querySelector('h2')!;
    const actionsHost = el('div'); const editorHost = el('div'); detail.append(actionsHost, text, editorHost);
    disposeEditor = mountDocumentEditor(editorHost, {kind:'proposal', id:selected.proposal_id, eager:true, actionsHost, fieldTargets, onSaved: record => {
      if (!selected) return; Object.assign(selected, record.content); heading.textContent = selected.title; drawText();
      const row = records.find(r => r.proposal_id === selected!.proposal_id); if(row) Object.assign(row, record.content); drawList();
    }});
    drawText();
    detail.append(el('p', `Proposal ID: ${selected.proposal_id}`, 'caption'));
  }
  function form(): void {
    const formElement = el('form'); const fields = {} as Record<'title' | 'question' | 'hypothesis' | 'plan', HTMLInputElement | HTMLTextAreaElement>;
    formElement.append(el('h2', 'New proposal'), el('p', 'All fields are required.'));
    for (const name of ['title', 'question', 'hypothesis', 'plan'] as const) {
      const label = el('label', name[0]!.toUpperCase() + name.slice(1));
      const input = createEditBox(name, label.textContent!, ''); input.required = true; input.maxLength = name === 'title' ? 1000 : 16000;
      input.setAttribute('aria-label', name[0]!.toUpperCase() + name.slice(1)); input.oninput = () => { key = undefined; }; label.append(input); formElement.append(label); fields[name] = input;
    }
    const message = el('p', '', 'error'); message.setAttribute('role', 'status'); const submit = el('button', 'Save draft'); submit.type = 'submit';
    formElement.append(submit, message); detail.append(formElement);
    formElement.onsubmit = event => {
      event.preventDefault(); key ??= crypto.randomUUID();
      const result = ProposalInputSchema.safeParse({ title: fields.title.value, question: fields.question.value, hypothesis: fields.hypothesis.value, plan: fields.plan.value, idempotency_key: key });
      if (!result.success) { message.textContent = 'Enter all fields within their length limits.'; return; }
      submit.disabled = true; Object.values(fields).forEach(field => { field.disabled = true; }); message.textContent = '';
      void (async () => {
        try {
          const record = ProposalRecordSchema.parse(await saver(result.data));
          if (disposed || !formElement.isConnected) return;
          creating = false; selected = record; key = undefined; drawDetail(); await load(); status.textContent = 'Draft saved. No research was run.';
        } catch {
          if (!disposed && formElement.isConnected) message.textContent = 'Save could not be confirmed. Retry without changing the fields to use the same key.';
        } finally { if (!disposed && formElement.isConnected) submit.disabled = false; Object.values(fields).forEach(field => { field.disabled = false; }); }
      })();
    };
  }
  async function open(id: string): Promise<void> {
    const current = ++generation; status.textContent = 'Reading draft…';
    try {
      const record = ProposalRecordSchema.parse(await reader({ operation: 'proposals.get', id }));
      if (record.proposal_id !== id) throw new Error('Proposal identity mismatch.');
      if (disposed || current !== generation) return;
      creating = false; selected = record; key = undefined; drawList(); drawDetail(); status.textContent = '';
    } catch { if (!disposed && current === generation) status.textContent = 'Cannot read this draft. Refresh and try again.'; }
  }
  async function load(): Promise<void> {
    const current = ++generation; status.textContent = 'Reading drafts…';
    try {
      const result = ProposalListSchema.parse(await reader({ operation: 'proposals.list', order }));
      if (disposed || current !== generation) return;
      records = result.proposals; drawList(); status.textContent = '';
    } catch { if (!disposed && current === generation) status.textContent = 'Cannot read drafts. The service may be unavailable or returned invalid data.'; }
  }
  search.oninput = drawList; sort.onchange = () => { order = sort.value as typeof order; void load(); };
  drawList(); drawDetail(); void load();
  return () => { disposeEditor(); disposed = true; generation++; };
}

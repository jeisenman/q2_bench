import { DocumentSchema, DocumentHistorySchema, DocumentContents, DocumentSaveSchema, type SavedDocument, type DocumentKind } from '../../../packages/runtime/src/documents.js';
import { read, saveDocument } from './client.js';
import { el, button, utc } from './dom.js';

type Options = {
  kind: DocumentKind; id: string; seed?: Record<string, unknown>;
  onSaved?: (record: SavedDocument) => void; eager?: boolean;
  actionsHost?: HTMLElement; editableRegion?: HTMLElement;
};
/** Edits a source-backed document and retains entered text on save failures. */
export function mountDocumentEditor(host: HTMLElement, options: Options, reader: typeof read = read, saver: typeof saveDocument = saveDocument): () => void {
  const doc = host.ownerDocument; const win = doc.defaultView!;
  let disposed = false; let current: SavedDocument | undefined; let dirty = false; let busy = false;
  let key: string | undefined; let editing = false;
  const panel = el('section', '', 'document-editor'); panel.setAttribute('aria-label', `${options.kind} editing`);
  const controls = el('div', '', 'document-actions'); const message = el('p', '', 'caption'); message.setAttribute('role', 'status');
  const area = el('div'); const history = el('div');
  const edit = button('Edit', () => { void start(); });
  const versions = button('Version history', () => { void showHistory(); });
  controls.append(edit, versions);
  if (options.actionsHost) options.actionsHost.append(controls); else panel.append(controls);
  panel.append(message, area, history); host.append(panel);
  function markEditing(active: boolean): void {
    options.editableRegion?.classList.toggle('document-editing', active);
    edit.setAttribute('aria-expanded', String(active));
  }
  markEditing(false);
  function checked(raw: unknown): SavedDocument {
    const record = DocumentSchema.parse(raw);
    if (record.kind !== options.kind) throw new Error('Document kind mismatch.');
    if (record.id !== options.id) {
      if (options.kind !== 'agent' || current) throw new Error('Document identity mismatch.');
      options.id = record.id; // New agent versions resolve to the stable edit anchor.
    }
    return record;
  }
  async function fetchDocument(): Promise<SavedDocument> {
    return checked(await reader({ operation: 'documents.get', kind: options.kind, id: options.id }));
  }
  function status(): void { message.textContent = current ? `Version ${current.version}${current.updated_at ? ` · Saved ${utc(current.updated_at)}` : ' · Original document'}` : ''; }
  async function start(): Promise<void> {
    if (busy || editing) return;
    busy = true; edit.disabled = true; message.textContent = 'Reading saved document…';
    try {
      const record = await fetchDocument(); if (disposed) return;
      current = record; editing = true; dirty = false; key = undefined;
      const content = record.version === 0 && options.kind === 'sme' ? { ...record.content, ...options.seed } : record.content;
      drawForm(content); markEditing(true); status();
    } catch { if (!disposed) message.textContent = 'Cannot read the saved document. Your source was not changed.'; }
    finally { busy = false; if (!disposed) edit.disabled = editing; }
  }
  function drawForm(content: Record<string, unknown>): void {
    area.replaceChildren(); history.replaceChildren();
    const form = el('form'); const fields = new Map<string, HTMLInputElement | HTMLTextAreaElement>();
    if (options.kind === 'agent') form.append(el('p', 'Use a new agent version. Existing runs keep their pinned definition.', 'caption'));
    if (options.kind === 'research') form.append(el('p', 'Edits revise this research document. Original run evidence remains in version history; saving does not run research.', 'caption'));
    if (options.kind === 'sme') form.append(el('p', 'Save a local SME draft. Upstream approval and source definitions remain separate.', 'caption'));
    for (const [name, value] of Object.entries(content)) {
      if (['allowed_tools', 'page_plugin', 'source_commit', 'id'].includes(name)) continue;
      const label = el('label', options.kind === 'sme' && name === 'text' ? 'SME definition' : name.replaceAll('_', ' ').replace(/^./, c => c.toUpperCase()));
      const field = ['title', 'name', 'version', 'model'].includes(name) ? el('input') : el('textarea');
      field.name = name; field.value = value === null ? '' : String(value); field.required = name !== 'output';
      field.maxLength = name === 'output' ? 200000 : name === 'title' && options.kind === 'research' ? 16000 : ['title','name','purpose','model'].includes(name) ? 1000 : name === 'version' ? 128 : 16000;
      field.setAttribute('aria-label', label.textContent!); field.oninput = () => { dirty = true; key = undefined; };
      label.append(field); fields.set(name, field); form.append(label);
    }
    const save = el('button', 'Save'); save.type = 'submit';
    const cancel = button('Cancel', () => { if (busy) return; editing = false; dirty = false; key = undefined; area.replaceChildren(); markEditing(false); edit.disabled = false; status(); edit.focus(); });
    form.append(save, cancel); area.append(form);
    form.onsubmit = event => {
      event.preventDefault(); if (busy || !current) return;
      const next = { ...content }; for (const [name, field] of fields) next[name] = name === 'output' && content[name] === null && field.value === '' ? null : field.value;
      const parsed = DocumentSaveSchema.safeParse({ kind: options.kind, id: options.id, base_version: current.version, content: next, idempotency_key: key ??= crypto.randomUUID() });
      if (!parsed.success || !DocumentContents[options.kind].safeParse(next).success) { message.textContent = 'Check required fields and length limits.'; return; }
      busy = true; save.disabled = true; cancel.disabled = true; fields.forEach(field => { field.disabled = true; }); message.textContent = 'Saving version…';
      void (async () => {
        try {
          const saved = checked(await saver(parsed.data));
          if (saved.version !== parsed.data.base_version + 1) throw new Error('Unexpected saved version.');
          if (disposed) return;
          current = saved; dirty = false; editing = false; key = undefined; area.replaceChildren(); markEditing(false); edit.disabled = false; status(); edit.focus();
          options.onSaved?.(saved);
        } catch { if (!disposed) message.textContent = 'Save could not be confirmed. Your text is retained. Retry unchanged to use the same save key. If another version was saved, copy your text, Cancel, and reopen Edit.'; }
        finally { busy = false; if (!disposed) { save.disabled = false; cancel.disabled = false; fields.forEach(field => { field.disabled = false; }); } }
      })();
    };
    fields.values().next().value?.focus();
  }
  async function showHistory(): Promise<void> {
    if (busy) return;
    versions.disabled = true;
    try {
      const result = DocumentHistorySchema.parse(await reader({ operation: 'documents.history', kind: options.kind, id: options.id }));
      result.versions.forEach(checked); if (disposed) return;
      history.replaceChildren(el('h3', 'Version history'));
      for (const record of [...result.versions].sort((a,b) => b.version-a.version)) {
        const item = el('details'); item.append(el('summary', `Version ${record.version} · ${record.updated_at ? utc(record.updated_at) : 'Original document'}`));
        for (const [name,value] of Object.entries(record.content)) item.append(el('h4', name.replaceAll('_',' ')), el('pre', typeof value === 'string' ? value : JSON.stringify(value), 'output'));
        history.append(item);
      }
    } catch { if (!disposed) message.textContent = 'Version history is unavailable. Refresh and try again.'; }
    finally { if (!disposed) versions.disabled = false; }
  }
  const guard = (event: MouseEvent) => {
    if (!dirty || panel.contains(event.target as Node) || controls.contains(event.target as Node)) return;
    if (!(event.target as Element).closest('button,a')) return;
    if (busy || !win.confirm('Discard unsaved document changes?')) { event.preventDefault(); event.stopImmediatePropagation(); }
    else dirty = false;
  };
  const unload = (event: BeforeUnloadEvent) => { if (dirty || busy) { event.preventDefault(); event.returnValue = ''; } };
  doc.addEventListener('click', guard, true); win.addEventListener('beforeunload', unload);
  if (options.eager) void fetchDocument().then(record => { if (!disposed && !editing && !busy && (!current || record.version >= current.version)) { current = record; status(); if (record.version > 0 && options.kind === 'sme') options.onSaved?.(record); } }).catch(() => { if (!disposed) message.textContent = 'Local document unavailable. Refresh to check saved drafts.'; });
  return () => { disposed = true; markEditing(false); if (options.actionsHost) controls.remove(); doc.removeEventListener('click', guard, true); win.removeEventListener('beforeunload', unload); };
}

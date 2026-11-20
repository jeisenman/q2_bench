import { AgentDefinitionSchema } from '../../../packages/runtime/src/contracts.js';
import { createAgent } from './client.js';
import { createEditBox } from './edit-box.js';
import { el, button } from './dom.js';

/** Mounts a new immutable agent form and protects unsaved input. */
export function mountNewAgent(row: HTMLDetailsElement, onSaved: () => void, save: typeof createAgent = createAgent): () => void {
  const doc = row.ownerDocument; const win = doc.defaultView!;
  const form = el('form', '', 'agent'); const fields = new Map<string, HTMLInputElement | HTMLTextAreaElement>();
  const status = el('p', '', 'caption'); status.setAttribute('role', 'status');
  let dirty = false; let busy = false; let disposed = false;
  const specs = [
    ['id', 'Agent ID', '', 128], ['version', 'Version', '1', 128], ['name', 'Name', '', 32000],
    ['purpose', 'Purpose', '', 32000], ['model', 'Model', 'gpt-6.1-sol', 128], ['instructions', 'Instructions', '', 32000],
  ] as const;
  for (const [name, text, initial, max] of specs) {
    const label = el('label', text); const field = createEditBox(name, text, initial);
    field.defaultValue = initial; field.required = true; field.maxLength = max; field.oninput = () => { dirty = true; };
    label.append(field); form.append(label); fields.set(name, field);
  }
  form.append(el('p', 'This agent uses no tools and the run summary results panel. Agent versions are immutable.', 'caption'), status);
  const actions = el('div', '', 'edit-box-actions'); const submit = el('button', 'Save agent'); submit.type = 'submit';
  const cancel = button('Cancel', () => { if (!busy) { form.reset(); dirty = false; status.textContent = ''; row.open = false; } });
  actions.append(submit, cancel); form.append(actions); row.append(form);
  form.onsubmit = event => {
    event.preventDefault(); if (busy) return;
    const values = Object.fromEntries([...fields].map(([name, field]) => [name, field.value]));
    const parsed = AgentDefinitionSchema.safeParse({ ...values, allowed_tools: [], page_plugin: 'run-summary' });
    if (!parsed.success) { status.textContent = 'Check required fields. Agent ID and version must use letters, numbers, dots, underscores, or hyphens.'; return; }
    busy = true; submit.disabled = cancel.disabled = true; fields.forEach(field => { field.disabled = true; }); status.textContent = 'Saving agent…';
    void save(parsed.data).then(() => { if (!disposed) { dirty = false; onSaved(); } }).catch(() => {
      if (!disposed) status.textContent = 'Save could not be confirmed. Your text is retained. Retry unchanged, or use a different ID or version if it already exists.';
    }).finally(() => { busy = false; if (!disposed) { submit.disabled = cancel.disabled = false; fields.forEach(field => { field.disabled = false; }); } });
  };
  const guard = (event: MouseEvent) => {
    const target = event.target as Element;
    if ((!dirty && !busy) || form.contains(target) || !target.closest('button,a,summary')) return;
    if (row.contains(target) && !target.closest('summary')) return;
    if (busy || !win.confirm('Discard unsaved agent changes?')) { event.preventDefault(); event.stopImmediatePropagation(); }
    else dirty = false;
  };
  const unload = (event: BeforeUnloadEvent) => { if (dirty || busy) { event.preventDefault(); event.returnValue = ''; } };
  doc.addEventListener('click', guard, true); win.addEventListener('beforeunload', unload);
  return () => { disposed = true; doc.removeEventListener('click', guard, true); win.removeEventListener('beforeunload', unload); };
}

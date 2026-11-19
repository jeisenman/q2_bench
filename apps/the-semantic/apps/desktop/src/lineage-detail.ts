import { mountDocumentEditor } from './document-editor.js';
import { nodeKey } from './lineage-contracts.js';
import { el } from './dom.js';
import type { LineageNode, Explanation } from './lineage-contracts.js';
import { lineageTitle } from './lineage-label.js';

function section(host: HTMLElement, title: string, text: string): void {
  host.append(el('h3', title), el('p', text, 'pre-line'));
}

function coverage(host: HTMLElement, explanation?: Explanation): void {
  host.append(el('h3', 'Evidence status'));
  if (!explanation) {
    host.append(el('p', 'Freshness and unresolved findings have not been checked.', 'caption'));
    return;
  }
  if (explanation.definitions_status === 'disabled') {
    host.append(el('p', 'Definition freshness checks are unavailable.', 'caption'));
  } else if (!explanation.definitions.length) {
    host.append(el('p', 'No definition freshness results were supplied.', 'caption'));
  } else if (explanation.definitions.some(state => state.stale)) {
    host.append(el('p', 'A definition is out of date with its source. See Technical evidence.', 'caption'));
  } else {
    host.append(el('p', 'Definitions match their pinned sources.', 'caption'));
  }
  const unresolved = new Set([...explanation.unresolved, ...(explanation.job_flow?.unresolved ?? [])]);
  host.append(el('p', unresolved.size
    ? `${unresolved.size} unresolved ${unresolved.size === 1 ? 'finding' : 'findings'}. See Technical evidence.`
    : 'No unresolved findings were reported for this response.', 'caption'));
  host.append(el('p', 'These checks cover this source graph only. Full coverage and runtime data equivalence are not established.', 'caption'));
}

/** Shows supplied definitions first and retains exact source evidence in a closed disclosure. */
export function lineageDetail(host: HTMLElement, node: LineageNode, explanation?: Explanation): () => void {
  const heading = el('div', '', 'sme-detail-heading');
  const title = el('div'); title.append(
    el('p', node.job ? 'JOB' : node.dataset ? 'DATASET' : 'COLUMN', 'eyebrow'),
    el('h2', lineageTitle(node.id)),
  );
  const actions = el('div', '', 'sme-edit-actions'); heading.append(title, actions); host.replaceChildren(heading);
  const meaning = node.facets.meaning;
  const sme = el('section', '', 'sme-definition'); sme.setAttribute('aria-label', 'SME definition');
  sme.append(el('h3', 'SME definition'), el('p', meaning.sme?.text.trim() ? meaning.sme.text : 'No SME definition is available for this item.', 'pre-line sme-source-text'));
  const local = el('section'); const draft = el('p', '', 'pre-line sme-local-draft'); local.append(draft); sme.append(local); host.append(sme);
  const disposeEditor = mountDocumentEditor(local, {kind:'sme', id:nodeKey(node.id), eager:true, actionsHost:actions, editableRegion:sme, seed:{text:meaning.sme?.text ?? '',source_commit:meaning.sme?.commit ?? null}, onSaved: record => { draft.textContent = `Local SME draft · Version ${record.version}\n${record.content.text}`; }});
  section(host, 'Generated business context', meaning.machine?.business_context.trim()
    ? meaning.machine.business_context
    : 'No generated business context is available for this item.');
  coverage(host, explanation);
  const evidence = el('details');
  evidence.append(el('summary', 'Technical evidence'));
  section(evidence, 'Exact identity', JSON.stringify(node.id, null, 2));
  if (meaning.machine?.description) section(evidence, 'Machine description', meaning.machine.description);
  evidence.append(el('h3', 'Source evidence'), el('pre', JSON.stringify(node, null, 2)));
  if (explanation) evidence.append(el('h3', 'Freshness and unresolved evidence'), el('pre', JSON.stringify(explanation, null, 2)));
  host.append(evidence);
  return disposeEditor;
}

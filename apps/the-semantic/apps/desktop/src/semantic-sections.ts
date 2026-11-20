import { el, button } from './dom.js';
import { nodeKey, type LineageGraph, type NodeID } from './lineage-contracts.js';
import { lineageTitle } from './lineage-label.js';

/** Local navigation retains source identities and keeps proposed connections explicit. */
export const semanticModes = ['Lineage', 'Zendesk', 'Definitions', 'Repositories', 'Research', 'PL-App Behavior'] as const;
export type SemanticMode = typeof semanticModes[number];


/** Shows repository names supplied by graph evidence without claiming source access. */
export function repositories(host: HTMLElement, graph?: LineageGraph): void {
  host.append(el('h2', 'Source repositories'), el('p', 'Inspect supplied repository references. Agentic source search is optional and is not connected.', 'lead'));
  const notice = el('section', '', 'semantic-notice');
  notice.append(el('p', 'OPTIONAL / OFF / NOT CONFIGURED', 'eyebrow'), el('h3', 'Agentic source search'), el('p', 'No repository checkout, search tool, or agent execution is configured here. Graph references do not establish repository access.'));
  host.append(notice);
  const names = new Set(graph?.nodes.flatMap(n => [ ...(n.sources ?? []), ...(n.job?.transformations?.map(t => t.source) ?? []) ]).map(s => s.repository).filter((s): s is string => Boolean(s?.trim())) ?? []);
  host.append(el('p', `${names.size} repository references in the current graph snapshot.`, 'caption'));
  if (!names.size) host.append(el('p', 'No repository inventory was supplied. Connection configuration is not available in this tab.', 'empty'));
  for (const name of [...names].sort()) {
    const row = el('article', '', 'semantic-source-row'); row.append(el('h3', name), el('p', 'Source reference only · checkout and search access unverified', 'caption')); host.append(row);
  }
}

/** Reuses Catalog's source-backed editor rather than creating a second definition store. */
export function definitions(host: HTMLElement, graph: LineageGraph | undefined, select: (id: NodeID) => void): void {
  host.append(el('h2', 'Reusable definitions'), el('p', 'SME definitions and calculation text stay pinned to their source node. Open an item to inspect its definition or edit a versioned local draft.', 'lead'), el('p', 'Local drafts do not change upstream approval. A separate calculation registry is not connected.', 'caption'));
  const nodes = graph?.nodes.filter(n => n.facets.meaning.sme?.text.trim()) ?? [];
  host.append(el('p', `${nodes.length} nodes with supplied SME definitions · Showing up to 100.`, 'caption'));
  if (!nodes.length) host.append(el('p', 'No SME definitions were supplied. Select a node in Catalog to create a local draft with the existing Edit control.', 'empty'));
  for (const node of nodes.slice(0, 100)) { const row = button('', () => select(node.id), 'semantic-source-row'); row.dataset.nodeKey = nodeKey(node.id); row.append(el('h3', lineageTitle(node.id)), el('p', node.facets.meaning.sme!.text, 'pre-line'), el('p', 'Open definition and local draft editor →', 'caption')); host.append(row); }
}

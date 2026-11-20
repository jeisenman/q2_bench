import { read } from './client.js';
import { el, button } from './dom.js';
import { GherkinListSchema, GherkinFeatureSchema, type GherkinList } from './gherkin-contracts.js';
import { appendGherkinSource } from './gherkin-detail.js';
let detailSequence = 0;
export interface GherkinState { query: string }
/** Displays literal feature evidence in a separate knowledge base. */
export function mountGherkin(host: HTMLElement, state: GherkinState, reader: typeof read = read): () => void {
  let disposed = false; let generation = 0; let page: GherkinList | undefined; let selectedPath: string | undefined;
  host.classList.add('gherkin-workspace');
  host.append(el('p', 'Read committed Gherkin specifications. Tags, Background, Scenario Outline and Examples remain verbatim. These specifications do not establish execution results or lineage links.', 'gherkin-intro'));
  const controls = el('form', '', 'toolbar'); const search = el('input'); search.type = 'search'; search.value = state.query; search.maxLength = 200; search.placeholder = 'Search feature text'; search.setAttribute('aria-label', 'Search Gherkin specifications');
  const submit = el('button', 'Search'); submit.type = 'submit';
  const modeLabel = el('label', 'Search mode '); const mode = el('select'); mode.setAttribute('aria-label', 'Gherkin search mode');
  const keyword = el('option', 'Keyword'); keyword.value = 'keyword'; const vector = el('option', 'Vector — disabled'); vector.value = 'vector'; vector.disabled = true; mode.append(keyword, vector); modeLabel.append(mode);
  const refresh = button('Refresh Gherkin source', () => { void load(0); });
  controls.append(modeLabel, search, submit, refresh); host.append(controls, el('p', 'Vector search is disabled. No embedding model or vector index is configured.', 'caption'));
  const status = el('p', '', 'caption'); status.setAttribute('aria-live', 'polite');
  const results = el('section', '', 'gherkin-results'); results.setAttribute('aria-label', 'Behavior specifications'); const detail = el('section', '', 'gherkin-detail'); detail.setAttribute('aria-label', 'Gherkin feature source');
  detail.id = `gherkin-detail-${++detailSequence}`; detail.tabIndex = -1; detail.setAttribute('aria-busy', 'false');
  const browser = el('div', '', 'gherkin-browser'); const listPanel = el('div', '', 'gherkin-list-panel');
  const navigation = el('div', '', 'toolbar');
  const previous = button('Previous features', () => { if (page) void load(Math.max(0, page.offset - 25), page.commit); });
  const next = button('Next features', () => { if (page) void load(page.offset + 25, page.commit); }); navigation.append(previous, next); listPanel.append(el('p', 'FEATURES / SELECT TO READ', 'eyebrow'), results, navigation); browser.append(listPanel, detail); host.append(status, browser);
  function busy(value: boolean): void { submit.disabled = value; refresh.disabled = value; previous.disabled = value || !page || page.offset === 0; next.disabled = value || !page?.has_more; }
  async function load(offset: number, commit?: string): Promise<void> {
    if (disposed) return;
    const current = ++generation; busy(true); page = undefined; selectedPath = undefined; results.replaceChildren(); detail.setAttribute('aria-busy', 'false'); detail.replaceChildren(el('p', 'Select a specification to read its original source, description, scenarios and examples.', 'empty')); status.textContent = 'Reading committed Gherkin source…';
    state.query = search.value.trim(); const query = state.query;
    try {
      const result = GherkinListSchema.parse(await reader(query ? { operation: 'gherkin.search', query, offset, ...(commit ? { commit } : {}) } : { operation: 'gherkin.list', offset, ...(commit ? { commit } : {}) }));
      if (disposed || current !== generation) return;
      if (result.offset !== offset || (commit && result.commit !== commit)) throw new Error('Source response does not match the requested page.');
      page = result;
      status.textContent = `${result.repository} · Commit ${result.commit} · ${result.count} matching features · Showing ${result.features.length ? result.offset + 1 : 0}–${result.offset + result.features.length}.`;
      if (!result.features.length) results.append(el('p', 'No tracked features match this search.', 'empty'));
      for (const feature of result.features) {
        const row = button('', () => { if (!disposed) void open(feature.path, result); }, 'semantic-source-row gherkin-feature-row'); row.dataset.path = feature.path; row.setAttribute('aria-pressed', 'false'); row.setAttribute('aria-controls', detail.id); row.append(el('h3', feature.title), el('p', feature.path, 'caption'), el('span', 'Read description & scenarios →', 'gherkin-read-hint')); results.append(row);
      }
    } catch { if (!disposed && current === generation) status.textContent = 'Gherkin unavailable. Check the configured checkout, exact commit, and source size limits. No substitute source is loaded.'; }
    finally { if (!disposed && current === generation) busy(false); }
  }
  async function open(path: string, source: GherkinList): Promise<void> {
    const current = ++generation; selectedPath = path; results.querySelectorAll<HTMLButtonElement>('.gherkin-feature-row').forEach(row => row.setAttribute('aria-pressed', String(row.dataset.path === selectedPath))); detail.setAttribute('aria-busy', 'true'); const loading = el('p', 'Reading exact feature source…', 'caption'); loading.setAttribute('role', 'status'); detail.replaceChildren(loading);
    detail.focus({ preventScroll: true });
    if (host.ownerDocument.defaultView?.matchMedia?.('(max-width:1100px)').matches) detail.scrollIntoView?.({ block: 'start' });
    try {
      const feature = GherkinFeatureSchema.parse(await reader({ operation: 'gherkin.feature', path, commit: source.commit }));
      if (disposed || current !== generation) return;
      if (feature.path !== path || feature.commit !== source.commit || feature.repository !== source.repository) throw new Error('Feature source identity mismatch.');
      detail.replaceChildren(el('p', 'Original Gherkin', 'eyebrow'), el('h3', feature.title), el('p', `${feature.repository} · ${feature.commit} · ${feature.path}`, 'caption'));
      appendGherkinSource(detail, feature.text, detail.id);
    } catch { if (!disposed && current === generation) { const error = el('p', 'Gherkin feature unavailable at the exact requested commit.', 'error'); error.setAttribute('role', 'alert'); detail.replaceChildren(error); } }
    finally { if (!disposed && current === generation) detail.setAttribute('aria-busy', 'false'); }
  }
  controls.onsubmit = event => { event.preventDefault(); if (!disposed) void load(0); };
  void load(0);
  return () => { disposed = true; generation++; controls.onsubmit = null; host.classList.remove('gherkin-workspace'); };
}

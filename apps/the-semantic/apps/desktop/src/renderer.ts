import './styles.css';
import './semantic-workspace.css';
import './codex.css';
import './proposal-modal.css';
import { createCodexView } from './codex-view.js';
import { AgentRecordSchema, ResearchRecordSchema, PluginManifestSchema, type ResearchRecord, type AgentRecord, type PluginManifest } from '../../../packages/runtime/src/contracts.js';
import { z } from 'zod';
import { mountDocumentEditor } from './document-editor.js';
import { read } from './client.js';
import { el, button, utc } from './dom.js';
import { mountPlugin } from './plugin.js';
import { mountProposals } from './proposal-view.js';
import { mountSemantic, type SemanticState } from './semantic-view.js';
import { mountSessions } from './session-view.js';
import { researchChatFixture } from './research-chat-fixture.js';
const codexView = createCodexView();
const semanticState:SemanticState={mode:'Lineage',query:'',help:{query:'',source:'snapshot'}};
const app = document.querySelector<HTMLElement>('#app')!;
const ledger = el('div', '', 'ledger');
const edition = el('div', '', 'edition');
edition.append(el('span', 'A LOCAL RESEARCH JOURNAL'), el('span', 'VOL. 01 · EVIDENCE & INQUIRY'));
const masthead = el('header', '', 'masthead');
masthead.append(el('p', 'The Semantic'), el('span', 'Questions become experiments. Evidence becomes understanding.'));
const nav = el('nav'); nav.setAttribute('aria-label', 'Main navigation');
const systems = el('div', '', 'systems');
const connection = el('span', 'Connecting to the research service…');
systems.append(connection, el('span', window.semantic ? 'DESKTOP · LOCAL MLFLOW EVIDENCE' : 'BROWSER PREVIEW · LOCAL SERVICE'));
const main = el('main'); ledger.append(edition, masthead, nav, systems, main); app.append(ledger);
let records: ResearchRecord[] = []; let agents: AgentRecord[] = []; let plugins: PluginManifest[] = [];
const requestedSession = new URLSearchParams(location.search).get('research_session');
let selectedSession = requestedSession && /^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$/.test(requestedSession) ? requestedSession : undefined;
let view: 'Research' | 'Proposals' | 'Agent Catalog' | 'Research Sessions' | 'Semantic Layer' | 'Codex' = selectedSession ? 'Research Sessions' : new URLSearchParams(location.search).get('tab') === 'codex' ? 'Codex' : 'Research';
let order: 'newest' | 'oldest' = 'newest'; let query = ''; let disposePlugin = () => {}; let revision = 0;
const navButtons = ['Research', 'Proposals', 'Agent Catalog', 'Research Sessions', 'Semantic Layer', 'Codex'].map(label => {
  const b = button(label, () => { view = label as typeof view; render(); if (view !== 'Research Sessions' && view !== 'Proposals' && view !== 'Semantic Layer' && view !== 'Codex') void load(); }); nav.append(b); return b;
});
function reset(): void { revision++; disposePlugin(); disposePlugin = () => {}; main.replaceChildren(); }
function intro(kicker: string, title: string, copy: string): void {
  const section = el('section', '', 'intro'); section.append(el('p', kicker, 'eyebrow'), el('h1', title), el('p', copy, 'lead')); main.append(section);
}
function render(): void {
  reset(); navButtons.forEach(b => b.classList.toggle('active', b.textContent === view));
  if (view === 'Research') renderResearch();
  else if (view === 'Proposals') disposePlugin = mountProposals(main);
  else if (view === 'Agent Catalog') renderAgents();
  else if (view === 'Research Sessions') disposePlugin = mountSessions(main, { selectedID: selectedSession,
    onSelect: id => { selectedSession = id; }, onConnection: message => { connection.textContent = message; } });
  else if (view === 'Codex') disposePlugin = codexView.mount(main);
  else disposePlugin=mountSemantic(main,semanticState,read,id=>{view='Research';navButtons.forEach(b=>b.classList.toggle('active',b.textContent===view));void detail(id);});
}
function renderResearch(): void {
  intro('01 / RESEARCH', 'A question worth\nfollowing.', 'A live ledger of accepted questions, bounded experiments and retained results. Open a record to follow its evidence from question to conclusion.');
  const toolbar = el('div', '', 'toolbar');
  const search = el('input'); search.type = 'search'; search.placeholder = 'Search titles, questions, agents, or run IDs'; search.value = query;
  search.setAttribute('aria-label', 'Search research');
  const select = el('select'); select.setAttribute('aria-label', 'Sort by date');
  for (const [value, label] of [['newest', 'Newest first'], ['oldest', 'Oldest first']]) {
    const option = el('option', label); option.value = value!; select.append(option);
  }
  select.value = order;
  const list = el('div', '', 'question-list');
  const drawList = () => {
    const filtered = records.filter(r => [r.title, r.question, r.agent_id, r.research_id].join(' ').toLowerCase().includes(query.toLowerCase()))
      .sort((a, b) => (Date.parse(b.created_at) - Date.parse(a.created_at)) * (order === 'newest' ? 1 : -1));
    list.replaceChildren();
    if (!filtered.length) list.append(el('p', records.length ? 'No records match this search.' : 'No research records are available. Register an agent and run an accepted plan with the CLI, then refresh.', 'empty'));
    for (const record of filtered) {
      const row = button('', () => { void detail(record.research_id); }, 'question-row');
      const meta = el('div', '', 'row-meta'); meta.append(el('span', `${record.status} · ${record.agent_id} / ${record.agent_version}`, 'eyebrow'), el('span', utc(record.created_at)));
      row.append(meta, el('h2', record.title), el('p', record.question), el('span', 'Open evidence →', 'record-id'));
      list.append(row);
    }
    count.textContent = `${filtered.length} OF ${records.length} RECORDS`;
  };
  const count = el('span', '', 'count');
  search.oninput = () => { query = search.value; drawList(); };
  select.onchange = () => { order = select.value as typeof order; drawList(); };
  toolbar.append(search, select, button('Refresh ↻', () => { void load(); }, 'refresh'));
  const grid = el('div', '', 'editorial-grid'); const feature = el('section', '', 'feature');
  feature.append(el('div', 'THE RESEARCH LEDGER', 'rule-title'), toolbar, count, list);
  const aside = el('aside', '', 'desk-aside');
  aside.append(el('p', 'FROM QUESTION TO EVIDENCE', 'eyebrow'), el('h2', 'Keep the\nwhole chain.'),
    el('p', 'Each accepted plan pins an agent definition and one attempt. MLflow retains the output, metrics and trace.'),
    el('div', '01   Question\n02   Hypothesis\n03   Experiment\n04   Runs\n05   Graphs', 'chain-note'),
    el('p', 'Dates use UTC. Missing measurements remain missing. Refresh reads the current service record.', 'caption'));
  grid.append(feature, aside); main.append(grid); drawList();
}
async function detail(id: string): Promise<void> {
  reset(); const current = revision;
  main.append(el('p', 'Loading the exact retained record…'));
  try {
    const r = ResearchRecordSchema.parse(await read({ operation: 'research.get', id }));
    if (revision !== current) return;
    main.replaceChildren(button('← Research ledger', () => render(), 'back'));
    intro(`RESEARCH / ${r.status}`, r.title, r.question);
    const meta = el('div', '', 'run-bar');
    meta.append(el('strong', `${r.agent_id} / ${r.agent_version}`), el('span', r.model), el('span', utc(r.created_at)));
    main.append(meta);
    const editorHost = el('div'); main.append(editorHost);
    const disposeEditor = mountDocumentEditor(editorHost, { kind:'research', id:r.research_id, eager:true, onSaved: () => { void detail(id); } });
    disposePlugin = disposeEditor;
    const steps = el('div', '', 'provenance');
    for (const [i, label] of ['Question', 'Hypothesis', 'Experiment', 'Runs', 'Graphs'].entries()) {
      const a = el('a', `0${i + 1}  ${label}`); a.href = `#stage-${i}`; steps.append(a);
    }
    main.append(steps);
    const content = el('div', '', 'detail-grid'); const body = el('div'); const aside = el('aside', '', 'evidence');
    body.append(researchChatFixture());
    const stage = (number: number, title: string, value: string) => {
      const section = el('section', '', 'stage'); section.id = `stage-${number}`;
      section.append(el('p', `0${number + 1} / ${title.toUpperCase()}`, 'eyebrow'), el('h2', title), el('p', value, 'pre-line')); body.append(section); return section;
    };
    stage(0, 'Question', r.question); stage(1, 'Hypothesis', r.hypothesis); stage(2, 'Experiment', r.plan);
    const runs = stage(3, 'Runs', `One accepted attempt · ${r.status}`);
    runs.append(el('h3', 'Retained output'), el('pre', r.output ?? 'No output is retained.', 'output'));
    if (r.error) runs.append(el('p', r.error, 'error'));
    const graphs = stage(4, 'Graphs', 'Measurements and output from the selected retained attempt.');
    const pluginHost = el('div', '', 'plugin-host'); graphs.append(pluginHost);
    const manifest = plugins.find(p => p.id === r.page_plugin);
    if (manifest) { const closePlugin = mountPlugin(pluginHost, manifest, r); disposePlugin = () => { disposeEditor(); closePlugin(); }; }
    else pluginHost.append(el('p', `Page plugin unavailable: ${r.page_plugin}.`, 'error'));
    aside.append(el('p', 'PINNED EVIDENCE', 'eyebrow'), el('p', 'The document can contain saved edits. Metrics, trace and execution identifiers refer to the original run. Version history retains the original document.', 'caption'));
    const technical = el('details', '', 'technical-evidence'); technical.append(el('summary', 'Technical evidence'));
    for (const [label, value] of [['Research run', r.research_id], ['Experiment run', r.experiment_id], ['Attempt run', r.attempt_id],
      ['Agent digest', r.agent_definition_digest], ['Trace ID', r.trace_id ?? 'No trace retained']]) {
      technical.append(el('h4', label), el('code', value));
    }
    aside.append(el('h4', 'Updated'), el('p', utc(r.updated_at), 'metric'), el('h4', 'Time limit'),
      el('p', `${r.max_seconds} seconds`, 'metric'), technical, el('h4', 'Retained metrics'));
    if (!Object.keys(r.metrics).length) aside.append(el('p', 'No metrics retained.'));
    for (const [key, value] of Object.entries(r.metrics)) aside.append(el('p', `${key}: ${value}`, 'metric'));
    content.append(body, aside); main.append(content);
  } catch { if (revision === current) main.replaceChildren(button('← Research ledger', render, 'back'), el('p', 'The selected record could not be read. Refresh the service connection.', 'error')); }
}
function renderAgents(): void {
  intro('02 / AGENT CATALOG', 'Every result has\nan author.', 'Immutable agent definitions establish the instructions, model and tool scope used by each experiment. Research records pin the definition digest.');
  main.append(button('Refresh catalog ↻', () => { void load(); }, 'refresh'));
  const list = el('div', '', 'agent-list');
  if (!agents.length) list.append(el('p', 'No registered agents. Use researcher-codex agent put <agent.json>, then refresh.', 'empty'));
  for (const agent of agents) {
    const section = el('article', '', 'agent');
    section.append(el('p', `${agent.id} / VERSION ${agent.version}`, 'eyebrow'), el('h2', agent.name), el('p', agent.purpose),
      el('h4', 'Model'), el('code', agent.model), el('h4', 'Instructions'), el('p', agent.instructions, 'pre-line'),
      el('h4', 'Tool scope'), el('p', 'No tools · one text-only model call'), el('h4', 'Page plugin'), el('code', agent.page_plugin),
      el('h4', 'Definition digest'), el('code', agent.definition_digest), el('h4', 'MLflow agent run'), el('code', agent.mlflow_run_id));
    const stopEditor = mountDocumentEditor(section, {kind:'agent', id:agent.mlflow_run_id, onSaved: () => { void load(); }});
    const previous = disposePlugin; disposePlugin = () => { previous(); stopEditor(); };
    list.append(section);
  }
  main.append(list);
}
async function load(): Promise<void> {
  const current = revision;
  connection.textContent = 'READING LOCAL EVIDENCE…';
  try {
    const [research, catalog, manifests] = await Promise.all([
      read({ operation: 'research.list', order }), read({ operation: 'agents.list' }), read({ operation: 'plugins.list' }),
    ]);
    if (revision !== current) return;
    records = z.object({ research: z.array(ResearchRecordSchema).max(100) }).strict().parse(research).research;
    agents = z.object({ agents: z.array(AgentRecordSchema).max(100) }).strict().parse(catalog).agents;
    plugins = z.object({ plugins: z.array(PluginManifestSchema).max(20) }).strict().parse(manifests).plugins;
    connection.textContent = '● CONNECTED · RESEARCH API 127.0.0.1:5056'; render();
  } catch {
    if (revision !== current) return;
    connection.textContent = '○ RESEARCH SERVICE UNAVAILABLE'; render();
    const warning = el('div', '', 'error service-error');
    warning.append(el('p', 'Cannot read the local research service. Start the API on 127.0.0.1:5056, then refresh.'), button('Retry connection', () => { void load(); })); main.prepend(warning);
  }
}
render(); if (!selectedSession) void load();

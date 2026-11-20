import './styles.css';
import './semantic-workspace.css';
import './gherkin-workspace.css';
import './codex.css';
import './proposal-modal.css';
import './research-chat-fixture.css';
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
import { chatDisplayText } from './chat-display.js';
import { mountNewAgent } from './new-agent.js';

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
  const section = el('section', '', 'intro'); section.append(el('p', kicker, 'eyebrow'), el('h1', chatDisplayText(title)), el('p', chatDisplayText(copy), 'lead')); main.append(section);
}
function agentName(id: string): string { return chatDisplayText(agents.find(agent => agent.id === id)?.name ?? 'Agent definition unavailable'); }
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
  const search = el('input'); search.type = 'search'; search.placeholder = 'Search titles, questions, or agents'; search.value = query;
  search.setAttribute('aria-label', 'Search research');
  const select = el('select'); select.setAttribute('aria-label', 'Sort by date');
  for (const [value, label] of [['newest', 'Newest first'], ['oldest', 'Oldest first']]) {
    const option = el('option', label); option.value = value!; select.append(option);
  }
  select.value = order;
  const list = el('div', '', 'question-list');
  const drawList = () => {
    const filtered = records.filter(r => [r.title, r.question, agentName(r.agent_id)].join(' ').toLowerCase().includes(query.toLowerCase()))
      .sort((a, b) => (Date.parse(b.created_at) - Date.parse(a.created_at)) * (order === 'newest' ? 1 : -1));
    list.replaceChildren();
    if (!filtered.length) list.append(el('p', records.length ? 'No records match this search.' : 'No research records are available. Register an agent and run an accepted plan with the CLI, then refresh.', 'empty'));
    for (const record of filtered) {
      const row = button('', () => { void detail(record.research_id); }, 'question-row');
      const meta = el('div', '', 'row-meta'); meta.append(el('span', `${record.status} · ${agentName(record.agent_id)} · Version ${chatDisplayText(record.agent_version)}`, 'eyebrow'), el('span', utc(record.created_at)));
      row.append(meta, el('h2', chatDisplayText(record.title)), el('p', chatDisplayText(record.question)), el('span', 'Open evidence →', 'record-id'));
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
    el('p', 'Each accepted plan uses a versioned agent definition. The service keeps its evidence for future lookups.'),
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
    meta.append(el('strong', `${agentName(r.agent_id)} · Version ${chatDisplayText(r.agent_version)}`), el('span', chatDisplayText(r.model)), el('span', utc(r.created_at)));
    main.append(meta);
    const editorHost = el('div'); main.append(editorHost);
    const fieldTargets: Record<string, HTMLElement> = { title: main.querySelector('h1')! };
    const disposeEditor = mountDocumentEditor(editorHost, { kind:'research', id:r.research_id, eager:true, fieldTargets, onSaved: () => { void detail(id); } });
    disposePlugin = disposeEditor;
    const steps = el('div', '', 'provenance');
    const chatStep = el('a', '00  Chat thread'); chatStep.href = '#stage-chat'; steps.append(chatStep);
    for (const [i, label] of ['Question', 'Hypothesis', 'Experiment', 'Runs', 'Graphs'].entries()) {
      const a = el('a', `0${i + 1}  ${label}`); a.href = `#stage-${i}`; steps.append(a);
    }
    main.append(steps);
    const content = el('div', '', 'detail-grid'); const body = el('div'); const aside = el('aside', '', 'evidence');
    body.append(researchChatFixture());
    const stage = (number: number, title: string, value: string) => {
      const section = el('section', '', 'stage'); section.id = `stage-${number}`;
      section.append(el('p', `0${number + 1} / ${title.toUpperCase()}`, 'eyebrow'), el('h2', title), el('p', chatDisplayText(value), 'pre-line')); body.append(section); return section;
    };
    for (const [index, name, label] of [[0, 'question', 'Question'], [1, 'hypothesis', 'Hypothesis'], [2, 'plan', 'Experiment']] as const) {
      fieldTargets[name] = stage(index, label, r[name]).querySelector('.pre-line')!;
    }
    const runs = stage(3, 'Runs', `Selected result · ${r.status}`);
    runs.append(el('h3', 'Retained output'), el('pre', chatDisplayText(r.output ?? 'No output is retained.'), 'output'));
    fieldTargets.output = runs.querySelector('.output')!;
    const graphs = stage(4, 'Graphs', 'The results panel shows the selected result.');
    const pluginHost = el('div', '', 'plugin-host'); graphs.append(pluginHost);
    const manifest = plugins.find(p => p.id === r.page_plugin);
    if (manifest) { const closePlugin = mountPlugin(pluginHost, manifest, r); disposePlugin = () => { disposeEditor(); closePlugin(); }; }
    else pluginHost.append(el('p', 'The results panel is unavailable.', 'error'));
    aside.append(el('p', 'PINNED EVIDENCE', 'eyebrow'), el('p', 'The document can contain saved edits. The service retains source references for lookups. Version history retains the original document.', 'caption'));
    const technical = el('details', '', 'technical-evidence'); technical.append(el('summary', 'Technical evidence'));
    technical.append(el('h4', 'Run references'), el('p', 'Source references are retained for service lookups.'));
    technical.append(el('h4', 'Agent definition'), el('p', 'The agent definition version is pinned to this record.'));
    technical.append(el('h4', 'Execution trace'), el('p', r.trace_id ? 'Retained.' : 'Not retained.'));
    aside.append(el('h4', 'Updated'), el('p', utc(r.updated_at), 'metric'), technical);
    content.append(body, aside); main.append(content);
  } catch { if (revision === current) main.replaceChildren(button('← Research ledger', render, 'back'), el('p', 'The selected record could not be read. Refresh the service connection.', 'error')); }
}
function renderAgents(): void {
  intro('02 / AGENT CATALOG', 'Every result has\nan author.', 'Immutable agent definitions establish the instructions, model and tool scope used by each experiment. Research records retain the agent definition version.');
  main.append(button('Refresh catalog ↻', () => { void load(); }, 'refresh'));
  const list = el('div', '', 'agent-list');
  if (!agents.length) list.append(el('p', 'No registered agents.', 'empty'));
  for (const agent of agents) {
    const row = el('details', '', 'agent-row');
    const summary = el('summary', '', 'agent-summary');
    summary.append(el('span', chatDisplayText(agent.name), 'agent-name'), el('span', `Version ${chatDisplayText(agent.version)}`, 'agent-version'));
    const section = el('article', '', 'agent');
    section.append(el('p', `Version ${chatDisplayText(agent.version)}`, 'eyebrow'), el('h2', chatDisplayText(agent.name)), el('p', chatDisplayText(agent.purpose)),
      el('h4', 'Model'), el('code', chatDisplayText(agent.model)), el('h4', 'Instructions'), el('p', chatDisplayText(agent.instructions), 'pre-line'),
      el('h4', 'Tool scope'), el('p', 'No tools · one text-only model call'), el('h4', 'Results panel'), el('p', 'Run summary'),
      el('h4', 'Stored definition'), el('p', 'Versioned and retained for future lookups.'));
    const fieldTargets: Record<string, HTMLElement> = { name: section.querySelector('h2')!, purpose: section.querySelector('h2 + p')!, instructions: section.querySelector('.pre-line')!, model: section.querySelector('code')! };
    const version = el('span', chatDisplayText(agent.version)); section.querySelector('.eyebrow')!.replaceChildren(document.createTextNode('Version '), version); fieldTargets.version = version;
    const stopEditor = mountDocumentEditor(section, {kind:'agent', id:agent.mlflow_run_id, fieldTargets, onSaved: () => { void load(); }});
    const previous = disposePlugin; disposePlugin = () => { previous(); stopEditor(); };
    row.append(summary, section);
    list.append(row);
  }
  const addRow = el('details', '', 'agent-row new-agent-row');
  addRow.append(el('summary', '+ New Agent', 'agent-summary agent-name'));
  const stopNewAgent = mountNewAgent(addRow, () => { void load(); });
  const previous = disposePlugin; disposePlugin = () => { previous(); stopNewAgent(); };
  list.append(addRow);
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

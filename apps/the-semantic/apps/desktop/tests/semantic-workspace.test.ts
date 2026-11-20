import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import { mountSemantic, type SemanticState } from '../src/semantic-view.js';
import { mountSemanticArchive } from '../src/semantic-archive.js';
import type { LineageGraph } from '../src/lineage-contracts.js';
import type { ResearchRecord } from '../../../packages/runtime/src/contracts.js';
const graph: LineageGraph = { nodes: [{ id: { namespace: 'fixture/source', name: 'margin' }, dataset: {}, sources: [{ repository: 'declared-repository' }], facets: { meaning: { sme: { text: 'Return divided by capital.', commit: 'fixture' } } } }], edges: [], aliases: [], unresolved: [] };
const settle = (): Promise<void> => new Promise(resolve => setImmediate(resolve));
function setup(): { host: HTMLElement; dom: JSDOM } {
  const dom = new JSDOM('<main></main>'); Object.assign(globalThis, { document: dom.window.document }); return { host: document.querySelector('main')!, dom };
}
function click(host: HTMLElement, label: string): void { const button = [...host.querySelectorAll('button')].find(b => b.getAttribute('aria-label') === label || b.textContent === label); assert.ok(button, label); button.click(); }
function record(id: string, created: string): ResearchRecord { return { research_id: id, experiment_id: 'experiment', attempt_id: 'attempt', title: id, question: 'What changed?', hypothesis: 'A change occurred.', plan: 'Compare retained evidence.', agent_id: 'fixture', agent_version: '1', agent_definition_digest: 'a'.repeat(64), model: 'fixture', page_plugin: 'run-summary', created_at: created, updated_at: created, status: 'FINISHED', max_runs: 1, max_seconds: 30, output: '<script>inert result</script>', metrics: { result: 2 }, trace_id: 'trace', error: null }; }

test('workspace keeps six peer bases, supplied inventory and existing definitions', async () => {
  const { host, dom } = setup(); const requests: string[] = [];
  const state: SemanticState = { mode: 'Lineage', graph, query: 'retained search', help: { query: '', source: 'snapshot' } };
  const dispose = mountSemantic(host, state, async request => { requests.push(request.operation); return { node: graph.nodes[0], definitions: [], definitions_status: 'disabled', unresolved: [] }; });
  assert.deepEqual([...host.querySelectorAll('.semantic-base')].map(b => b.getAttribute('aria-label')), ['Lineage', 'Zendesk', 'Definitions', 'Repositories', 'Research', 'PL-App Behavior']);
  assert.equal(host.querySelector('.semantic-base[aria-label="Pages"]'), null);
  assert.equal(host.querySelector<HTMLElement>('.semantic-main')!.hidden, true); assert.equal(host.querySelector('.semantic-sidebar'), null); assert.equal(host.querySelector('.semantic-layout'), null); assert.deepEqual(requests, []);
  click(host, 'Lineage');
  assert.deepEqual([...host.querySelectorAll('.semantic-catalog th')].map(n => n.textContent), ['Name','Kind','System / scope']);
  assert.equal(host.querySelector('.lineage-grid')?.lastElementChild, host.querySelector('.lineage-detail'));
  click(host, 'All knowledge bases'); click(host, 'Repositories'); assert.match(host.textContent!, /declared-repository/); assert.match(host.textContent!, /OPTIONAL \/ OFF \/ NOT CONFIGURED/); assert.deepEqual(requests, []);
  click(host, 'All knowledge bases'); click(host, 'Definitions'); assert.match(host.textContent!, /Return divided by capital/); (host.querySelector('.semantic-source-row') as HTMLButtonElement).click(); await settle(); assert.equal(state.mode, 'Lineage'); assert.match(host.querySelector('.lineage-detail')!.textContent!, /SME definition/); assert.ok(host.querySelector('[aria-label="sme editing"]')); assert.equal(state.query, 'retained search');
  dispose(); assert.ok(!host.classList.contains('semantic-workspace')); dom.window.close();
});

test('research lists only completed records newest first and opens the exact source ID', async () => {
  const { host, dom } = setup(); const old = record('old-record', '2026-11-10T12:00:00Z'); const recent = record('new-record', '2026-11-19T12:00:00Z'); const failed = {...recent, research_id:'failed',status:'FAILED' as const}; const requests: unknown[] = []; const opened: string[] = [];
  const dispose = mountSemanticArchive(host, async request => { requests.push(request); return { research: [old, failed, recent] }; }, id => opened.push(id)); await settle();
  assert.deepEqual(requests, [{ operation: 'research.list', order: 'newest' }]);
  assert.deepEqual([...host.querySelectorAll('.semantic-source-row h3')].map(n=>n.textContent), ['new-record','old-record']);
  (host.querySelector('.semantic-source-row') as HTMLButtonElement).click(); assert.deepEqual(opened,['new-record']); assert.equal(requests.length,1);
  const detached=host.querySelector('.semantic-source-row') as HTMLButtonElement; dispose();detached.click();assert.deepEqual(opened,['new-record']);dom.window.close();
});

test('archive errors and disposed reads do not substitute records or update detached sections', async () => {
  const { host, dom } = setup(); const dispose = mountSemanticArchive(host, async () => { throw new Error('offline'); }); await settle(); assert.match(host.textContent!, /Research unavailable/); assert.equal(host.querySelector('.semantic-source-row'), null); dispose();
  host.replaceChildren(); let resolve: (value: unknown) => void = () => {};
  const stop = mountSemanticArchive(host, () => new Promise(done => { resolve = done; })); const text = host.textContent; stop(); resolve({ research: [record('late', '2026-11-19T12:00:00Z')] }); await settle(); assert.equal(host.textContent, text); dom.window.close();
});

test('disposed lineage reads cannot restore Semantic classes or render late node evidence', async () => {
  const { host, dom } = setup(); let resolve: (value: unknown) => void = () => {};
  const state: SemanticState = { mode: 'Lineage', open: true, graph, query: '', help: { query: '', source: 'snapshot' } };
  const stop = mountSemantic(host, state, () => new Promise(done => { resolve = done; }));
  (host.querySelector('.lineage-row') as HTMLButtonElement).click(); stop();
  host.replaceChildren(document.createTextNode('Existing editorial Research'));
  resolve({node:graph.nodes[0],definitions:[],definitions_status:'disabled',unresolved:['Late evidence']});await settle();
  assert.equal(host.textContent,'Existing editorial Research'); assert.equal(host.classList.contains('semantic-workspace'),false);assert.equal(host.classList.contains('semantic-graph-mode'),false);dom.window.close();
});

test('default editorial index is read-free; open and back retain exact lineage and source state', async () => {
  const {host,dom}=setup(); const requests:unknown[]=[];
  const state:SemanticState={mode:'Lineage',query:'margin',selected:graph.nodes[0]!.id,help:{query:'retained article query',source:'public'},gherkin:{query:'retained scenario'}};
  const dispose=mountSemantic(host,state,async request=>{requests.push(request);return graph;});
  assert.equal(host.querySelectorAll('.semantic-base').length,6);assert.equal(host.querySelector('.semantic-sidebar,.semantic-layout'),null);assert.deepEqual(requests,[]);
  const row=host.querySelector<HTMLButtonElement>('.semantic-base')!;assert.equal(row.tagName,'BUTTON');assert.match(row.textContent!,/Open knowledge base/);row.click();await settle();
  assert.deepEqual(requests,[{operation:'lineage.graph'}]);click(host,'Graph');assert.ok(host.querySelector('svg'));
  click(host,'All knowledge bases');assert.equal(state.open,false);assert.equal(document.activeElement,row);click(host,'Lineage');
  assert.equal(requests.length,1);assert.equal(state.query,'margin');assert.equal(state.lineageView,'Graph');assert.deepEqual(state.selected,graph.nodes[0]!.id);assert.equal(state.help.query,'retained article query');assert.equal(state.gherkin!.query,'retained scenario');assert.ok(host.querySelector('svg'));
  dispose();dom.window.close();
});

test('back invalidates pending source reads and cached definitions do not fetch on reopen', async()=>{
  const {host,dom}=setup();let resolve:(value:unknown)=>void=()=>{};const state:SemanticState={mode:'Lineage',query:'',help:{query:'',source:'snapshot'}};
  const dispose=mountSemantic(host,state,()=>new Promise(done=>{resolve=done;}));click(host,'Lineage');click(host,'All knowledge bases');resolve(graph);await settle();
  assert.equal(state.graph,undefined);assert.equal(host.querySelector('.lineage-grid'),null);assert.equal(host.querySelector<HTMLElement>('.semantic-main')!.hidden,true);
  dispose();host.replaceChildren();const cached:SemanticState={...state,graph};let reads=0;const stop=mountSemantic(host,cached,async()=>{reads++;});click(host,'Definitions');assert.match(host.textContent!,/Return divided by capital/);click(host,'All knowledge bases');click(host,'Definitions');assert.equal(reads,0);stop();dom.window.close();
});

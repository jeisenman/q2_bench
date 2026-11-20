import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import { mountGherkin } from '../src/gherkin-view.js';
import { mountSemantic, type SemanticState } from '../src/semantic-view.js';
const commit = 'a'.repeat(40);
const listing = { repository: 'fixture', commit, features: [{ title: 'Literal', path: 'specs/literal.feature' }], count: 1, offset: 0, has_more: false };
const settle = (): Promise<void> => new Promise(resolve => setImmediate(resolve));
function setup(): { host: HTMLElement; dom: JSDOM } { const dom = new JSDOM('<main></main>'); Object.assign(globalThis, { document: dom.window.document }); return { host: document.querySelector('main')!, dom }; }
test('Gherkin is an isolated sixth base with exact source reads and inert verbatim detail', async () => {
  const { host, dom } = setup(); const requests: unknown[] = [];
  const state: SemanticState = { mode: 'PL-App Behavior', open: true, query: 'lineage search', help: { query: 'article search', source: 'snapshot' } };
  const dispose = mountSemantic(host, state, async request => { requests.push(request); return request.operation === 'gherkin.feature' ? { ...listing.features[0], repository: 'fixture', commit, text: '@tag\nBackground:\n<script>inert</script>\nScenario Outline:\nExamples:' } : listing; });
  await settle(); assert.deepEqual(requests, [{ operation: 'gherkin.list', offset: 0 }]);
  const mode = host.querySelector<HTMLSelectElement>('[aria-label="Gherkin search mode"]')!;
  assert.equal(mode.value, 'keyword'); assert.equal(mode.querySelector<HTMLOptionElement>('option[value="vector"]')!.disabled, true);
  assert.match(host.textContent!, /No embedding model or vector index is configured/);
  assert.equal(host.querySelector<HTMLElement>('.semantic-bases')!.hidden, true); assert.equal(host.querySelector('.semantic-sidebar'), null);
  assert.equal(host.querySelector('.semantic-view-heading h2')?.textContent, 'PL-App Behavior');
  assert.equal(host.querySelector('.gherkin-workspace h2'), null);
  assert.match(host.querySelector('.gherkin-detail')!.textContent!, /Select a specification/);
  assert.doesNotMatch(host.textContent!, /runtime_duration_seconds|trace[_ -]?id|experiment[_ -]?run[_ -]?id/i);
  (host.querySelector('.semantic-source-row') as HTMLButtonElement).click(); await settle(); assert.deepEqual(requests[1], { operation: 'gherkin.feature', path: 'specs/literal.feature', commit });
  assert.equal(host.querySelector('.gherkin-feature-row')?.getAttribute('aria-pressed'), 'true');
  assert.match(host.textContent!, /specs\/literal.feature/); assert.match(host.textContent!, new RegExp(commit)); assert.match(host.querySelector('pre')!.textContent!, /<script>inert<\/script>/); assert.equal(host.querySelector('script'), null);
  assert.match(host.querySelector('.gherkin-detail')!.textContent!, /Original Gherkin/);
  const search = host.querySelector<HTMLInputElement>('[aria-label="Search Gherkin specifications"]')!; search.value = 'Examples'; host.querySelector('form')!.dispatchEvent(new dom.window.Event('submit', { cancelable: true })); await settle();
  assert.deepEqual(requests[2], { operation: 'gherkin.search', query: 'Examples', offset: 0 }); assert.equal(state.query, 'lineage search'); assert.equal(state.help.query, 'article search'); assert.equal(state.gherkin?.query, 'Examples');
  assert.equal(host.querySelector('.gherkin-feature-row')?.getAttribute('aria-pressed'), 'false');
  assert.match(host.querySelector('.gherkin-detail')!.textContent!, /Select a specification/);
  const old = host.querySelector('.semantic-source-row') as HTMLButtonElement; dispose(); old.click(); assert.equal(requests.length, 3); dom.window.close();
});
test('unavailable and mismatched feature source never substitute content', async () => {
  const { host, dom } = setup(); const stop = mountGherkin(host, { query: '' }, async () => { throw new Error('missing'); }); await settle(); assert.match(host.textContent!, /Gherkin unavailable/); stop(); host.replaceChildren();
  const dispose = mountGherkin(host, { query: '' }, async request => request.operation === 'gherkin.feature' ? { ...listing.features[0], repository: 'fixture', commit: 'b'.repeat(40), text: 'Wrong revision' } : listing);
  await settle(); (host.querySelector('.semantic-source-row') as HTMLButtonElement).click(); await settle(); assert.match(host.textContent!, /exact requested commit/); assert.equal(host.querySelector('pre'), null); dispose(); dom.window.close();
});
test('disposal invalidates pending list and detail reads', async () => {
  const { host, dom } = setup(); let resolve: (value: unknown) => void = () => {};
  const stop = mountGherkin(host, { query: '' }, () => new Promise(done => { resolve = done; })); const before = host.textContent; stop(); resolve(listing); await settle(); assert.equal(host.textContent, before);
  host.replaceChildren(); const dispose = mountGherkin(host, { query: '' }, async request => request.operation === 'gherkin.feature' ? new Promise(done => { resolve = done; }) : listing); await settle();
  (host.querySelector('.semantic-source-row') as HTMLButtonElement).click(); dispose(); const pending = host.textContent; resolve({ ...listing.features[0], repository: 'fixture', commit, text: 'Late source' }); await settle(); assert.equal(host.textContent, pending); dom.window.close();
});

test('selection opens adjacent detail with loading state and narrow reveal; pagination stays in list', async () => {
  const { host, dom } = setup(); let resolve: (value: unknown) => void = () => {}; let reveals = 0;
  Object.defineProperty(dom.window, 'matchMedia', { value: () => ({ matches: true }) });
  dom.window.HTMLElement.prototype.scrollIntoView = () => { reveals++; };
  const dispose = mountGherkin(host, { query: '' }, async request => request.operation === 'gherkin.feature' ? new Promise(done => { resolve = done; }) : listing);
  await settle(); const row = host.querySelector<HTMLButtonElement>('.gherkin-feature-row')!; const detail = host.querySelector<HTMLElement>('.gherkin-detail')!;
  assert.equal(detail.parentElement, host.querySelector('.gherkin-browser'));
  assert.equal(host.querySelector('.gherkin-list-panel')?.lastElementChild?.className, 'toolbar');
  assert.equal(row.getAttribute('aria-controls'), detail.id);
  row.click(); assert.equal(detail.getAttribute('aria-busy'), 'true'); assert.equal(document.activeElement, detail); assert.equal(reveals, 1);
  assert.match(detail.querySelector('[role="status"]')!.textContent!, /Reading exact/);
  const text = 'Feature: Purpose\n  As a lender\n  Background: Setup\n  Scenario: Case\n    Given a source\n    When selected\n    Then visible\n';
  resolve({ ...listing.features[0], repository: 'fixture', commit, text }); await settle();
  assert.equal(detail.getAttribute('aria-busy'), 'false'); assert.equal(detail.querySelector('pre')!.textContent, text);
  dispose(); dom.window.close();
});

test('rapid selections retain only the newest exact source and its loading state', async () => {
  const { host, dom } = setup(); const pending = new Map<string, (value: unknown) => void>();
  const features = [{title:'First',path:'first.feature'},{title:'Second',path:'second.feature'}];
  const dispose = mountGherkin(host, { query: '' }, async request => request.operation === 'gherkin.feature' ? new Promise(done => { pending.set(request.path, done); }) : {...listing,features,count:2});
  await settle(); const rows = host.querySelectorAll<HTMLButtonElement>('.gherkin-feature-row'); rows[0]!.click(); rows[1]!.click();
  pending.get('second.feature')!({...features[1],repository:'fixture',commit,text:'Feature: Second\n'}); await settle();
  pending.get('first.feature')!({...features[0],repository:'fixture',commit,text:'Feature: Stale first\n'}); await settle();
  assert.equal(host.querySelector('pre')!.textContent,'Feature: Second\n');
  assert.equal(host.querySelector('.gherkin-detail')!.getAttribute('aria-busy'),'false');
  assert.equal(rows[0]!.getAttribute('aria-pressed'),'false'); assert.equal(rows[1]!.getAttribute('aria-pressed'),'true');
  dispose(); dom.window.close();
});

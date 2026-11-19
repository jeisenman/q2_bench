import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import type { Explanation, LineageNode } from '../src/lineage-contracts.js';
import { lineageDetail } from '../src/lineage-detail.js';
import { lineageTitle } from '../src/lineage-label.js';
import { nodeKey } from '../src/lineage-contracts.js';

const node: LineageNode = {
  id: { namespace: 'q2://internal/clientdata', name: 'derived/client_opportunity_products' },
  dataset: { keys: ['client_id'], partition: 'as_of_date' },
  facets: { meaning: {
    sme: { text: 'Products that belong to a client opportunity.', commit: 'abc123commit' },
    machine: {
      description: 'select client_id from raw_table',
      business_context: 'A client can compare products.\n<img src=x onerror=alert(1)>',
      producer: 'generator_v1', generation_id: 'generation_123', evidence_sha256: 'sha256secret',
    },
  }, location: { uri: 'abfss://raw/private/path', verified: false } },
  sources: [{ repository: 'internal-repository', path: 'src/raw/client.py', commit: 'abc123commit' }],
};

test('header Edit highlights only the inline SME definition and Cancel restores its reading view', async () => {
  const dom = new JSDOM('<main></main>', { url: 'http://127.0.0.1:4175' });
  Object.assign(globalThis, { document: dom.window.document, window: dom.window });
  let writes = 0;
  window.semantic = {
    read: async () => ({ kind: 'sme', id: nodeKey(node.id), version: 0, content: { text: '', source_commit: null }, updated_at: null }),
    saveDocument: async () => { writes++; throw Error('Not expected'); },
    saveProposal: async () => { throw Error('Not expected'); },
  };
  const host = document.querySelector('main')!; const stop = lineageDetail(host, node);
  const header = host.querySelector('.sme-detail-heading')!;
  const edit = [...header.querySelectorAll('button')].find(b => b.textContent === 'Edit')!;
  const target = host.querySelector('.sme-definition')!;
  assert.ok(edit); assert.equal(target.querySelector('button'), null);
  edit.click(); await new Promise(resolve => setImmediate(resolve));
  assert.ok(target.classList.contains('document-editing'));
  const field = target.querySelector('textarea')!;
  assert.equal(field.value, node.facets.meaning.sme!.text);
  assert.equal(field.getAttribute('aria-label'), 'SME definition');
  assert.equal(document.activeElement, field);
  assert.equal(target.textContent!.includes('Generated business context'), false);
  assert.equal(host.querySelectorAll('textarea').length, 1);
  [...target.querySelectorAll('button')].find(b => b.textContent === 'Cancel')!.click();
  assert.equal(target.classList.contains('document-editing'), false);
  assert.equal(target.querySelector('textarea'), null); assert.equal(document.activeElement, edit);
  assert.equal(writes, 0); assert.equal(edit.getAttribute('aria-expanded'), 'false');
  stop(); assert.equal(header.querySelector('button'), null); dom.window.close();
});
function render(value: LineageNode, explanation?: Explanation) {
  const dom = new JSDOM('<main></main>');
  Object.assign(globalThis, { document: dom.window.document });
  const host = document.querySelector('main')!;
  lineageDetail(host, value, explanation);
  const visible = host.cloneNode(true) as HTMLElement;
  visible.querySelectorAll('details').forEach(detail => detail.remove());
  return { dom, host, visible };
}

test('reading view shows supplied meaning and keeps technical evidence closed and intact', () => {
  const before = JSON.stringify(node);
  const { dom, host, visible } = render(node);
  assert.equal(host.querySelector('h2')!.textContent, 'Client opportunity products');
  assert.ok(visible.textContent!.includes(node.facets.meaning.machine!.business_context));
  assert.ok(visible.textContent!.includes(node.facets.meaning.sme!.text));
  for (const raw of ['q2://', 'abc123commit', 'select client_id', 'raw_table', 'sha256secret', 'src/raw', 'client_opportunity_products', 'as_of_date']) {
    assert.ok(!visible.textContent!.includes(raw), `Reading view must hide ${raw}`);
    assert.ok(host.querySelector('details')!.textContent!.includes(raw), `Evidence must retain ${raw}`);
  }
  assert.equal(host.querySelector('details')!.open, false);
  assert.equal(host.querySelector('summary')!.textContent, 'Technical evidence');
  assert.equal(host.querySelector('img'), null);
  assert.equal(JSON.stringify(node), before);
  dom.window.close();
});

test('missing and blank meaning remains explicit without promoting machine descriptions', () => {
  const { dom, visible } = render({ ...node, facets: { meaning: {} } });
  assert.match(visible.textContent!, /No SME definition is available/);
  assert.match(visible.textContent!, /No generated business context is available/);
  assert.match(visible.textContent!, /Freshness and unresolved findings have not been checked/);
  dom.window.close();
  const blank = { ...node, facets: { meaning: { machine: { ...node.facets.meaning.machine!, business_context: ' \n ' } } } };
  const rendered = render(blank);
  assert.match(rendered.visible.textContent!, /No generated business context is available/);
  assert.ok(!rendered.visible.textContent!.includes('select client_id'));
  rendered.dom.window.close();
});

test('freshness and unresolved messages are concise with raw reasons retained in evidence', () => {
  const explanation: Explanation = {
    node, definitions_status: 'available',
    definitions: [{ pinned_id: node.id, current_id: node.id, stale: true, reasons: ['commit_mismatch: abc123commit'] }],
    unresolved: ['raw_table / missing_column'],
    job_flow: { inputs: [], outputs: [], transformations: [], unresolved: ['raw_table / missing_column'] },
  };
  const { dom, host, visible } = render(node, explanation);
  assert.match(visible.textContent!, /A definition is out of date/);
  assert.match(visible.textContent!, /1 unresolved finding\./);
  assert.ok(!visible.textContent!.includes('commit_mismatch'));
  assert.ok(host.querySelector('details')!.textContent!.includes('commit_mismatch'));
  dom.window.close();
  for (const [status, definitions, message] of [
    ['disabled', [], 'Definition freshness checks are unavailable.'],
    ['available', [], 'No definition freshness results were supplied.'],
    ['available', [{ ...explanation.definitions[0]!, stale: false }], 'Definitions match their pinned sources.'],
  ] as const) {
    const rendered = render(node, { node, definitions_status: status, definitions: [...definitions], unresolved: [] });
    assert.ok(rendered.visible.textContent!.includes(message));
    assert.match(rendered.visible.textContent!, /No unresolved findings were reported/);
    rendered.dom.window.close();
  }
});

test('reading titles retain identity separately and format columns and plain names', () => {
  assert.equal(lineageTitle({ namespace: 'internal', name: 'folder/daily_totals', column: 'net_amount' }), 'Daily totals · Net amount');
  assert.equal(lineageTitle({ namespace: 'internal', name: 'GDP totals' }), 'GDP totals');
});

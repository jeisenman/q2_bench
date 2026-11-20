import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { readGherkin } from '../src/gherkin-source.js';
import { GherkinListSchema, GherkinFeatureSchema, GherkinRequestSchema, GHERKIN_CAPABILITIES, gherkinPath, gherkinRequestFromPath } from '../src/gherkin-contracts.js';
import { ReadSchema, validateResponse } from '../src/api.js';
const literal = '@tag\nFeature: Literal source\n  Background:\n    Given <script>inert</script>\n  Scenario Outline: values\n    Then value <amount>\n    Examples:\n      | amount |\n      | 1 |\n';
async function fixture(run: (root: string, git: (...args: string[]) => string) => Promise<void>): Promise<void> {
  const root = await mkdtemp(path.join(tmpdir(), 'gherkin-'));
  const git = (...args: string[]): string => execFileSync('git', ['-C', root, ...args], { encoding: 'utf8', env: { ...process.env, GIT_CONFIG_GLOBAL: '/dev/null', GIT_CONFIG_NOSYSTEM: '1' } }).trim();
  try { git('init', '-q'); git('config', 'user.name', 'Test'); git('config', 'user.email', 'test@example.invalid'); await mkdir(path.join(root, 'specs')); await writeFile(path.join(root, 'specs', 'literal.feature'), literal); git('add', '.'); git('commit', '-qm', 'source'); await run(root, git); }
  finally { await rm(root, { recursive: true, force: true }); }
}
test('source lists and searches tracked features, retains tags/outlines, and pins detail across HEAD changes', async () => {
  await fixture(async (root, git) => {
    await writeFile(path.join(root, 'untracked.feature'), 'Feature: untracked');
    const listing = GherkinListSchema.parse(await readGherkin({ operation: 'gherkin.list', offset: 0 }, root));
    assert.deepEqual(listing.features, [{ path: 'specs/literal.feature', title: 'literal' }]); assert.equal(listing.count, 1);
    const matches = GherkinListSchema.parse(await readGherkin({ operation: 'gherkin.search', offset: 0, query: 'SCENARIO OUTLINE' }, root)); assert.equal(matches.count, 1);
    const none = GherkinListSchema.parse(await readGherkin({ operation: 'gherkin.search', offset: 0, query: 'missing phrase' }, root)); assert.equal(none.count, 0);
    await writeFile(path.join(root, 'specs/literal.feature'), 'Feature: changed\n'); git('add', 'specs'); git('commit', '-qm', 'changed');
    const detail = GherkinFeatureSchema.parse(await readGherkin({ operation: 'gherkin.feature', commit: listing.commit, path: listing.features[0]!.path }, root)); assert.equal(detail.text, literal); assert.equal(detail.commit, listing.commit);
    const current = GherkinListSchema.parse(await readGherkin({ operation: 'gherkin.search', offset: 0, commit: listing.commit, query: 'Examples:' }, root)); assert.equal(current.count, 1); assert.equal(current.commit, listing.commit);
  });
});
test('pagination is bounded and source failures stay explicit', async () => {
  await fixture(async (root, git) => {
    for (let i = 0; i < 27; i++) await writeFile(path.join(root, `item-${i}.feature`), `Feature: ${i}\n`);
    git('add', '.'); git('commit', '-qm', 'many');
    const first = GherkinListSchema.parse(await readGherkin({ operation: 'gherkin.list', offset: 0 }, root)); assert.equal(first.features.length, 25); assert.equal(first.count, 28); assert.equal(first.has_more, true);
    const second = GherkinListSchema.parse(await readGherkin({ operation: 'gherkin.list', offset: 25, commit: first.commit }, root)); assert.equal(second.features.length, 3); assert.equal(second.has_more, false);
    await assert.rejects(readGherkin({ operation: 'gherkin.feature', commit: first.commit, path: 'absent.feature' }, root), /not tracked/);
    await writeFile(path.join(root, 'large.feature'), 'x'.repeat(1_000_001)); git('add', '.'); git('commit', '-qm', 'large');
    const commit = git('rev-parse', 'HEAD'); await assert.rejects(readGherkin({ operation: 'gherkin.feature', commit, path: 'large.feature' }, root), /size or time limit/);
    await assert.rejects(readGherkin({ operation: 'gherkin.list', offset: 0 }, path.join(root, 'missing')), /Gherkin unavailable/);
    await assert.rejects(readGherkin({ operation: 'gherkin.list', offset: 0 }, 'relative'), /absolute checkout/);
    await assert.rejects(readGherkin({ operation: 'gherkin.list', offset: 0, commit: '0'.repeat(40) }, root), /Gherkin unavailable/);
  });
});
test('finite contracts reject traversal, unpinned detail, renderer roots, origins and extra preview parameters', () => {
  const commit = 'a'.repeat(40);
  for (const featurePath of ['../x.feature', '/x.feature', 'a/../x.feature', 'a\\x.feature', 'a\nx.feature', 'x.txt']) assert.equal(GherkinRequestSchema.safeParse({ operation: 'gherkin.feature', commit, path: featurePath }).success, false);
  for (const extra of [{ root: '/tmp' }, { origin: 'https://example.invalid' }]) assert.equal(ReadSchema.safeParse({ operation: 'gherkin.list', offset: 0, ...extra }).success, false);
  assert.equal(GherkinRequestSchema.safeParse({ operation: 'gherkin.feature', path: 'x.feature' }).success, false);
  assert.equal(GherkinRequestSchema.safeParse({ operation: 'gherkin.list', offset: 10001 }).success, false);
  const request = { operation: 'gherkin.search', offset: 25, commit, query: 'a & b' } as const; assert.deepEqual(gherkinRequestFromPath(gherkinPath(request)), request);
  for (const raw of ['/features?offset=0&root=/tmp', '/features?offset=0&offset=1', 'https://example.invalid/features?offset=0', '/wrong?offset=0', '/features?offset=-1']) assert.throws(() => gherkinRequestFromPath(raw));
  assert.throws(() => validateResponse('gherkin.list', { features: [] }));
});

test('capabilities need no source and vector requests fail before any source access', async () => {
  assert.deepEqual(await readGherkin({ operation: 'gherkin.capabilities' }, 'relative-invalid-source'), GHERKIN_CAPABILITIES);
  assert.deepEqual(validateResponse('gherkin.capabilities', GHERKIN_CAPABILITIES), GHERKIN_CAPABILITIES);
  await assert.rejects(readGherkin({ operation: 'gherkin.search', query: 'rate lock', offset: 0, mode: 'vector' }, 'relative-invalid-source'), /^Error: Vector search is disabled\.$/);
  for (const mode of ['keyword', 'vector'] as const) {
    const request = { operation: 'gherkin.search', query: 'rate lock', offset: 0, mode } as const;
    assert.deepEqual(gherkinRequestFromPath(gherkinPath(request)), request);
  }
  assert.deepEqual(gherkinRequestFromPath('/capabilities'), { operation: 'gherkin.capabilities' });
  for (const invalid of ['/capabilities?root=/tmp', '/features?offset=0&query=rate&mode=hybrid', '/features?offset=0&mode=vector']) assert.throws(() => gherkinRequestFromPath(invalid));
});

test('Gherkin output contracts reject internal research metadata', () => {
  const feature = { repository: 'fixture', commit: 'a'.repeat(40), path: 'specs/example.feature', title: 'Example', text: 'Feature: Example' };
  const listing = { repository: 'fixture', commit: feature.commit, features: [{ path: feature.path, title: feature.title }], count: 1, offset: 0, has_more: false };
  for (const key of ['research_id', 'experiment_id', 'attempt_id', 'agent_definition_digest', 'trace_id', 'metrics', 'runtime_duration_seconds']) {
    assert.equal(GherkinFeatureSchema.safeParse({ ...feature, [key]: 'internal' }).success, false);
    assert.equal(GherkinListSchema.safeParse({ ...listing, [key]: 'internal' }).success, false);
  }
});

import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { readKnowledgeSnapshot } from '../src/knowledge-snapshot.js';
import { HelpArticleSchema, HelpListSchema } from '../src/help-contracts.js';

function article(id = 1) {
  return { articleId: id, title: `Article ${id}`, url: `https://support.precisionlender.com/hc/en-us/articles/${id}-Article`,
    locale: 'en-us', updatedAt: '2026-09-02T10:00:00Z', createdAt: '2020-01-01T00:00:00Z',
    bodyHtml: '<p>Loan &amp; pricing</p><script>stolen()</script><iframe src="https://evil.test">hidden</iframe>', sections: [] };
}
function manifest(size = 1) {
  return { status: 'success', run_id: 'test-corpus', completed_at: '2026-09-02T21:01:37.590Z',
    config: { site_hosts: ['https://support.precisionlender.com'], locales: ['en-us'] },
    counts: { normalized_articles: size, sections: 0, chunks: size * 2 } };
}
async function fixture(t: test.TestContext, articles = [article()]) {
  const root = await mkdtemp(join(tmpdir(), 'semantic-snapshot-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  await writeFile(join(root, 'manifest.json'), JSON.stringify(manifest(articles.length)));
  await writeFile(join(root, 'articles-normalized.json'), JSON.stringify({ counts: { articles: articles.length, sections: 0 }, articles }));
  return root;
}

test('snapshot lists 25 newest records with deterministic ties and provenance', async t => {
  const root = await fixture(t, Array.from({ length: 26 }, (_, i) => article(26 - i)));
  const value = HelpListSchema.parse(await readKnowledgeSnapshot({ operation: 'knowledge.list' }, root));
  assert.equal(value.count, 26);
  assert.equal(value.has_more, true);
  assert.equal(value.articles.length, 25);
  assert.equal(value.articles[0]?.id, 1);
  assert.equal(value.snapshot?.article_count, 26);
  assert.equal(value.snapshot?.chunk_count, 52);
});

test('snapshot searches titles and inert body text and returns exact detail', async t => {
  const root = await fixture(t, [article(2), { ...article(1), updatedAt: '2026-09-03T00:00:00Z' }]);
  const list = HelpListSchema.parse(await readKnowledgeSnapshot({ operation: 'knowledge.search', query: 'PRICING' }, root));
  assert.deepEqual(list.articles.map(item => item.id), [1, 2]);
  const title = HelpListSchema.parse(await readKnowledgeSnapshot({ operation: 'knowledge.search', query: 'Article 2' }, root));
  assert.equal(title.count, 1);
  const detail = HelpArticleSchema.parse(await readKnowledgeSnapshot({ operation: 'knowledge.article', id: 2 }, root));
  assert.equal(detail.text, 'Loan & pricing');
  assert.equal(detail.snapshot?.run_id, 'test-corpus');
  const hidden = HelpListSchema.parse(await readKnowledgeSnapshot({ operation: 'knowledge.search', query: 'stolen' }, root));
  assert.equal(hidden.count, 0);
  await assert.rejects(readKnowledgeSnapshot({ operation: 'knowledge.article', id: 3 }, root), /not found/);
});

test('snapshot rejects absent files, failed manifests and mismatched counts', async t => {
  const root = await fixture(t);
  await rm(join(root, 'manifest.json'));
  await assert.rejects(readKnowledgeSnapshot({ operation: 'knowledge.list' }, root), /ENOENT/);
  await writeFile(join(root, 'manifest.json'), JSON.stringify({ ...manifest(), status: 'failed' }));
  await assert.rejects(readKnowledgeSnapshot({ operation: 'knowledge.list' }, root));
  await writeFile(join(root, 'manifest.json'), JSON.stringify(manifest(2)));
  await assert.rejects(readKnowledgeSnapshot({ operation: 'knowledge.list' }, root), /counts do not match/);
});

test('snapshot rejects duplicate IDs, unsafe URLs and non-UTC dates', async t => {
  const duplicate = await fixture(t, [article(), article()]);
  await assert.rejects(readKnowledgeSnapshot({ operation: 'knowledge.list' }, duplicate), /duplicate/);
  for (const changed of [
    { url: 'https://evil.test/hc/en-us/articles/1' },
    { url: 'https://support.precisionlender.com/hc/en-us/articles/2-Other' },
    { updatedAt: '2026-09-02T10:00:00+01:00' },
  ]) {
    const root = await fixture(t, [{ ...article(), ...changed }]);
    await assert.rejects(readKnowledgeSnapshot({ operation: 'knowledge.list' }, root));
  }
});

test('snapshot bounds files and prevents subfile links escaping trusted root', async t => {
  const root = await fixture(t);
  await writeFile(join(root, 'manifest.json'), ' '.repeat(64_001));
  await assert.rejects(readKnowledgeSnapshot({ operation: 'knowledge.list' }, root), /file limit/);
  await writeFile(join(root, 'manifest.json'), JSON.stringify(manifest()));
  await writeFile(join(root, 'articles-normalized.json'), ' '.repeat(16_000_001));
  await assert.rejects(readKnowledgeSnapshot({ operation: 'knowledge.list' }, root), /file limit/);
  const outside = await fixture(t);
  await rm(join(root, 'articles-normalized.json'));
  await symlink(join(outside, 'articles-normalized.json'), join(root, 'articles-normalized.json'));
  await assert.rejects(readKnowledgeSnapshot({ operation: 'knowledge.list' }, root), /escapes/);
});

test('snapshot rejects renderer root inputs and invalid requests', async t => {
  const root = await fixture(t);
  await assert.rejects(readKnowledgeSnapshot({ operation: 'knowledge.list', root: '/tmp' } as never, root));
  await assert.rejects(readKnowledgeSnapshot({ operation: 'knowledge.search', query: ' ' }, root));
  await assert.rejects(readKnowledgeSnapshot({ operation: 'knowledge.article', id: 0 }, root));
});

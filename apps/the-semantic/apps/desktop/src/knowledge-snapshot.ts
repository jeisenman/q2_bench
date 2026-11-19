import { constants } from 'node:fs';
import { open, realpath } from 'node:fs/promises';
import { dirname, isAbsolute, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { z } from 'zod';
import { articleText } from './help-client.js';
import { ArticleIDSchema, HelpArticleSchema, HelpListSchema, KnowledgeRequestSchema, type KnowledgeRequest } from './help-contracts.js';

const utcDate = z.iso.datetime();
const count = z.number().int().nonnegative().max(100_000);
const Manifest = z.object({
  status: z.literal('success'),
  run_id: z.string().min(1).max(200),
  completed_at: utcDate,
  config: z.object({
    site_hosts: z.array(z.literal('https://support.precisionlender.com')).min(1).max(1),
    locales: z.array(z.literal('en-us')).min(1).max(1),
  }),
  counts: z.object({ normalized_articles: count, sections: count, chunks: count }),
});
const RawArticle = z.object({
  articleId: ArticleIDSchema,
  title: z.string().min(1).max(1000),
  url: HelpArticleSchema.shape.url,
  locale: z.literal('en-us'),
  updatedAt: utcDate,
  createdAt: utcDate,
  bodyHtml: z.string().max(2_000_000).nullable(),
  sections: z.array(z.unknown()).max(100_000),
});
const Corpus = z.object({
  counts: z.object({ articles: count, sections: count }),
  articles: z.array(RawArticle).max(10_000),
});

function defaultRoot(): string {
  // Both src/ (tsx) and dist-electron/ (bundled main) have this project depth.
  const directory = typeof __dirname === 'string' ? __dirname : dirname(fileURLToPath(import.meta.url));
  return process.env.SEMANTIC_ZENDESK_SNAPSHOT ?? resolve(directory, '../../../var/zendesk-snapshot');
}

async function readBounded(root: string, filename: string, limit: number): Promise<unknown> {
  const path = await realpath(resolve(root, filename));
  const child = relative(root, path);
  if (!child || isAbsolute(child) || child === '..' || child.startsWith(`..${sep}`)) {
    throw new Error(`Snapshot ${filename} escapes the trusted directory.`);
  }
  const file = await open(path, constants.O_RDONLY | constants.O_NOFOLLOW);
  try {
    const stat = await file.stat();
    if (!stat.isFile() || stat.size > limit) throw new Error(`Snapshot ${filename} exceeds its file limit.`);
    const bytes = Buffer.alloc(limit + 1);
    let length = 0;
    while (length < bytes.length) {
      const { bytesRead } = await file.read(bytes, length, bytes.length - length, null);
      if (bytesRead === 0) break;
      length += bytesRead;
    }
    if (length > limit) throw new Error(`Snapshot ${filename} exceeds its file limit.`);
    return JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes.subarray(0, length)));
  } finally {
    await file.close();
  }
}

/** Reads bounded local Zendesk evidence. The optional root is a trusted host setting, never a renderer input. */
export async function readKnowledgeSnapshot(raw: KnowledgeRequest, root = defaultRoot()): Promise<unknown> {
  const request = KnowledgeRequestSchema.parse(raw);
  const trustedRoot = await realpath(root);
  const manifest = Manifest.parse(await readBounded(trustedRoot, 'manifest.json', 64_000));
  const corpus = Corpus.parse(await readBounded(trustedRoot, 'articles-normalized.json', 16_000_000));
  if (manifest.counts.normalized_articles !== corpus.counts.articles || corpus.counts.articles !== corpus.articles.length ||
      manifest.counts.sections !== corpus.counts.sections ||
      corpus.counts.sections !== corpus.articles.reduce((total, article) => total + article.sections.length, 0)) {
    throw new Error('Snapshot article or section counts do not match.');
  }
  const ids = new Set<number>();
  for (const article of corpus.articles) {
    if (ids.has(article.articleId)) throw new Error('Snapshot contains duplicate article IDs.');
    ids.add(article.articleId);
    const path = new URL(article.url).pathname;
    if (!path.startsWith(`/hc/en-us/articles/${article.articleId}-`) && path !== `/hc/en-us/articles/${article.articleId}`) {
      throw new Error('Snapshot article URL does not match its ID.');
    }
  }
  const snapshot = {
    run_id: manifest.run_id,
    completed_at: manifest.completed_at,
    article_count: manifest.counts.normalized_articles,
    chunk_count: manifest.counts.chunks,
  };
  const normalize = (article: z.infer<typeof RawArticle>) => HelpArticleSchema.parse({
    id: article.articleId, title: article.title, url: article.url, updated_at: article.updatedAt,
    locale: article.locale, text: article.bodyHtml === null ? null : articleText(article.bodyHtml),
  });
  if (request.operation === 'knowledge.article') {
    const article = corpus.articles.find(item => item.articleId === request.id);
    if (!article) throw new Error('Snapshot article was not found.');
    return HelpArticleSchema.parse({ ...normalize(article), snapshot });
  }
  const query = request.operation === 'knowledge.search' ? request.query.toLowerCase() : null;
  const articles = corpus.articles.map(normalize)
    .filter(article => query === null || `${article.title}\n${article.text ?? ''}`.toLowerCase().includes(query))
    .sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at) || a.id - b.id);
  return HelpListSchema.parse({ articles: articles.slice(0, 25), count: articles.length, has_more: articles.length > 25, snapshot });
}

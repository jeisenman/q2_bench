import { z } from 'zod';
export const ArticleIDSchema=z.number().int().positive().max(Number.MAX_SAFE_INTEGER);
export const HelpRequestSchema=z.discriminatedUnion('operation',[
  z.object({operation:z.literal('help.list')}).strict(),
  z.object({operation:z.literal('help.search'),query:z.string().trim().min(1).max(200)}).strict(),
  z.object({operation:z.literal('help.article'),id:ArticleIDSchema}).strict(),
]);
export const PublicArticleURLSchema=z.string().max(2048).refine(value=>{try{const u=new URL(value);return u.protocol==='https:'&&u.hostname==='support.precisionlender.com'&&!u.username&&!u.password&&!u.port&&u.pathname.startsWith('/hc/en-us/articles/');}catch{return false;}},'A public PrecisionLender article URL is required.');
export const SnapshotInfoSchema=z.object({run_id:z.string().min(1).max(256),completed_at:z.iso.datetime({offset:true}),article_count:z.number().int().nonnegative(),chunk_count:z.number().int().nonnegative()}).strict();
export const KnowledgeRequestSchema=z.discriminatedUnion('operation',[
  z.object({operation:z.literal('knowledge.list')}).strict(),
  z.object({operation:z.literal('knowledge.search'),query:z.string().trim().min(1).max(200)}).strict(),
  z.object({operation:z.literal('knowledge.article'),id:ArticleIDSchema}).strict(),
]);
export type KnowledgeRequest=z.infer<typeof KnowledgeRequestSchema>;
/** Plain-text public knowledge. It is not an approved lineage definition. */
export const HelpArticleSchema=z.object({id:ArticleIDSchema,title:z.string().min(1).max(1000),url:PublicArticleURLSchema,updated_at:z.iso.datetime({offset:true}),locale:z.literal('en-us'),text:z.string().max(1_000_000).nullable(),snapshot:SnapshotInfoSchema.optional()}).strict();
export const HelpListSchema=z.object({articles:z.array(HelpArticleSchema).max(25),count:z.number().int().nonnegative(),has_more:z.boolean(),snapshot:SnapshotInfoSchema.optional()}).strict();
export type HelpRequest=z.infer<typeof HelpRequestSchema>;
export type HelpArticle=z.infer<typeof HelpArticleSchema>;
/** Fixed public API paths only. The caller never supplies a host or URL. */
export function helpPath(raw:unknown):string {
  const r=HelpRequestSchema.parse(raw);
  if(r.operation==='help.article')return `/api/v2/help_center/en-us/articles/${r.id}.json`;
  if(r.operation==='help.search')return `/api/v2/help_center/articles/search.json?query=${encodeURIComponent(r.query)}&locale=en-us&per_page=25`;
  return '/api/v2/help_center/en-us/articles.json?per_page=25&sort_by=updated_at&sort_order=desc';
}
/** Decodes only canonical preview paths, never arbitrary upstream addresses. */
export function helpRequestFromPath(raw:string):HelpRequest {
  const u=new URL(raw,'http://127.0.0.1');
  const article=/^\/api\/v2\/help_center\/en-us\/articles\/(\d+)\.json$/.exec(u.pathname);
  let request:HelpRequest;
  if(article)request=HelpRequestSchema.parse({operation:'help.article',id:Number(article[1])});
  else if(u.pathname==='/api/v2/help_center/articles/search.json')request=HelpRequestSchema.parse({operation:'help.search',query:u.searchParams.get('query')});
  else request={operation:'help.list'};
  if(helpPath(request)!==raw)throw new Error('Unsupported public Help Center read.');
  return request;
}

/** Canonical same-origin preview paths for the configured snapshot, never a filesystem path. */
export function knowledgePath(raw:unknown):string {
  const r=KnowledgeRequestSchema.parse(raw);
  if(r.operation==='knowledge.article')return `/articles/${r.id}`;
  if(r.operation==='knowledge.search')return `/articles?query=${encodeURIComponent(r.query)}`;
  return '/articles';
}
export function knowledgeRequestFromPath(raw:string):KnowledgeRequest {
  const url=new URL(raw,'http://127.0.0.1');const article=/^\/articles\/(\d+)$/.exec(url.pathname);
  const request=KnowledgeRequestSchema.parse(article?{operation:'knowledge.article',id:Number(article[1])}:url.search?{operation:'knowledge.search',query:url.searchParams.get('query')}:{operation:'knowledge.list'});
  if(knowledgePath(request)!==raw)throw new Error('Unsupported knowledge snapshot read.');return request;
}

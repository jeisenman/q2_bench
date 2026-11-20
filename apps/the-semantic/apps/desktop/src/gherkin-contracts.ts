import { z } from 'zod';
const CommitSchema = z.string().regex(/^[0-9a-f]{40}$/);
const FeaturePathSchema = z.string().min(1).max(2048).refine(value => !value.startsWith('/') && !value.includes('\\') && !/[\x00-\x1f\x7f]/.test(value) && value.split('/').every(part => part !== '.' && part !== '..' && part !== '') && value.endsWith('.feature'), 'A tracked relative feature path is required.');
const PageSchema = { offset: z.number().int().min(0).max(10000), commit: CommitSchema.optional() };
/** Finite source reads accept no repository roots or renderer origins. */
export const GherkinRequestSchema = z.discriminatedUnion('operation', [
  z.object({ operation: z.literal('gherkin.capabilities') }).strict(),
  z.object({ operation: z.literal('gherkin.list'), ...PageSchema }).strict(),
  z.object({ operation: z.literal('gherkin.search'), query: z.string().trim().min(1).max(200).refine(value => !/[\x00-\x1f\x7f]/.test(value)), mode: z.enum(['keyword', 'vector']).optional(), ...PageSchema }).strict(),
  z.object({ operation: z.literal('gherkin.feature'), path: FeaturePathSchema, commit: CommitSchema }).strict(),
]);
/** Retrieval modes currently supported by the host, without provider setup. */
export const GHERKIN_CAPABILITIES = { keyword: { enabled: true }, vector: { enabled: false, reason: 'Vector search is disabled.' } } as const;
export const GherkinCapabilitiesSchema = z.object({ keyword: z.object({ enabled: z.literal(true) }).strict(), vector: z.object({ enabled: z.literal(false), reason: z.literal('Vector search is disabled.') }).strict() }).strict();
const SourceSchema = { repository: z.string().min(1).max(256), commit: CommitSchema };
const FeatureSummarySchema = z.object({ path: FeaturePathSchema, title: z.string().min(1).max(2048) }).strict();
export const GherkinListSchema = z.object({ ...SourceSchema, features: z.array(FeatureSummarySchema).max(25), count: z.number().int().min(0).max(10000), offset: z.number().int().min(0).max(10000), has_more: z.boolean() }).strict();
export const GherkinFeatureSchema = FeatureSummarySchema.extend({ ...SourceSchema, text: z.string().max(1_000_000) }).strict();
export type GherkinRequest = z.infer<typeof GherkinRequestSchema>;
export type GherkinList = z.infer<typeof GherkinListSchema>;
export type GherkinFeature = z.infer<typeof GherkinFeatureSchema>;
/** Encodes a finite preview route, retaining the exact source commit. */
export function gherkinPath(raw: unknown): string {
  const r = GherkinRequestSchema.parse(raw);
  if (r.operation === 'gherkin.capabilities') return '/capabilities';
  if (r.operation === 'gherkin.feature') return `/feature?commit=${r.commit}&path=${encodeURIComponent(r.path)}`;
  return `/features?offset=${r.offset}${r.commit ? `&commit=${r.commit}` : ''}${r.operation === 'gherkin.search' ? `&query=${encodeURIComponent(r.query)}${r.mode ? `&mode=${r.mode}` : ''}` : ''}`;
}
/** Rejects unknown, duplicate and noncanonical preview parameters. */
export function gherkinRequestFromPath(raw: string): GherkinRequest {
  const url = new URL(raw, 'http://127.0.0.1');
  const request = GherkinRequestSchema.parse(url.pathname === '/capabilities' ? { operation: 'gherkin.capabilities' } : url.pathname === '/feature'
    ? { operation: 'gherkin.feature', commit: url.searchParams.get('commit'), path: url.searchParams.get('path') }
    : { operation: url.searchParams.has('query') ? 'gherkin.search' : 'gherkin.list', offset: Number(url.searchParams.get('offset')), ...(url.searchParams.has('commit') ? { commit: url.searchParams.get('commit') } : {}), ...(url.searchParams.has('query') ? { query: url.searchParams.get('query') } : {}), ...(url.searchParams.has('mode') ? { mode: url.searchParams.get('mode') } : {}) });
  if (gherkinPath(request) !== raw) throw new Error('Unsupported Gherkin source read.');
  return request;
}

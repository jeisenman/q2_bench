import { z } from 'zod';
const text = z.string().max(128000);
const identity = z.string().min(1).max(4096).refine(s => s.trim() === s);
const list = <T extends z.ZodType>(schema: T, max = 150000) => z.array(schema).max(max).nullable().transform(v => v ?? []);
/** Logical identity; labels never replace source identities. */
export const NodeIDSchema = z.object({ namespace: identity, name: identity, column: z.string().max(4096).refine(s => s.trim() === s).optional() }).strict();
export const SourceSchema = z.object({ repository: text.optional(), path: text.optional(), commit: text.optional(), sha256: text.optional(), snapshot_id: text.optional() }).strict();
const MachineSchema = z.object({ description: text, business_context: text, generation_id: text, evidence_sha256: text, producer: text }).strict();
const TransformationSchema = z.object({ name: text, implementation: text, source: SourceSchema }).strict();
/** Full typed graph node returned by the independent Go serving boundary. */
export const LineageNodeSchema = z.object({
  id: NodeIDSchema,
  job: z.object({ dag: text.optional(), transformations: list(TransformationSchema,10000).optional() }).strict().optional(),
  dataset: z.object({ keys: list(text,10000).optional(), partition: text.optional() }).strict().optional(),
  column: z.object({ type: text, nullable: z.boolean() }).strict().optional(),
  facets: z.object({
    location: z.object({ uri: text, verified: z.boolean() }).strict().optional(),
    meaning: z.object({ sme: z.object({ text, commit: text }).strict().optional(), machine: MachineSchema.optional() }).strict(),
    formal: z.object({ method_id: text, profile: text, status: text, source: SourceSchema }).strict().optional(),
  }).strict(), sources: list(SourceSchema,10000).optional(),
}).strict().superRefine((node,ctx) => {
  if ([node.job,node.dataset,node.column].filter(Boolean).length !== 1) ctx.addIssue({code:'custom',message:'Exactly one node kind is required.'});
});
export const EdgeSchema = z.object({ source: NodeIDSchema, target: NodeIDSchema, kind: z.string().min(1).max(128) }).strict();
/** Complete scoped graph. Unresolved findings never establish complete coverage. */
export const LineageGraphSchema = z.object({
  nodes:list(LineageNodeSchema), edges:list(EdgeSchema,500000),
  aliases:list(z.object({renamed_from:NodeIDSchema,current:NodeIDSchema}).strict()), unresolved:list(text,10000),
}).strict().superRefine((graph,ctx) => {
  const keys = new Set(graph.nodes.map(n=>nodeKey(n.id)));
  if (keys.size !== graph.nodes.length || graph.edges.some(e=>!keys.has(nodeKey(e.source))||!keys.has(nodeKey(e.target)))) ctx.addIssue({code:'custom',message:'Graph contains duplicate or unmatched node identities.'});
});
const StateSchema = z.object({pinned_id:NodeIDSchema,current_id:NodeIDSchema,stale:z.boolean(),reasons:list(text,10000)}).strict();
const ExampleSchema = z.object({title:text,scope:text,overview:text,source:SourceSchema,steps:list(z.object({text,evidence:list(text,10000)}).strict(),10000),limits:list(text,10000)}).strict();
/** Exact-node explanation with source-pinned independent facets and unknowns. */
export const ExplanationSchema = z.object({
  node:LineageNodeSchema, definitions:list(StateSchema,10000), definitions_status:z.enum(['available','disabled']),unresolved:list(text,10000),
  job_flow:z.object({example:ExampleSchema.optional(),inputs:list(LineageNodeSchema),outputs:list(LineageNodeSchema),transformations:list(TransformationSchema,10000),summary:MachineSchema.optional(),unresolved:list(text,10000)}).strict().optional(),
}).strict();
export type NodeID = z.infer<typeof NodeIDSchema>;
export type LineageNode = z.infer<typeof LineageNodeSchema>;
export type LineageGraph = z.infer<typeof LineageGraphSchema>;
export type LineageEdge = z.infer<typeof EdgeSchema>;
export type Explanation = z.infer<typeof ExplanationSchema>;
/** Stable key for comparisons, including optional columns. */
export function nodeKey(id:NodeID):string { return JSON.stringify([id.namespace,id.name,id.column??'']); }
/** Human-readable source label. */
export function nodeLabel(id:NodeID):string { return id.column?`${id.name} · ${id.column}`:id.name; }
/** Nested escaping preserves namespace slashes, dataset paths and column punctuation. */
export function nodePath(raw:unknown):string {
  const id=NodeIDSchema.parse(raw);
  const wire=`${encodeURIComponent(id.namespace)}/${encodeURIComponent(id.name)}#${encodeURIComponent(id.column??'')}`;
  if(wire.length>8192)throw new Error('Node identity exceeds the supported wire limit.');
  return `/node/${encodeURIComponent(wire)}`;
}

import { z } from 'zod';

const text = z.string().min(1).max(32000);
const id = z.string().regex(/^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$/);
const digest = z.string().regex(/^(sha256:)?[a-f0-9]{64}$/);
const timestamp = z.iso.datetime({ offset: true });
/** An immutable, text-only agent definition retained by the research service. */
export const AgentDefinitionSchema = z.object({
  id, version: id, name: text, purpose: text, instructions: text,
  model: z.string().min(1).max(128), allowed_tools: z.array(z.never()).max(0),
  page_plugin: z.literal('run-summary'),
}).strict();
/** An agent definition with persistent identity. */
export const AgentRecordSchema = AgentDefinitionSchema.extend({ definition_digest: digest, mlflow_run_id: id });
/** One accepted experiment with one bounded attempt. */
export const ResearchSpecSchema = z.object({
  title: text, question: text, hypothesis: text, plan: text,
  agent_id: id, agent_version: id, accepted: z.literal(true), max_runs: z.literal(1),
  max_seconds: z.number().int().min(1).max(300), idempotency_key: id,
}).strict();
/** Evidence returned by the research service. Missing metrics stay missing. */
export const ResearchRecordSchema = z.object({
  research_id: id, experiment_id: id, attempt_id: id,
  title: text, question: text, hypothesis: text, plan: text,
  agent_id: id, agent_version: id, agent_definition_digest: digest,
  model: text, page_plugin: z.string().min(1).max(128), created_at: timestamp, updated_at: timestamp,
  status: z.enum(['RUNNING', 'FINISHED', 'FAILED', 'KILLED']),
  max_runs: z.literal(1), max_seconds: z.number().int().min(1).max(300),
  output: z.string().max(2_000_000).nullable(),
  metrics: z.record(z.string().max(128), z.number().finite()).refine(v => Object.keys(v).length <= 100),
  trace_id: z.string().max(128).nullable(), error: z.string().max(32000).nullable(),
}).strict();
/** The only packaged page that can receive selected research evidence. */
export const PluginManifestSchema = z.object({
  id: z.literal('run-summary'), version: z.literal('1'), name: text,
  entry_path: z.literal('/plugins/run-summary/index.html'),
  capabilities: z.tuple([z.literal('research.read')]),
}).strict();
export const RuntimeRequestSchema = z.object({
  research_id: id, attempt_id: id, agent: AgentRecordSchema, spec: ResearchSpecSchema,
}).strict().superRefine((v, ctx) => {
  if (v.agent.id !== v.spec.agent_id || v.agent.version !== v.spec.agent_version) {
    ctx.addIssue({ code: 'custom', message: 'Agent identity does not match the accepted specification.' });
  }
});
export type ResearchRecord = z.infer<typeof ResearchRecordSchema>;
export type AgentRecord = z.infer<typeof AgentRecordSchema>;
export type RuntimeRequest = z.infer<typeof RuntimeRequestSchema>;
export type PluginManifest = z.infer<typeof PluginManifestSchema>;
export interface SDKEvent { event: string; trace_id: string; span_id?: string; type?: string }
export interface Completion {
  attempt_id: string; status: 'FINISHED' | 'FAILED' | 'KILLED'; output: string;
  metrics: Record<string, number>; sdk_events: SDKEvent[]; error: string | null;
}

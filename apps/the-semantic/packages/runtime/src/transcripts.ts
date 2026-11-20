import { z } from 'zod';

const id = z.string().regex(/^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$/);
const time = z.iso.datetime({ offset: true });
// Match Python's code-point count; bound UTF-16 input before counting it.
const text = (max: number) => z.string().max(max * 2).refine(
  value => value.length <= max * 2 && [...value].length <= max,
  `Text must contain at most ${max} Unicode characters.`,
);
const requiredText = (max: number) => text(max).min(1).refine(v => v.trim().length > 0, 'Text is required.');
const block = (kind: 'input_text' | 'output_text') => z.object({type:z.literal(kind),text:text(262144)}).strict();
/** Historical public text and tool evidence. Tool arguments are inert data. */
export const TranscriptItemSchema = z.union([
  z.object({timestamp:time,type:z.literal('message'),role:z.literal('user'),phase:z.null(),content:z.array(block('input_text')).min(1).max(100)}).strict(),
  z.object({timestamp:time,type:z.literal('message'),role:z.literal('assistant'),phase:z.enum(['commentary','final','final_answer']).nullable(),content:z.array(block('output_text')).min(1).max(100)}).strict(),
  z.object({timestamp:time,type:z.literal('tool_call'),call_id:id,name:requiredText(256),arguments:text(262144),status:z.literal('completed').nullable()}).strict(),
  z.object({timestamp:time,type:z.literal('tool_output'),call_id:id,output:z.union([text(262144),z.array(block('input_text')).min(1).max(100)])}).strict(),
]);
/** Exact imported source, separate from alternating live-chat turns. */
export const TranscriptSourceSchema = z.object({
  source:z.literal('Native Codex rollout JSONL'),thread_id:id,title:requiredText(1000),description:requiredText(16000),
  redactions:z.object({}).strict(),items:z.array(TranscriptItemSchema).min(1).max(1000),
}).strict().superRefine((v,ctx) => {
  const calls = new Set<string>(), outputs = new Set<string>();
  for(const item of v.items) {
    if(item.type === 'tool_call') {
      if(calls.has(item.call_id))ctx.addIssue({code:'custom',message:'Tool call IDs must be unique.'});
      calls.add(item.call_id);
    } else if(item.type === 'tool_output') {
      if(!calls.has(item.call_id)||outputs.has(item.call_id))ctx.addIssue({code:'custom',message:'Tool output requires one preceding unmatched call.'});
      outputs.add(item.call_id);
    }
  }
  if(calls.size!==outputs.size)ctx.addIssue({code:'custom',message:'Every tool call requires one output.'});
  if(new TextEncoder().encode(JSON.stringify(v)).length>1048576)ctx.addIssue({code:'custom',message:'Transcript exceeds 1 MiB of UTF-8 JSON.'});
});
/** Immutable MLflow import record; proposal links are explicit and optional. */
export const TranscriptRecordSchema = z.object({transcript_id:id,imported_at:time,proposal_id:id.nullable(),transcript:TranscriptSourceSchema}).strict();
export const TranscriptSummarySchema = z.object({
  transcript_id:id,title:requiredText(1000),source_thread_id:id,created_at:time,updated_at:time,
  message_count:z.number().int().nonnegative().max(1000),tool_call_count:z.number().int().nonnegative().max(1000),
  tool_output_count:z.number().int().nonnegative().max(1000),proposal_id:id.nullable(),
}).strict();
export const TranscriptListSchema = z.object({transcripts:z.array(TranscriptSummarySchema).max(100)}).strict();
/** Explicit bounded import; no provider invocation or executable options. */
export const TranscriptImportSchema = z.object({transcript:TranscriptSourceSchema,proposal_id:id.nullable(),idempotency_key:z.uuid()}).strict();
export type TranscriptSource = z.infer<typeof TranscriptSourceSchema>;
export type TranscriptItem = z.infer<typeof TranscriptItemSchema>;
export type TranscriptRecord = z.infer<typeof TranscriptRecordSchema>;
export type TranscriptSummary = z.infer<typeof TranscriptSummarySchema>;
export type TranscriptImport = z.infer<typeof TranscriptImportSchema>;

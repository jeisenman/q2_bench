import { z } from 'zod';

const id = z.string().regex(/^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$/);
const savedText = z.string().max(16000);
const utc = z.iso.datetime({ offset: true }).refine(v => /(?:Z|\+00:00)$/.test(v), 'A UTC timestamp is required.');
/** Safe normalized native-session evidence; private payload fields are rejected. */
export const SessionEventSchema = z.object({
  event_id: id, at: utc,
  kind: z.enum(['user_message', 'assistant_message', 'tool', 'warning', 'error', 'lifecycle']),
  text: savedText.nullable(), tool_name: z.string().max(128).nullable(), status: z.string().max(128).nullable(),
}).strict().superRefine((event, ctx) => {
  if (event.kind === 'tool' && event.text !== null) ctx.addIssue({ code: 'custom', message: 'Tool payload text is unsupported.' });
});
/** A persisted native Codex session summary, separate from accepted experiments. */
export const SessionSummarySchema = z.object({
  session_id: id, title: savedText, model: z.string().min(1).max(128), cwd: savedText,
  codex_home: savedText, codex_binary: savedText, created_at: utc, updated_at: utc,
  status: z.enum(['ACTIVE', 'CLOSED', 'INTERRUPTED', 'FAILED']), exit_code: z.number().int().nullable(),
  event_count: z.number().int().min(0).max(1000), message_count: z.number().int().min(0).max(1000),
  trace_id: z.string().max(128).nullable(), error: savedText.nullable(),
}).strict().superRefine((summary, ctx) => {
  if (summary.message_count > summary.event_count) ctx.addIssue({ code: 'custom', message: 'Message count exceeds retained events.' });
});
/** Complete bounded session evidence with counts derived from retained events. */
export const SessionRecordSchema = SessionSummarySchema.safeExtend({ events: z.array(SessionEventSchema).max(1000) })
  .superRefine((record, ctx) => {
    if (record.event_count !== record.events.length || record.message_count !== record.events.filter(e => e.kind === 'user_message' || e.kind === 'assistant_message').length) {
      ctx.addIssue({ code: 'custom', message: 'Session counts do not match retained events.' });
    }
    if (new Set(record.events.map(e => e.event_id)).size !== record.events.length) ctx.addIssue({ code: 'custom', message: 'Duplicate session event IDs.' });
    if (new TextEncoder().encode(JSON.stringify(record)).length > 2_000_000) ctx.addIssue({ code: 'custom', message: 'Session evidence exceeds 2 MB.' });
  });
export type SessionSummary = z.infer<typeof SessionSummarySchema>;
export type SessionRecord = z.infer<typeof SessionRecordSchema>;
export type SessionEvent = z.infer<typeof SessionEventSchema>;

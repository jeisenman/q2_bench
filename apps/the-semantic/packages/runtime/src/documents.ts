import { z } from 'zod';
import { AgentDefinitionSchema } from './contracts.js';

const text = (max: number) => z.string().max(max).refine(v => v.trim().length > 0, 'Text is required.');
export const DocumentKindSchema = z.enum(['proposal', 'research', 'agent', 'sme']);
const narrative = { title: text(1000), question: text(16000), hypothesis: text(16000), plan: text(16000) };
export const DocumentContents = {
  proposal: z.object(narrative).strict(),
  research: z.object({ ...narrative, title:text(16000), output: z.string().max(200000).nullable() }).strict(),
  agent: AgentDefinitionSchema,
  sme: z.object({ text: z.string().max(16000), source_commit: z.string().min(1).max(128).nullable() }).strict(),
};
export const DocumentIdentitySchema = z.object({ kind: DocumentKindSchema, id: z.string().min(1).max(2048) }).strict();
const envelope = DocumentIdentitySchema.extend({ version: z.number().int().nonnegative().max(99), content: z.record(z.string(), z.unknown()), updated_at: z.iso.datetime({ offset: true }).nullable() }).strict();
/** A persisted document revision; version zero retains the source document. */
export const DocumentSchema = envelope.superRefine((v, ctx) => {
  if (!DocumentContents[v.kind].safeParse(v.content).success) ctx.addIssue({ code: 'custom', message: 'Invalid document content.' });
});
/** Explicit save with optimistic concurrency and stable retry identity. */
export const DocumentSaveSchema = DocumentIdentitySchema.extend({ base_version: z.number().int().nonnegative().max(99), content: z.record(z.string(), z.unknown()), idempotency_key: z.uuid() }).strict().superRefine((v, ctx) => {
  if (!DocumentContents[v.kind].safeParse(v.content).success || (v.kind === 'sme' && !String(v.content.text ?? '').trim())) ctx.addIssue({ code: 'custom', message: 'Invalid document content.' });
});
export const DocumentHistorySchema = z.object({ versions: z.array(DocumentSchema).max(100) }).strict();
export type DocumentKind = z.infer<typeof DocumentKindSchema>;
export type SavedDocument = z.infer<typeof DocumentSchema>;
export type DocumentSave = z.infer<typeof DocumentSaveSchema>;

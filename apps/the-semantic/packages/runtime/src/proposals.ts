import { z } from 'zod';

const id = z.string().regex(/^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$/);
const text = (max: number) => z.string().min(1).max(max).refine(value => value.trim().length > 0, 'Text is required.');
const utc = z.iso.datetime({ offset: true }).refine(value => /(?:Z|\+00:00)$/.test(value), 'A UTC timestamp is required.');
/** Finite draft proposal payload. It does not authorize an experiment. */
export const ProposalInputSchema = z.object({ title: text(1000), question: text(16000), hypothesis: text(16000), plan: text(16000), idempotency_key: text(128) }).strict();
/** Persisted draft proposal returned by the research service. */
export const ProposalRecordSchema = z.object({ proposal_id: id, title: text(1000), question: text(16000), hypothesis: text(16000), plan: text(16000), status: z.literal('DRAFT'), created_at: utc, updated_at: utc }).strict();
export const ProposalListSchema = z.object({ proposals: z.array(ProposalRecordSchema).max(100) }).strict();
export type ProposalRecord = z.infer<typeof ProposalRecordSchema>;
export type ProposalInput = z.infer<typeof ProposalInputSchema>;

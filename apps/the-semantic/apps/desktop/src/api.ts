import {TranscriptListSchema,TranscriptRecordSchema} from '../../../packages/runtime/src/transcripts.js';
import { ChatActivitySchema, ChatListSchema, ChatRecordSchema, ChatRequestSchema } from '../../../packages/runtime/src/chats.js';
import { z } from 'zod';
import { DocumentIdentitySchema, DocumentSchema, DocumentSaveSchema, DocumentHistorySchema } from '../../../packages/runtime/src/documents.js';
import { AgentDefinitionSchema, AgentRecordSchema, PluginManifestSchema, ResearchRecordSchema } from '../../../packages/runtime/src/contracts.js';
import { ProposalInputSchema, ProposalRecordSchema, ProposalListSchema } from '../../../packages/runtime/src/proposals.js';
import { SessionSummarySchema, SessionRecordSchema } from '../../../packages/runtime/src/sessions.js';
import { NodeIDSchema, LineageGraphSchema, ExplanationSchema, nodePath } from './lineage-contracts.js';
import { HelpRequestSchema, KnowledgeRequestSchema, knowledgePath, HelpArticleSchema, HelpListSchema, helpPath } from './help-contracts.js';
import { GherkinRequestSchema, GherkinCapabilitiesSchema, GherkinListSchema, GherkinFeatureSchema, gherkinPath } from './gherkin-contracts.js';
export const ReadSchema = z.discriminatedUnion('operation', [
  z.object({operation:z.literal('transcripts.list')}).strict(),
  z.object({operation:z.literal('transcripts.get'),id:z.string().regex(/^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$/)}).strict(),
  z.object({operation:z.literal('chats.activity'),id:z.string().regex(/^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$/),key:z.uuid()}).strict(),
  z.object({operation:z.literal('chats.list'),order:z.enum(['newest','oldest'])}).strict(),
  z.object({operation:z.literal('chats.get'),id:z.string().regex(/^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$/)}).strict(),
  DocumentIdentitySchema.extend({operation:z.literal('documents.get')}).strict(),
  DocumentIdentitySchema.extend({operation:z.literal('documents.history')}).strict(),
  ...GherkinRequestSchema.options, ...HelpRequestSchema.options, ...KnowledgeRequestSchema.options,
  z.object({operation:z.literal('lineage.graph')}).strict(),
  z.object({operation:z.literal('lineage.node'),id:NodeIDSchema}).strict(),
  z.object({ operation: z.literal('proposals.list'), order: z.enum(['newest', 'oldest']) }).strict(),
  z.object({ operation: z.literal('proposals.get'), id: z.string().regex(/^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$/) }).strict(),
  z.object({ operation: z.literal('research.list'), order: z.enum(['newest', 'oldest']) }).strict(),
  z.object({ operation: z.literal('research.get'), id: z.string().regex(/^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$/) }).strict(),
  z.object({ operation: z.literal('agents.list') }).strict(),
  z.object({ operation: z.literal('plugins.list') }).strict(),
  z.object({ operation: z.literal('sessions.list'), order: z.enum(['newest', 'oldest']) }).strict(),
  z.object({ operation: z.literal('sessions.get'), id: z.string().regex(/^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$/) }).strict(),
]);
export type ReadRequest = z.infer<typeof ReadSchema>;
export type Operation = ReadRequest['operation'];
/** Converts a finite IPC read request to a fixed API route. */
export function route(raw: unknown): string {
  const r = ReadSchema.parse(raw);
  switch (r.operation) {
    case 'gherkin.capabilities': case 'gherkin.list': case 'gherkin.search': case 'gherkin.feature': return gherkinPath(r);
    case 'transcripts.list': return '/api/research/v1/transcripts';
    case 'transcripts.get': return `/api/research/v1/transcripts/${encodeURIComponent(r.id)}`;
    case 'chats.activity': return `/api/research/v1/chats/${encodeURIComponent(r.id)}/activity?key=${encodeURIComponent(r.key)}`;
    case 'chats.list': return `/api/research/v1/chats?order=${r.order}`;
    case 'chats.get': return `/api/research/v1/chats/${encodeURIComponent(r.id)}`;
    case 'documents.get': case 'documents.history': return `/api/research/v1/documents${r.operation === 'documents.history' ? '/history' : ''}?kind=${r.kind}&id=${encodeURIComponent(r.id)}`;
    case 'help.list': case 'help.search': case 'help.article': return helpPath(r);
    case 'knowledge.list': case 'knowledge.search': case 'knowledge.article': return knowledgePath(r);
    case 'lineage.graph': return '/graph';
    case 'lineage.node': return nodePath(r.id);
    case 'proposals.list': return `/api/research/v1/proposals?order=${r.order}`;
    case 'proposals.get': return `/api/research/v1/proposals/${encodeURIComponent(r.id)}`;
    case 'research.list': return `/api/research/v1/research?order=${r.order}`;
    case 'research.get': return `/api/research/v1/research/${encodeURIComponent(r.id)}`;
    case 'agents.list': return '/api/research/v1/agents';
    case 'plugins.list': return '/api/research/v1/page-plugins';
    case 'sessions.list': return `/api/research/v1/sessions?order=${r.order}`;
    case 'sessions.get': return `/api/research/v1/sessions/${encodeURIComponent(r.id)}`;
  }
}
/** Validates all service evidence before it enters the renderer. */
export function validateResponse(operation: Operation | 'agent.created', value: unknown): unknown {
  switch (operation) {
    case 'agent.created': return AgentRecordSchema.parse(value);
    case 'gherkin.capabilities': return GherkinCapabilitiesSchema.parse(value);
    case 'gherkin.list': case 'gherkin.search': return GherkinListSchema.parse(value);
    case 'gherkin.feature': return GherkinFeatureSchema.parse(value);
    case 'transcripts.list': return TranscriptListSchema.parse(value);
    case 'transcripts.get': return TranscriptRecordSchema.parse(value);
    case 'chats.activity': return ChatActivitySchema.parse(value);
    case 'chats.list': return ChatListSchema.parse(value);
    case 'chats.get': return ChatRecordSchema.parse(value);
    case 'documents.get': return DocumentSchema.parse(value);
    case 'documents.history': return DocumentHistorySchema.parse(value);
    case 'knowledge.list': case 'knowledge.search': case 'help.list': case 'help.search': return HelpListSchema.parse(value);
    case 'knowledge.article': case 'help.article': return HelpArticleSchema.parse(value);
    case 'lineage.graph': return LineageGraphSchema.parse(value);
    case 'lineage.node': return ExplanationSchema.parse(value);
    case 'proposals.list': return ProposalListSchema.parse(value);
    case 'proposals.get': return ProposalRecordSchema.parse(value);
    case 'research.list': return z.object({ research: z.array(ResearchRecordSchema).max(100) }).strict().parse(value);
    case 'research.get': return ResearchRecordSchema.parse(value);
    case 'sessions.list': return z.object({ sessions: z.array(SessionSummarySchema).max(100) }).strict().parse(value);
    case 'sessions.get': return SessionRecordSchema.parse(value);
    case 'agents.list': return z.object({ agents: z.array(AgentRecordSchema).max(100) }).strict().parse(value);
    case 'plugins.list': return z.object({ plugins: z.array(PluginManifestSchema).max(20) }).strict().parse(value);
  }
}
/** Performs a bounded fixed-route read against the supplied trusted base. */
export async function readAPI(raw: unknown, base: string): Promise<unknown> {
  const request = ReadSchema.parse(raw);
  return requestAPI(base + route(request), request.operation);
}
/** Saves only a validated draft, with a caller-provided idempotency key. */
export async function saveProposalAPI(raw: unknown, base: string): Promise<unknown> {
  const payload = ProposalInputSchema.parse(raw);
  return requestAPI(base + '/api/research/v1/proposals', 'proposals.get', payload);
}
/** Saves a versioned document through the finite research endpoint. */
export async function saveDocumentAPI(raw: unknown, base: string): Promise<unknown> {
  return requestAPI(base + '/api/research/v1/documents', 'documents.get', DocumentSaveSchema.parse(raw));
}
/** Registers one validated immutable agent definition. */
export async function createAgentAPI(raw: unknown, base: string): Promise<unknown> {
  const definition = AgentDefinitionSchema.parse(raw);
  const result = AgentRecordSchema.parse(await requestAPI(base + '/api/research/v1/agents', 'agent.created', definition));
  for (const key of Object.keys(definition) as (keyof typeof definition)[]) {
    if (JSON.stringify(result[key]) !== JSON.stringify(definition[key])) throw new Error('Agent response does not match the submitted definition.');
  }
  return result;
}
async function requestAPI(url: string, operation: Operation | 'agent.created', payload?: unknown, timeout = 10000): Promise<unknown> {
  const response = await fetch(url, { method: payload ? 'POST' : 'GET', ...(payload ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) } : {}), signal: AbortSignal.timeout(timeout), credentials: 'omit', redirect: 'error' });
  if (!response.ok) throw new Error(`Research service returned HTTP ${response.status}.`);
  const reader = response.body?.getReader();
  if (!reader) throw new Error('Research service returned no response body.');
  let size = 0; const chunks: Uint8Array[] = [];
  try {
    while (true) {
      const { value, done } = await reader.read(); if (done) break;
      size += value.length;
      if (size > 8_000_000) throw new Error('Research response exceeds 8 MB.');
      chunks.push(value);
    }
  } finally { await reader.cancel(); }
  const bytes = new Uint8Array(size); let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
  return validateResponse(operation, JSON.parse(new TextDecoder().decode(bytes)));
}

/** Executes one explicit bounded chat mutation through the fixed API. */
export async function chatAPI(raw: unknown, base: string): Promise<unknown> {
  const request = ChatRequestSchema.parse(raw);
  if (request.operation === 'chats.create') {
    const {operation: _, ...payload} = request;
    return requestAPI(base + '/api/research/v1/chats', 'chats.get', payload);
  }
  const {operation: _, id, ...payload} = request;
  return requestAPI(base + `/api/research/v1/chats/${encodeURIComponent(id)}/messages`, 'chats.get', payload, 200000);
}

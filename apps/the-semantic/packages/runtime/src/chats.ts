import { z } from 'zod';

const id = z.string().regex(/^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$/);
const time = z.iso.datetime({ offset: true });
const text = (max: number) => z.string().min(1).max(max).refine(v => v.trim().length > 0, 'Text is required.');
/** Public operation metadata. It excludes prompts and provider payloads. */
export const ChatActivityEventSchema = z.object({
  name:z.enum(['agent_get','research_list','proposal_list','codex_complete','proposal_prepare','chat_save']),
  status:z.enum(['running','completed','failed']),elapsed_ms:z.number().int().nonnegative().safe(),
}).strict();
export const ChatActivitySchema = z.object({events:z.array(ChatActivityEventSchema).max(6),done:z.boolean()}).strict();
export type ChatActivity = z.infer<typeof ChatActivitySchema>;
/** A public chat message, without private reasoning or provider payloads. */
export const ChatMessageSchema = z.object({
  id, role:z.enum(['user','assistant']), text:text(32000), created_at:time,
  activity:z.array(ChatActivityEventSchema).max(6).optional(),
  proposal_id:id.nullable(), tool:z.object({name:z.literal('proposal_prepare'),status:z.literal('completed')}).strict().nullable(),
}).strict().superRefine((v,ctx) => {
  if ((v.proposal_id === null) !== (v.tool === null) || (v.role === 'user' && v.tool !== null)) ctx.addIssue({code:'custom',message:'Only an assistant tool result can attach a proposal.'});
});
/** A durable, versioned research conversation. It does not accept experiments. */
export const ChatRecordSchema = z.object({
  chat_id:id,title:text(1000),created_at:time,updated_at:time,version:z.number().int().nonnegative().max(50),messages:z.array(ChatMessageSchema).max(100),
}).strict().superRefine((v,ctx) => {
  if(v.messages.length!==v.version*2||v.messages.some((m,i)=>m.role!==(i%2?'assistant':'user')))ctx.addIssue({code:'custom',message:'Chat versions must retain complete user and assistant turns.'});
  if(new Set(v.messages.map(m=>m.id)).size!==v.messages.length)ctx.addIssue({code:'custom',message:'Chat message IDs must be unique.'});
});
export const ChatSummarySchema = z.object({chat_id:id,title:text(1000),created_at:time,updated_at:time,message_count:z.number().int().nonnegative().max(100)}).strict();
export const ChatListSchema = z.object({chats:z.array(ChatSummarySchema).max(100)}).strict();
/** Finite desktop mutations; no arbitrary prompt, model, executable or URL override. */
export const ChatRequestSchema = z.discriminatedUnion('operation',[
  z.object({operation:z.literal('chats.create'),title:text(1000),idempotency_key:z.uuid()}).strict(),
  z.object({operation:z.literal('chats.send'),id,message:text(16000),base_version:z.number().int().nonnegative(),idempotency_key:z.uuid()}).strict(),
]);
export type ChatRecord = z.infer<typeof ChatRecordSchema>;
export type ChatMessage = z.infer<typeof ChatMessageSchema>;
export type ChatRequest = z.infer<typeof ChatRequestSchema>;

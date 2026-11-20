import { ChatRecordSchema, ChatRequestSchema } from '../../../packages/runtime/src/chats.js';
import { DocumentSchema, DocumentSaveSchema } from '../../../packages/runtime/src/documents.js';
import { contextBridge, ipcRenderer } from 'electron';
import { ProposalInputSchema, ProposalRecordSchema } from '../../../packages/runtime/src/proposals.js';
import { ReadSchema, validateResponse } from './api.js';
import { AgentDefinitionSchema, AgentRecordSchema } from '../../../packages/runtime/src/contracts.js';

contextBridge.exposeInMainWorld('semantic', Object.freeze({
  async createAgent(raw: unknown): Promise<unknown> {
    return AgentRecordSchema.parse(await ipcRenderer.invoke('semantic:agents.create', AgentDefinitionSchema.parse(raw)));
  },
  async chat(raw: unknown): Promise<unknown> {
    return ChatRecordSchema.parse(await ipcRenderer.invoke('semantic:chat', ChatRequestSchema.parse(raw)));
  },
  async saveDocument(raw: unknown): Promise<unknown> {
    return DocumentSchema.parse(await ipcRenderer.invoke('semantic:documents.save', DocumentSaveSchema.parse(raw)));
  },
  async saveProposal(raw: unknown): Promise<unknown> {
    const payload = ProposalInputSchema.parse(raw);
    return ProposalRecordSchema.parse(await ipcRenderer.invoke('semantic:proposals.save', payload));
  },
  async read(raw: unknown): Promise<unknown> {
    const request = ReadSchema.parse(raw);
    return validateResponse(request.operation, await ipcRenderer.invoke('semantic:read', request));
  },
}));

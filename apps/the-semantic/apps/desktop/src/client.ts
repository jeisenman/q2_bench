import { validateResponse, route, readAPI, chatAPI, saveProposalAPI, saveDocumentAPI, type ReadRequest } from './api.js';
import { boundedJSON } from './bounded-json.js';
import { readLineage } from './lineage-client.js';
declare global { interface Window { semantic?: { read(request: ReadRequest): Promise<unknown>; chat?(request: unknown): Promise<unknown>; saveDocument(payload: unknown): Promise<unknown>; saveProposal(payload: unknown): Promise<unknown> } } }
/** Reads service evidence through preload, or the explicit Vite preview proxy. */
export async function read(request: ReadRequest): Promise<unknown> {
  if (window.semantic) return window.semantic.read(request);
  if (import.meta.env.DEV && location.origin === 'http://127.0.0.1:4175') {
    if(request.operation==='gherkin.capabilities'||request.operation==='gherkin.list'||request.operation==='gherkin.search'||request.operation==='gherkin.feature')return validateResponse(request.operation,await boundedJSON('/preview-gherkin'+route(request)));
    if(request.operation==='lineage.graph'||request.operation==='lineage.node')return readLineage(request,'/preview-lineage');
    if(request.operation==='knowledge.list'||request.operation==='knowledge.search'||request.operation==='knowledge.article')return validateResponse(request.operation,await boundedJSON('/preview-knowledge'+route(request)));
    if(request.operation==='help.list'||request.operation==='help.search'||request.operation==='help.article')return validateResponse(request.operation,await boundedJSON('/preview-help'+route(request)));
    return readAPI(request, '/preview-api');
  }
  throw new Error('The finite desktop read bridge is unavailable.');
}

/** Saves a draft through the finite desktop bridge or local preview proxy. */
export async function saveProposal(payload: unknown): Promise<unknown> {
  if (window.semantic) return window.semantic.saveProposal(payload);
  if (import.meta.env.DEV && location.origin === 'http://127.0.0.1:4175') return saveProposalAPI(payload, '/preview-api');
  throw new Error('The finite desktop mutation bridge is unavailable.');
}

/** Saves one revision through the finite desktop bridge. */
export async function saveDocument(payload: unknown): Promise<unknown> {
  if (window.semantic) return window.semantic.saveDocument(payload);
  if (import.meta.env.DEV && location.origin === 'http://127.0.0.1:4175') return saveDocumentAPI(payload, '/preview-api');
  throw new Error('The finite document bridge is unavailable.');
}

/** Sends one chat action through the authenticated host boundary. */
export async function chat(request: unknown): Promise<unknown> {
  if (window.semantic?.chat) return window.semantic.chat(request);
  if (window.semantic) throw new Error('Restart The Semantic to load the chat bridge.');
  if (import.meta.env.DEV && location.origin === 'http://127.0.0.1:4175') return chatAPI(request, '/preview-api');
  throw new Error('The finite chat bridge is unavailable.');
}

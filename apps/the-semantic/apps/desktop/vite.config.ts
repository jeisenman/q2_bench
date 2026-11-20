import { readGherkin } from './src/gherkin-source.js';
import { gherkinRequestFromPath } from './src/gherkin-contracts.js';
import { defineConfig } from 'vite';
import { lineageOrigin, lineageRequestFromPath, readLineage } from './src/lineage-client.js';
import { readKnowledgeSnapshot } from './src/knowledge-snapshot.js';
import { knowledgeRequestFromPath, helpRequestFromPath } from './src/help-contracts.js';
import { readHelpCenter } from './src/help-client.js';
/** Development proxy permits only finite renderer read operations. */
function allowedPreviewRead(method: string | undefined, rawURL: string | undefined): boolean {
  if (!rawURL) return false;
  const url = new URL(rawURL, 'http://127.0.0.1:4175');
  const path = url.pathname.replace(/^\/preview-api/, '');
  const keys = [...url.searchParams.keys()];
  if (method === 'POST') return keys.length === 0 && (['/api/research/v1/proposals', '/api/research/v1/proposals/prepare', '/api/research/v1/documents', '/api/research/v1/chats'].includes(path) || /^\/api\/research\/v1\/chats\/[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}\/messages$/.test(path));
  if (method !== 'GET') return false;
  if (path === '/api/research/v1/transcripts' || /^\/api\/research\/v1\/transcripts\/[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$/.test(path)) return keys.length === 0;
  if (/^\/api\/research\/v1\/chats\/[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}\/activity$/.test(path)) return keys.length === 1 && keys[0] === 'key' && /^[0-9a-f-]{36}$/i.test(url.searchParams.get('key') ?? '');
  if (['/api/research/v1/documents', '/api/research/v1/documents/history'].includes(path)) return keys.length === 2 && new Set(keys).size === 2 && keys.includes('kind') && keys.includes('id') && ['proposal','research','agent','sme'].includes(url.searchParams.get('kind') ?? '') && (url.searchParams.get('id')?.length ?? 0) > 0 && (url.searchParams.get('id')?.length ?? 0) <= 2048;
  if (path === '/api/research/v1/chats' || path === '/api/research/v1/research' || path === '/api/research/v1/sessions' || path === '/api/research/v1/proposals') {
    return keys.length === 1 && keys[0] === 'order' && ['newest', 'oldest'].includes(url.searchParams.get('order') ?? '');
  }
  return keys.length === 0 && (/^\/api\/research\/v1\/(?:chats|research|sessions|proposals)\/[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$/.test(path)
    || path === '/api/research/v1/agents' || path === '/api/research/v1/page-plugins');
}
export default defineConfig({
  base: './',
  plugins: [
    // Vite injects development CSS through style tags. Production stays self-only.
    { name: 'preview-style-csp', apply: 'serve', transformIndexHtml: html => html.replace("style-src 'self'", "style-src 'self' 'unsafe-inline'") },
    { name: 'production-csp', apply: 'build', transformIndexHtml: html => html.replace("connect-src 'self'", "connect-src 'none'") },
    { name: 'finite-preview-reads', configureServer(server) {
      server.middlewares.use('/preview-gherkin', async (request,response) => {
        try {
          if(request.method!=='GET')throw new Error('Read-only operation.');
          const data=await readGherkin(gherkinRequestFromPath(request.url??''));
          response.setHeader('Content-Type','application/json');response.end(JSON.stringify(data));
        } catch {response.statusCode=503;response.end('Gherkin source unavailable or request unsupported.');}
      });
      server.middlewares.use('/preview-lineage', async (request,response) => {
        try {
          if(request.method!=='GET')throw new Error('Read-only operation.');
          const data=await readLineage(lineageRequestFromPath(request.url??''),lineageOrigin(process.env.SEMANTIC_LINEAGE_URL));
          response.setHeader('Content-Type','application/json');response.end(JSON.stringify(data));
        } catch {response.statusCode=503;response.end('Current lineage service unavailable or request unsupported.');}
      });
      server.middlewares.use('/preview-knowledge', async (request,response) => {
        try {
          if(request.method!=='GET')throw new Error('Read-only operation.');
          const data=await readKnowledgeSnapshot(knowledgeRequestFromPath(request.url??''));
          response.setHeader('Content-Type','application/json');response.end(JSON.stringify(data));
        } catch {response.statusCode=503;response.end('Configured Zendesk snapshot unavailable or request unsupported.');}
      });
      server.middlewares.use('/preview-help', async (request,response) => {
        try {
          if(request.method!=='GET')throw new Error('Read-only operation.');
          const data=await readHelpCenter(helpRequestFromPath(request.url??''));
          response.setHeader('Content-Type','application/json');response.end(JSON.stringify(data));
        } catch {response.statusCode=503;response.end('Public Help Center unavailable or request unsupported.');}
      });
      server.middlewares.use('/preview-api', (request, response, next) => {
        if (allowedPreviewRead(request.method, request.url)) return next();
        response.statusCode = 403; response.end('Only finite research operations are permitted.');
      });
    } },
  ],
  server: {
    host: '127.0.0.1', port: 4175, strictPort: true,
    proxy: {
      '/preview-api': { timeout:210000, proxyTimeout:210000, target: 'http://127.0.0.1:5056', rewrite: p => p.replace(/^\/preview-api/, '') },
    },
  },
  build: { outDir: 'dist', emptyOutDir: true },
});

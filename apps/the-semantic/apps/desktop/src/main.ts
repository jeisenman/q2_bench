import { app, BrowserWindow, ipcMain, session, net, shell } from 'electron';
import path from 'node:path';
import { ReadSchema, readAPI, chatAPI, saveProposalAPI, saveDocumentAPI } from './api.js';
import { researchSessionArgument, forwardedResearchSession } from './launch.js';

import { lineageOrigin, readLineage } from './lineage-client.js';
import { readHelpCenter } from './help-client.js';
import { PublicArticleURLSchema } from './help-contracts.js';
import { readKnowledgeSnapshot } from './knowledge-snapshot.js';
const lineageBase=lineageOrigin(process.env.SEMANTIC_LINEAGE_URL);
app.setName('The Semantic');
let selectedSession = researchSessionArgument(process.argv);
let currentWindow: BrowserWindow | undefined;
const hasInstanceLock = app.requestSingleInstanceLock({ research_session: selectedSession ?? null });
if (!hasInstanceLock) app.quit();
app.on('second-instance', (_event, _args, _cwd, data) => {
  try {
    selectedSession = forwardedResearchSession(data) ?? selectedSession;
    if (!currentWindow && app.isReady()) createWindow();
    else if (currentWindow) {
      if (currentWindow.isMinimized()) currentWindow.restore();
      currentWindow.show(); currentWindow.focus();
      void currentWindow.loadFile(path.join(__dirname, '../dist/index.html'), { query: selectedSession ? { research_session: selectedSession } : {} });
    }
  } catch { console.error('Cannot open the requested research session: invalid session ID.'); }
});

function createWindow(): void {
  const index = path.join(__dirname, '../dist/index.html');
  const win = new BrowserWindow({ width: 1440, height: 1080, minWidth: 900, backgroundColor: '#f5f2e9',
    title: 'The Semantic', webPreferences: { preload: path.join(__dirname, 'preload.cjs'),
      nodeIntegration: false, contextIsolation: true, sandbox: true, webSecurity: true } });
  currentWindow = win;
  win.on('closed', () => { currentWindow = undefined; });
  ipcMain.removeHandler('semantic:read');
  ipcMain.handle('semantic:read', async (event, request: unknown) => {
    if (event.sender !== win.webContents || event.senderFrame !== win.webContents.mainFrame) throw new Error('Untrusted IPC sender.');
    const validated=ReadSchema.parse(request);
    if(validated.operation==='lineage.graph'||validated.operation==='lineage.node')return readLineage(validated,lineageBase,net.fetch);
    if(validated.operation==='knowledge.list'||validated.operation==='knowledge.search'||validated.operation==='knowledge.article')return readKnowledgeSnapshot(validated);
    if(validated.operation==='help.list'||validated.operation==='help.search'||validated.operation==='help.article')return readHelpCenter(validated,net.fetch);
    return readAPI(validated, 'http://127.0.0.1:5056');
  });
  ipcMain.removeHandler('semantic:proposals.save');
  ipcMain.handle('semantic:proposals.save', async (event, payload: unknown) => {
    if (event.sender !== win.webContents || event.senderFrame !== win.webContents.mainFrame) throw new Error('Untrusted IPC sender.');
    return saveProposalAPI(payload, 'http://127.0.0.1:5056');
  });
  ipcMain.removeHandler('semantic:chat');
  ipcMain.handle('semantic:chat', async (event, payload: unknown) => {
    if (event.sender !== win.webContents || event.senderFrame !== win.webContents.mainFrame) throw new Error('Untrusted IPC sender.');
    return chatAPI(payload, 'http://127.0.0.1:5056');
  });
  ipcMain.removeHandler('semantic:documents.save');
  ipcMain.handle('semantic:documents.save', async (event, payload: unknown) => {
    if (event.sender !== win.webContents || event.senderFrame !== win.webContents.mainFrame) throw new Error('Untrusted IPC sender.');
    return saveDocumentAPI(payload, 'http://127.0.0.1:5056');
  });
  win.webContents.setWindowOpenHandler(({url}) => {
    if(PublicArticleURLSchema.safeParse(url).success)void shell.openExternal(url);
    return { action: 'deny' };
  });
  win.webContents.on('will-navigate', event => event.preventDefault());
  win.webContents.on('will-frame-navigate', (event) => {
    if (event.url !== 'http://127.0.0.1:5056/plugins/run-summary/index.html') event.preventDefault();
  });
  win.webContents.on('will-attach-webview', event => event.preventDefault());
  session.defaultSession.setPermissionRequestHandler((_contents, _permission, callback) => callback(false));
  session.defaultSession.webRequest.onHeadersReceived((details, callback) => {
    if (details.url.startsWith('file:')) {
      callback({ responseHeaders: { ...details.responseHeaders, 'Content-Security-Policy': [
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'none'; frame-src http://127.0.0.1:5056; object-src 'none'; base-uri 'none'; form-action 'none'",
      ] } });
    } else callback({});
  });
  void win.loadFile(index, { query: selectedSession ? { research_session: selectedSession } : {} });
}
if (hasInstanceLock) void app.whenReady().then(createWindow);
app.on('activate', () => { if (hasInstanceLock && !currentWindow) createWindow(); });
app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit(); });

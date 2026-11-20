// Explicit smoke check against actual bundled main/preload and the local read API.
const { app, BrowserWindow } = require('electron');
const { spawn } = require('node:child_process');
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const os = require('node:os');
const secondary = process.env.SEMANTIC_NATIVE_SECONDARY === '1';
const statePath = process.env.SEMANTIC_NATIVE_STATE || fs.mkdtempSync(path.join(os.tmpdir(), 'semantic-native-'));
app.setPath('userData', statePath);
const flagIndex = process.argv.indexOf('--research-session');
const expectedSession = flagIndex >= 0 ? process.argv[flagIndex + 1] : undefined;
async function selectedRecord(window, id) {
  assert.equal(new URL(window.webContents.getURL()).searchParams.get('research_session'), id);
  const evidence = await window.webContents.executeJavaScript(`window.semantic.read({operation:'sessions.get',id:${JSON.stringify(id)}})`);
  assert.equal(evidence.session_id, id);
  // Wait for the actual renderer snapshot, without issuing an extra renderer read.
  const displayed = await window.webContents.executeJavaScript(`new Promise(resolve => {
    const ready = () => document.querySelector('.session-detail')?.dataset.sessionId === ${JSON.stringify(id)};
    if (ready()) return resolve(true);
    const observer = new MutationObserver(() => { if (ready()) { observer.disconnect(); clearTimeout(timer); resolve(true); } });
    observer.observe(document.querySelector('main'), {childList:true,subtree:true});
    const timer = setTimeout(() => { observer.disconnect(); resolve(false); }, 5000);
  })`);
  assert.equal(displayed, true, 'The selected exact session must appear in the actual renderer.');
  const content = await window.webContents.executeJavaScript("({heading:document.querySelector('.session-detail h2').textContent,text:document.querySelector('.session-detail').textContent,messages:document.querySelectorAll('.session-detail .user_message,.session-detail .assistant_message').length,events:document.querySelectorAll('.session-detail .session-event').length})");
  assert.ok(content.text.includes(evidence.model)); assert.ok(content.text.includes(evidence.status));
  assert.equal(content.heading,evidence.title || 'Native research session');
  assert.ok(!content.text.includes(id));
  if (evidence.trace_id) { assert.ok(!content.text.includes(evidence.trace_id)); assert.ok(content.text.includes('Trace evidenceRetained')); }
  assert.equal(content.messages,evidence.message_count); assert.equal(content.events,evidence.event_count);
}
if (!secondary) {
  app.on('quit', () => fs.rmSync(statePath, { recursive: true, force: true }));
  const timer = setTimeout(() => { console.error('Native desktop smoke timed out.'); app.exit(1); }, 25000);
  app.on('browser-window-created', (_event, window) => {
    window.hide();
    window.webContents.once('did-finish-load', async () => {
      try {
        const prefs = window.webContents.getLastWebPreferences();
        assert.equal(prefs.contextIsolation, true); assert.equal(prefs.sandbox, true); assert.equal(prefs.nodeIntegration, false);
        const result = await window.webContents.executeJavaScript(`(async () => {
          const agents = await window.semantic.read({operation:'agents.list'});
          let rejected = false;
          try { await window.semantic.read({operation:'shell',command:'ls'}); } catch { rejected = true; }
          let networkBlocked = false;
          try { await fetch('http://127.0.0.1:5056/health'); } catch { networkBlocked = true; }
          return {bridge: typeof window.semantic.read, require: typeof window.require,
            process: typeof window.process, agents: Array.isArray(agents.agents), rejected, networkBlocked,
            background: getComputedStyle(document.documentElement).backgroundColor,
            title: document.title, csp: document.querySelector('meta[http-equiv="Content-Security-Policy"]').content};
        })()`);
        assert.equal(result.bridge, 'function'); assert.equal(result.require, 'undefined'); assert.equal(result.process, 'undefined');
        assert.equal(result.agents, true); assert.equal(result.rejected, true); assert.equal(result.networkBlocked, true);
        if (expectedSession) await selectedRecord(window, expectedSession);
        assert.equal(result.background, 'rgb(245, 242, 233)');
        assert.equal(result.title, 'The Semantic'); assert.ok(result.csp.includes("connect-src 'none'"));
        const nextSession = process.env.SEMANTIC_TEST_SECOND_SESSION || expectedSession;
        const forwarded = new Promise(resolve => app.once('second-instance', resolve));
        const reloaded = new Promise(resolve => window.webContents.once('did-finish-load', resolve));
        const child = spawn(process.execPath, [__filename, ...(nextSession ? ['--research-session', nextSession] : [])], {
          env: { ...process.env, SEMANTIC_NATIVE_SECONDARY: '1', SEMANTIC_NATIVE_STATE: statePath }, stdio: 'ignore',
        });
        const exited = new Promise((resolve, reject) => { child.once('error', reject); child.once('exit', resolve); });
        await Promise.all([forwarded, reloaded, exited]);
        assert.equal(BrowserWindow.getAllWindows().length, 1);
        if (nextSession) await selectedRecord(window, nextSession);
        console.log(`PASS: actual Electron finite reads, single-instance reuse, isolation, CSS and CSP; exact saved session ${expectedSession ? 'verified' : 'not selected for this check'}.`);
        clearTimeout(timer); app.exit(0);
      } catch (error) { console.error(error); clearTimeout(timer); app.exit(1); }
    });
  });
}
require(path.resolve(__dirname, '../dist-electron/main.cjs'));

import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { JSDOM } from 'jsdom';
import { route, validateResponse } from '../src/api.js';
import { mountPlugin } from '../src/plugin.js';
import type { ResearchRecord } from '../../../packages/runtime/src/contracts.js';

const record: ResearchRecord = { research_id:'r1',experiment_id:'e1',attempt_id:'a1',title:'Retained result',question:'What?',hypothesis:'This.',plan:'Read.',
  agent_id:'agent',agent_version:'1',agent_definition_digest:'a'.repeat(64),model:'fixture-model',page_plugin:'run-summary',
  created_at:'2026-11-18T12:00:00Z',updated_at:'2026-11-18T12:00:01Z',status:'FINISHED',max_runs:1,max_seconds:90,
  output:'<script>untrusted</script>',metrics:{input_tokens:19,output_tokens:7,duration_seconds:0.4},trace_id:'trace_1',error:null };
const manifest = {id:'run-summary',version:'1',name:'Run Summary',entry_path:'/plugins/run-summary/index.html',capabilities:['research.read']};
test('finite read bridge rejects arbitrary URL, path traversal and extra properties', () => {
  assert.equal(route({operation:'research.get',id:'r1'}),'/api/research/v1/research/r1');
  assert.equal(route({operation:'research.list',order:'oldest'}),'/api/research/v1/research?order=oldest');
  for (const value of [{operation:'shell',command:'ls'},{operation:'research.get',id:'../secret'},{operation:'agents.list',url:'https://example.com'}]) assert.throws(()=>route(value));
  assert.throws(()=>validateResponse('research.list',{research:[{...record,metrics:{bad:Infinity}}]}));
  assert.deepEqual(validateResponse('research.get',record),record);
});
test('iframe host limits sandbox and source, transfers selected evidence and closes ports', () => {
  const dom = new JSDOM('<div id="host"></div>',{url:'http://127.0.0.1:4175'});
  Object.assign(globalThis,{document:dom.window.document});
  const oldChannel=globalThis.MessageChannel;
  let closed=0; const data:unknown[]=[];
  class FakeChannel { port1={postMessage:(v:unknown)=>data.push(v),close:()=>closed++};port2={close:()=>closed++}; }
  Object.assign(globalThis,{MessageChannel:FakeChannel});
  try {
    const host=document.querySelector<HTMLElement>('#host')!;
    const cleanup=mountPlugin(host,manifest,record); const frame=host.querySelector('iframe')!;
    assert.equal(frame.getAttribute('sandbox'),'allow-scripts');
    assert.equal(frame.hasAttribute('credentialless'),true);
    assert.equal(frame.src,'http://127.0.0.1:5056/plugins/run-summary/index.html');
    let init:unknown; Object.defineProperty(frame.contentWindow,'postMessage',{value:(v:unknown)=>{init=v;}});
    frame.dispatchEvent(new dom.window.Event('load'));
    assert.deepEqual(init,{type:'semantic.init',version:1});
    assert.deepEqual(data,[{type:'semantic.data',version:1,research:record}]);
    cleanup(); assert.equal(closed,2); assert.equal(host.children.length,0);
    assert.throws(()=>mountPlugin(host,{...manifest,entry_path:'https://evil.invalid'},record));
  } finally { globalThis.MessageChannel=oldChannel; dom.window.close(); }
});
test('plugin validates messages, uses safe DOM, shows units, and reports missing metrics', async () => {
  const source=await readFile(new URL('../../../plugins/run-summary/page.js',import.meta.url),'utf8');
  const dom=new JSDOM('<p id="state"></p><div id="evidence"></div>',{runScripts:'outside-only',url:'http://127.0.0.1:5056/plugins/run-summary/index.html'});
  dom.window.eval(source);
  let receive: ((message:{data:unknown})=>void)|undefined;
  const port={start(){},close(){},set onmessage(v:typeof receive){receive=v;}};
  dom.window.dispatchEvent(new dom.window.MessageEvent('message',{source:dom.window as unknown as Window, data:{type:'semantic.init',version:1},ports:[port as unknown as MessagePort]}));
  assert.ok(receive);
  receive({data:{type:'semantic.data',version:1,research:record}});
  assert.ok(dom.window.document.body.textContent!.includes('19 tokens'));
  assert.ok(!dom.window.document.body.textContent!.includes(record.attempt_id));
  assert.ok(dom.window.document.body.textContent!.includes('0.4 seconds'));
  assert.equal(dom.window.document.querySelectorAll('script').length,0);
  assert.ok(dom.window.document.querySelector('pre')!.textContent!.includes('<script>'));
  receive({data:{type:'semantic.data',version:1,research:{...record,metrics:{}}}});
  assert.match(dom.window.document.body.textContent!,/No tokens measurements retained/);
  receive({data:{type:'semantic.data',version:2,research:record}});
  assert.match(dom.window.document.querySelector('#state')!.textContent!,/failed validation/);
  dom.window.close();
});
test('production security settings deny node, popup, webview and renderer network', async () => {
  const main=await readFile(new URL('../src/main.ts',import.meta.url),'utf8');
  const config=await readFile(new URL('../vite.config.ts',import.meta.url),'utf8');
  for(const setting of ['nodeIntegration: false','contextIsolation: true','sandbox: true',"action: 'deny'","'will-attach-webview'","connect-src 'none'"]) assert.ok(main.includes(setting));
  assert.ok(config.includes("connect-src 'none'"));
});

test('article links are allowlisted in main and never create a child BrowserWindow',async()=>{
  const main=await readFile(new URL('../src/main.ts',import.meta.url),'utf8');
  assert.ok(main.includes('PublicArticleURLSchema.safeParse(url).success'));
  assert.ok(main.includes('shell.openExternal(url)'));
  assert.ok(main.includes("return { action: 'deny' }"));
});

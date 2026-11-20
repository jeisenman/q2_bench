import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { JSDOM } from 'jsdom';
import { build } from 'esbuild';
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
    const cleanup=mountPlugin(host,manifest,{...record,title:'Result trace_id: hidden-trace',output:'Result '+ 'a'.repeat(64)}); const frame=host.querySelector('iframe')!;
    assert.equal(frame.getAttribute('sandbox'),'allow-scripts');
    assert.equal(frame.hasAttribute('credentialless'),true);
    assert.equal(frame.src,'http://127.0.0.1:5056/plugins/run-summary/index.html');
    let init:unknown; Object.defineProperty(frame.contentWindow,'postMessage',{value:(v:unknown)=>{init=v;}});
    frame.dispatchEvent(new dom.window.Event('load'));
    assert.deepEqual(init,{type:'semantic.init',version:1});
    assert.deepEqual(data,[{type:'semantic.data',version:1,research:{title:'Internal execution metadata omitted.',model:record.model,status:record.status,output:'Result [internal reference]'}}]);
    cleanup(); assert.equal(closed,2); assert.equal(host.children.length,0);
    assert.throws(()=>mountPlugin(host,{...manifest,entry_path:'https://evil.invalid'},record));
  } finally { globalThis.MessageChannel=oldChannel; dom.window.close(); }
});
test('plugin accepts only human-readable result fields and uses safe DOM', async () => {
  const source=await readFile(new URL('../../../plugins/run-summary/page.js',import.meta.url),'utf8');
  const dom=new JSDOM('<p id="state"></p><div id="evidence"></div>',{runScripts:'outside-only',url:'http://127.0.0.1:5056/plugins/run-summary/index.html'});
  dom.window.eval(source);
  let receive: ((message:{data:unknown})=>void)|undefined;
  const port={start(){},close(){},set onmessage(v:typeof receive){receive=v;}};
  dom.window.dispatchEvent(new dom.window.MessageEvent('message',{source:dom.window as unknown as Window, data:{type:'semantic.init',version:1},ports:[port as unknown as MessagePort]}));
  assert.ok(receive);
  const result={title:record.title,model:record.model,status:record.status,output:record.output};
  receive({data:{type:'semantic.data',version:1,research:result}});
  assert.ok(dom.window.document.body.textContent!.includes(record.title));
  for(const hidden of [record.research_id,record.experiment_id,record.attempt_id,record.agent_id,record.agent_definition_digest,record.trace_id ?? '', 'input_tokens','runtime_duration_seconds','19','0.4']) assert.ok(!dom.window.document.body.textContent!.includes(hidden));
  assert.equal(dom.window.document.querySelectorAll('script').length,0);
  assert.ok(dom.window.document.querySelector('pre')!.textContent!.includes('<script>'));
  receive({data:{type:'semantic.data',version:1,research:{...result,metrics:record.metrics}}});
  assert.match(dom.window.document.querySelector('#state')!.textContent!,/failed validation/);
  receive({data:{type:'semantic.data',version:2,research:record}});
  assert.match(dom.window.document.querySelector('#state')!.textContent!,/failed validation/);
  dom.window.close();
});
test('research renderer does not expose internal codes or numeric measurements',async()=>{
  const source=await readFile(new URL('../src/renderer.ts',import.meta.url),'utf8');
  for(const forbidden of ['Definition digest','MLflow agent run','Agent digest','Trace ID','Retained metrics','Object.entries(r.metrics)','Page plugin unavailable:','duration_seconds','input_tokens']) assert.ok(!source.includes(forbidden),forbidden);
  assert.ok(source.includes("'Run references'"));
  assert.ok(source.includes("'Results panel'"));
});
test('research and agent views project service narrative text while retaining the source records',async()=>{
  const research={...record,title:'Study\nresearch_id: private-run',question:'Public question\ntrace_id: private-trace',output:'{"finding":"Unverified","runtime_duration_seconds":12,"trace_id":"private-trace"}'};
  const agent={id:'agent',version:'1',name:'Analyst\ntrace_id: private-trace',purpose:'Review evidence',instructions:'Check sources\nattempt_id: private-attempt',model:'fixture-model',allowed_tools:[],page_plugin:'run-summary',definition_digest:'a'.repeat(64),mlflow_run_id:'agent-run'};
  const snapshot=JSON.stringify({research,agent});
  const bundle=await build({entryPoints:[new URL('../src/renderer.ts',import.meta.url).pathname],bundle:true,write:false,format:'iife',loader:{'.css':'empty'},define:{'import.meta.env.DEV':'false'}});
  const dom=new JSDOM('<div id="app"></div>',{url:'http://127.0.0.1:4175',runScripts:'outside-only'});
  Object.assign(dom.window,{semantic:{read:async(request:{operation:string})=>{
    if(request.operation==='research.list')return {research:[research]};if(request.operation==='research.get')return research;
    if(request.operation==='agents.list')return {agents:[agent]};if(request.operation==='plugins.list')return {plugins:[]};
    throw Error('Unexpected read');
  }}});
  const settle=()=>new Promise(resolve=>setImmediate(resolve));dom.window.eval(bundle.outputFiles[0]!.text);await settle();
  const assertHidden=()=>assert.doesNotMatch(dom.window.document.body.textContent!,/private-run|private-trace|private-attempt|runtime_duration_seconds|a{64}/);
  assertHidden();dom.window.document.querySelector<HTMLButtonElement>('.question-row')!.click();await settle();assertHidden();assert.match(dom.window.document.querySelector('.stage .output')!.textContent!,/Unverified/);
  [...dom.window.document.querySelectorAll<HTMLButtonElement>('nav button')].find(button=>button.textContent==='Agent Catalog')!.click();await settle();assertHidden();assert.match(dom.window.document.body.textContent!,/Check sources/);
  assert.equal(JSON.stringify({research,agent}),snapshot);dom.window.close();
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

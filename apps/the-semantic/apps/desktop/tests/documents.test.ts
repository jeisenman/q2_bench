import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import { mountDocumentEditor } from '../src/document-editor.js';
import { route, saveDocumentAPI } from '../src/api.js';
import { DocumentSaveSchema } from '../../../packages/runtime/src/documents.js';

const original = {kind:'proposal' as const,id:'p1',version:0,content:{title:'Title',question:'Question',hypothesis:'Hypothesis',plan:'Plan'},updated_at:null};
const tick = () => new Promise(resolve => setTimeout(resolve,0));
function setup() {
  const dom = new JSDOM('<div id="host"></div>',{url:'http://127.0.0.1:4175'});
  Object.assign(globalThis,{window:dom.window,document:dom.window.document});
  const host = document.querySelector<HTMLElement>('#host')!;
  const click = (text:string) => [...host.querySelectorAll('button')].find(b=>b.textContent===text)!.click();
  return {dom,host,click};
}
test('edit preloads the source, cancel writes nothing, save publishes and history retains the source',async()=>{
  const {dom,host,click} = setup(); let writes=0; let saved:any;
  const reader = async(r:any)=>r.operation==='documents.history'?{versions:[original,saved]}:original;
  const saver = async(p:any)=>{writes++;return saved={...original,content:p.content,version:1,updated_at:'2026-11-19T12:00:00Z'};};
  const stop = mountDocumentEditor(host,{kind:'proposal',id:'p1'},reader,saver);
  click('Edit'); await tick(); assert.equal(host.querySelector<HTMLInputElement>('[name=title]')!.value,'Title');
  click('Cancel'); assert.equal(writes,0); assert.equal(host.querySelector('form'),null);
  click('Edit'); await tick(); const field=host.querySelector<HTMLInputElement>('[name=title]')!;
  field.value='<script>updated</script>';field.dispatchEvent(new dom.window.Event('input'));
  host.querySelector('form')!.dispatchEvent(new dom.window.Event('submit',{cancelable:true}));await tick();
  assert.equal(writes,1);assert.match(host.textContent!,/Version 1/);assert.equal(host.querySelector('form'),null);
  click('Version history');await tick();assert.match(host.textContent!,/Original document/);assert.equal(host.querySelector('script'),null);assert.match(host.textContent!,/<script>updated<\/script>/);
  stop();dom.window.close();
});
test('failed saves retain text and replay identity; duplicate submit is bounded',async()=>{
  const {dom,host,click}=setup();const keys:string[]=[];
  const stop=mountDocumentEditor(host,{kind:'proposal',id:'p1'},async()=>original,async(p:any)=>{keys.push(p.idempotency_key);throw Error('conflict');});
  click('Edit');await tick();const field=host.querySelector<HTMLInputElement>('[name=title]')!;field.value='User text';field.dispatchEvent(new dom.window.Event('input'));
  const submit=()=>host.querySelector('form')!.dispatchEvent(new dom.window.Event('submit',{cancelable:true}));
  submit();submit();await tick();assert.equal(keys.length,1);assert.equal(field.value,'User text');assert.match(host.textContent!,/text is retained/);
  submit();await tick();assert.equal(keys[0],keys[1]);stop();dom.window.close();
});
test('external SME controls retain highlight on save failure and clear it after confirmed save', async () => {
  const { dom, host } = setup(); const actions = document.createElement('header'); host.before(actions);
  const source = {kind:'sme' as const,id:'node',version:0,content:{text:'Source definition',source_commit:null},updated_at:null};
  let fail = true;
  const stop = mountDocumentEditor(host,{kind:'sme',id:'node',actionsHost:actions,editableRegion:host},async()=>source,async p=>{
    if(fail) throw Error('offline'); return {...source,version:1,content:DocumentSaveSchema.parse(p).content,updated_at:'2026-11-19T12:00:00Z'};
  });
  actions.querySelector('button')!.click(); await tick();
  const field = host.querySelector('textarea')!; field.value='Updated definition';field.dispatchEvent(new dom.window.Event('input'));
  const submit=()=>host.querySelector('form')!.dispatchEvent(new dom.window.Event('submit',{cancelable:true}));
  submit();await tick();assert.ok(host.classList.contains('document-editing'));assert.equal(field.value,'Updated definition');
  fail=false;submit();await tick();assert.equal(host.classList.contains('document-editing'),false);assert.equal(host.querySelector('form'),null);
  assert.equal(actions.querySelector('button')!.disabled,false);stop();assert.equal(actions.children.length,0);dom.window.close();
});
test('wrong document responses fail closed and invalid writes never reach fetch',async()=>{
  const {dom,host,click}=setup();
  const stop=mountDocumentEditor(host,{kind:'proposal',id:'p1'},async()=>({...original,id:'other'}));
  click('Edit');await tick();assert.equal(host.querySelector('form'),null);assert.match(host.textContent!,/Cannot read/);
  assert.equal(route({operation:'documents.get',kind:'sme',id:'["ns","name",""]'}),'/api/research/v1/documents?kind=sme&id=%5B%22ns%22%2C%22name%22%2C%22%22%5D');
  assert.equal(DocumentSaveSchema.safeParse({kind:'sme',id:'node',base_version:0,content:{text:' ',source_commit:null},idempotency_key:'k'}).success,false);
  await assert.rejects(saveDocumentAPI({kind:'unknown'},'http://127.0.0.1:5056'));
  stop();dom.window.close();
});
test('unsaved navigation asks before discarding edits',async()=>{
  const {dom,host,click}=setup();const outside=document.createElement('button');document.body.append(outside);let navigated=0;outside.onclick=()=>{navigated++;};
  const stop=mountDocumentEditor(host,{kind:'proposal',id:'p1'},async()=>original);
  click('Edit');await tick();host.querySelector('input')!.dispatchEvent(new dom.window.Event('input'));
  dom.window.confirm=()=>false;outside.click();assert.equal(navigated,0);
  dom.window.confirm=()=>true;outside.click();assert.equal(navigated,1);stop();dom.window.close();
});
test('SME starts from supplied source and saves a clearly local version',async()=>{
  const {dom,host,click}=setup();let payload:any;
  const stop=mountDocumentEditor(host,{kind:'sme',id:'["ns","name",""]',seed:{text:'Approved source',source_commit:'abc'}},async()=>({kind:'sme',id:'["ns","name",""]',version:0,content:{text:'',source_commit:null},updated_at:null}),async(p:any)=>{payload=p;return {kind:p.kind,id:p.id,version:1,content:p.content,updated_at:'2026-11-19T12:00:00Z'};});
  click('Edit');await tick();assert.equal(host.querySelector('textarea')!.value,'Approved source');assert.match(host.textContent!,/local SME draft/);
  host.querySelector('form')!.dispatchEvent(new dom.window.Event('submit',{cancelable:true}));await tick();assert.equal(payload.content.source_commit,'abc');assert.equal(payload.content.text,'Approved source');stop();dom.window.close();
});
test('agent aliases resolve to a stable anchor and existing pins are not editable',async()=>{
  const {dom,host,click}=setup();let payload:any;
  const content={id:'author',version:'2',name:'Author',purpose:'Research',instructions:'Check evidence',model:'gpt-6.1-sol',allowed_tools:[],page_plugin:'run-summary'};
  const stop=mountDocumentEditor(host,{kind:'agent',id:'new-run'},async()=>({kind:'agent',id:'anchor-run',version:1,content,updated_at:'2026-11-19T12:00:00Z'}),async(p:any)=>{payload=p;return {kind:p.kind,id:p.id,version:2,content:p.content,updated_at:'2026-11-19T12:01:00Z'};});
  click('Edit');await tick();assert.equal(host.querySelector('[name=id]'),null);host.querySelector<HTMLInputElement>('[name=version]')!.value='3';
  host.querySelector('form')!.dispatchEvent(new dom.window.Event('submit',{cancelable:true}));await tick();assert.equal(payload.id,'anchor-run');assert.equal(payload.content.version,'3');assert.deepEqual(payload.content.allowed_tools,[]);stop();dom.window.close();
});

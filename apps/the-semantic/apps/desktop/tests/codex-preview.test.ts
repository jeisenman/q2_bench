import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import { createCodexView } from '../src/codex-view.js';
import { ChatRecordSchema } from '../../../packages/runtime/src/chats.js';
import { ChatRequestSchema } from '../../../packages/runtime/src/chats.js';
import { route } from '../src/api.js';
import type { ChatRecord } from '../../../packages/runtime/src/chats.js';
const time='2026-11-19T12:00:00Z';
const empty:ChatRecord={chat_id:'chat1',title:'A question',created_at:time,updated_at:time,version:0,messages:[]};
const reply:ChatRecord={...empty,version:1,messages:[{id:'u1',role:'user',text:'Can scenario experience help?',created_at:time,proposal_id:null,tool:null},{id:'a1',role:'assistant',text:'Here is a draft.',created_at:time,proposal_id:'p1',tool:{name:'proposal_prepare',status:'completed'}}]};
const proposal={proposal_id:'p1',title:'Learning and ROE',question:'Does experience help?',hypothesis:'A proposed association.',plan:'Verify the data.',status:'DRAFT',created_at:time,updated_at:time};
const tick=()=>new Promise(r=>setImmediate(r));
function setup(options:{fail?:boolean;result?:ChatRecord}={}){
 const dom=new JSDOM('<main></main>',{url:'http://127.0.0.1:4175'});Object.assign(globalThis,{document:dom.window.document});
 const calls:any[]=[];let modal:any;let stopped=0;const host=document.querySelector('main')!;
 const view=createCodexView({reader:async(r:any)=>r.operation==='chats.list'?{chats:[]}:r.operation==='proposals.get'?proposal:empty,
 sender:async(r:any)=>{calls.push(r);if(r.operation==='chats.create')return empty;if(options.fail)throw Error('offline');const result=structuredClone(options.result??reply);result.messages[result.messages.length-2]!.text=r.message;return result;},
 animate:(host,text,done)=>{host.textContent=text;done();return()=>{};},
 openProposal:(p)=>{modal=p;return()=>{stopped++;};}});
 let dispose=view.mount(host);
 const send=(text:string)=>{const field=host.querySelector('textarea')!;field.value=text;field.dispatchEvent(new dom.window.Event('input'));host.querySelector('form')!.dispatchEvent(new dom.window.Event('submit',{cancelable:true}));};
 return{dom,host,calls,send,get modal(){return modal;},get stopped(){return stopped;},remount(){dispose();dispose=view.mount(host);},close(){dispose();dom.window.close();}};
}
test('a real chat action returns a persisted proposal attachment without a keyword trigger',async()=>{
 const s=setup();await tick();s.send('Can scenario experience help?');await tick();await tick();
 assert.equal(s.host.querySelector('[aria-current=page][data-chat-id]')?.getAttribute('data-chat-id'),'chat1');assert.equal(s.calls.length,2);assert.equal(s.calls[1].operation,'chats.send');assert.equal(s.host.querySelectorAll('.codex-proposal-attachment').length,1);assert.match(s.host.textContent!,/proposal_prepare/);
 s.host.querySelector<HTMLButtonElement>('.codex-proposal-attachment')!.click();await tick();assert.equal(s.modal.proposal_id,'p1');
 s.remount();assert.equal(s.stopped,1);s.close();
});
test('a clarification does not invent a proposal attachment',async()=>{
 const noDraft={...reply,messages:[reply.messages[0]!,{...reply.messages[1]!,text:'Which loan population?',proposal_id:null,tool:null}]};
 const s=setup({result:noDraft});await tick();s.send('Draft the question and plan');await tick();await tick();assert.match(s.host.textContent!,/Which loan population/);assert.equal(s.host.querySelector('.codex-proposal-attachment'),null);s.close();
});
test('uncertain send retains text, rejects double submit and reuses the request key',async()=>{
 const s=setup({fail:true});await tick();s.send('Keep this text');const form=s.host.querySelector('form')!;form.dispatchEvent(new s.dom.window.Event('submit',{cancelable:true}));await tick();await tick();
 assert.equal(s.calls.filter(x=>x.operation==='chats.send').length,1);assert.equal(s.host.querySelector('textarea')!.value,'Keep this text');assert.match(s.host.textContent!,/text is retained/);
 s.host.querySelector('form')!.dispatchEvent(new s.dom.window.Event('submit',{cancelable:true}));await tick();assert.equal(s.calls[1].idempotency_key,s.calls[2].idempotency_key);s.close();
});
test('unsafe service text stays inert and chat contracts reject private fields',async()=>{
 const s=setup({result:{...reply,messages:reply.messages.map(m=>({...m,text:'<img src=x onerror=alert(1)>'}))}});await tick();s.send('<script>question</script>');await tick();await tick();assert.equal(s.host.querySelector('img,script'),null);assert.match(s.host.textContent!,/<img/);s.close();
 assert.throws(()=>ChatRecordSchema.parse({...empty,reasoning:'private'}));assert.throws(()=>ChatRequestSchema.parse({operation:'chats.send',id:'../file',message:'x',idempotency_key:crypto.randomUUID(),base_version:0}));
 assert.throws(()=>ChatRequestSchema.parse({operation:'chats.create',title:'x',model:'other',idempotency_key:crypto.randomUUID()}));assert.equal(route({operation:'chats.list',order:'newest'}),'/api/research/v1/chats?order=newest');
});
test('pending chat displays observed operations before the reply and retains saved activity',async()=>{
 const dom=new JSDOM('<main></main>',{url:'http://127.0.0.1:4175'});Object.assign(globalThis,{document:dom.window.document});
 let resolve!:(value:unknown)=>void;const event={name:'codex_complete' as const,status:'running' as const,elapsed_ms:1200};
 const host=document.querySelector('main')!;
 const view=createCodexView({reader:async r=>r.operation==='chats.list'?{chats:[]}:r.operation==='chats.activity'?{events:[event],done:false}:empty,
 sender:async r=>ChatRequestSchema.parse(r).operation==='chats.create'?empty:new Promise(r=>{resolve=r;}),animate:(h,t,done)=>{h.textContent=t;done();return()=>{};}});
 const dispose=view.mount(host);await tick();const field=host.querySelector('textarea')!;field.value='Can scenario experience help?';field.dispatchEvent(new dom.window.Event('input'));host.querySelector('form')!.dispatchEvent(new dom.window.Event('submit',{cancelable:true}));await tick();
 assert.match(host.querySelector('.codex-live-activity')!.textContent!,/Request Codex reply/);assert.equal(host.querySelector('.codex-live-activity details')!.hasAttribute('open'),true);
 const saved=structuredClone(reply);saved.messages[1]!.activity=[{...event,status:'completed'}];resolve(saved);await tick();
 assert.equal(host.querySelector('.codex-live-activity'),null);assert.match(host.querySelector('.codex-message-assistant .codex-activity')!.textContent!,/completed · 1.2s/);
 dispose();dom.window.close();
});

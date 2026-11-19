import test from 'node:test';
import assert from 'node:assert/strict';
import {JSDOM} from 'jsdom';
import {createCodexView} from '../src/codex-view.js';
import {chatSidebar} from '../src/chat-sidebar.js';
import type {ChatRecord} from '../../../packages/runtime/src/chats.js';
const time='2026-11-19T12:00:00Z';
const records:ChatRecord[]=['Loan scenario study','Matched offers'].map((title,index)=>({chat_id:`chat${index}`,title,created_at:time,updated_at:time,version:0,messages:[]}));
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function setup(){
 const dom=new JSDOM('<main></main>',{url:'http://127.0.0.1:4175'});Object.assign(globalThis,{document:dom.window.document});
 const host=document.querySelector('main')!;let calls=0;
 const view=createCodexView({reader:async r=>{calls++;if(r.operation==='chats.list')return {chats:records.map(record=>({chat_id:record.chat_id,title:record.title,created_at:time,updated_at:time,message_count:0}))};if(r.operation==='chats.get')return records.find(record=>record.chat_id===r.id);throw Error('Unexpected read');},sender:async()=>{throw Error('Navigation cannot send');}});
 const dispose=view.mount(host);
 return {dom,host,get calls(){return calls;},close(){dispose();dom.window.close();}};
}
test('sidebar switches saved chats and marks the active conversation without sending',async()=>{
 const s=setup();await tick();assert.equal(s.host.querySelector('select'),null);assert.equal(s.host.querySelector('[aria-current=page][data-chat-id]')?.getAttribute('data-chat-id'),'chat0');
 s.host.querySelector<HTMLButtonElement>('[data-chat-id=chat1]')!.click();await tick();assert.equal(s.host.querySelector('.codex-thread-heading h2')!.textContent,'Matched offers');assert.equal(s.host.querySelector('[aria-current=page][data-chat-id]')?.getAttribute('data-chat-id'),'chat1');
 s.host.querySelector<HTMLButtonElement>('.codex-new-chat')!.click();assert.equal(s.host.querySelector('.codex-thread-heading h2')!.textContent,'A new question.');assert.equal(s.host.querySelector('[aria-current=page][data-chat-id]'),null);s.close();
});
test('chat switching protects unsent text and active-chat clicks leave it in place',async()=>{
 const s=setup();await tick();let prompts=0;s.dom.window.confirm=()=>{prompts++;return false;};
 const field=s.host.querySelector('textarea')!;field.value='Keep this question';field.dispatchEvent(new s.dom.window.Event('input'));
 s.host.querySelector<HTMLButtonElement>('[data-chat-id=chat1]')!.click();await tick();assert.equal(prompts,1);assert.equal(s.host.querySelector('textarea')!.value,'Keep this question');assert.equal(s.host.querySelector('.codex-thread-heading h2')!.textContent,records[0]!.title);
 const before=s.calls;s.host.querySelector<HTMLButtonElement>('[data-chat-id=chat0]')!.click();await tick();assert.equal(prompts,1);assert.equal(s.calls,before);
 s.dom.window.confirm=()=>true;s.host.querySelector<HTMLButtonElement>('[data-chat-id=chat1]')!.click();await tick();assert.equal(s.host.querySelector('textarea')!.value,'');s.close();
});
test('search filters titles locally, keeps text inert, and pending turns disable navigation',()=>{
 const dom=new JSDOM('<main></main>');Object.assign(globalThis,{document:dom.window.document});let query='';
 const sidebar=chatSidebar({chats:[...records,{chat_id:'unsafe',title:'<img src=x onerror=alert(1)>'}],pending:true,query:'',onQuery:value=>{query=value;},onOpen:()=>assert.fail('Pending navigation'),onNew:()=>assert.fail('Pending new chat'),onRefresh:()=>assert.fail('Pending refresh')});document.querySelector('main')!.append(sidebar);
 assert.equal(sidebar.querySelector('img'),null);assert.ok([...sidebar.querySelectorAll('button')].every(button=>button.disabled));
 const input=sidebar.querySelector('input')!;input.value='matched';input.dispatchEvent(new dom.window.Event('input'));assert.equal(query,'matched');assert.equal(sidebar.querySelectorAll('[data-chat-id]').length,1);assert.equal(sidebar.querySelector('[data-chat-id]')!.getAttribute('data-chat-id'),'chat1');
 input.value='absent';input.dispatchEvent(new dom.window.Event('input'));assert.match(sidebar.textContent!,/No matching chats/);dom.window.close();
});
test('message-style rows use saved timestamps and loaded previews without inventing messages',()=>{
 const dom=new JSDOM('<main></main>');Object.assign(globalThis,{document:dom.window.document});
 const sidebar=chatSidebar({chats:[{...records[0]!,updated_at:time,preview:'<img src=x> Saved reply'},{...records[1]!,message_count:4}],currentID:'chat0',pending:false,query:'',onQuery:()=>{},onOpen:()=>{},onNew:()=>{},onRefresh:()=>{}});
 const items=sidebar.querySelectorAll('[data-chat-id]');assert.equal(items[0]!.querySelector('.codex-chat-icon')!.textContent,'LS');assert.equal(items[0]!.querySelector('time')!.dateTime,time);assert.match(items[0]!.querySelector('time')!.title,/UTC/);assert.equal(items[0]!.querySelector('.codex-chat-preview')!.textContent,'<img src=x> Saved reply');assert.equal(sidebar.querySelector('img'),null);assert.match(items[1]!.textContent!,/4 messages · Open conversation/);dom.window.close();
});

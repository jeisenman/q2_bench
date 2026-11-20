import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import { activityPanel, watchActivity } from '../src/chat-activity.js';
import { ChatActivitySchema, ChatRecordSchema } from '../../../packages/runtime/src/chats.js';
import { route, validateResponse } from '../src/api.js';
const tick=()=>new Promise(r=>setImmediate(r));
const key='a04a153b-585b-40f3-8ee8-81c2487584b0';
const activity={events:[{name:'codex_complete' as const,status:'running' as const,elapsed_ms:250}],done:false};

test('activity uses a finite read route and rejects payloads or invented operations',()=>{
 assert.equal(route({operation:'chats.activity',id:'chat1',key}),`/api/research/v1/chats/chat1/activity?key=${key}`);
 assert.deepEqual(validateResponse('chats.activity',activity),activity);
 for(const value of [{...activity,reasoning:'private'},{events:[{...activity.events[0],name:'shell'}],done:true},{events:[{...activity.events[0],elapsed_ms:-1}],done:true},{events:[{...activity.events[0],output:'private'}],done:true}])assert.throws(()=>ChatActivitySchema.parse(value));
});
test('activity shows observed status and operation name without retained timings',()=>{
 const dom=new JSDOM('<main></main>');Object.assign(globalThis,{document:dom.window.document});
 const panel=activityPanel(activity,true);assert.equal(panel.open,false);assert.match(panel.textContent!,/Request Codex reply/);assert.match(panel.textContent!,/running/);assert.doesNotMatch(panel.textContent!,/0\.3s|250|elapsed_ms/);assert.match(panel.textContent!,/codex_complete/);assert.equal(activity.events[0]!.elapsed_ms,250);
 assert.equal(activityPanel({...activity,done:true}).open,false);dom.window.close();
});
test('cancelled live reads cannot update an unmounted conversation',async()=>{
 let resolve!:(value:unknown)=>void;let updates=0;
 const stop=watchActivity(async()=>new Promise(r=>{resolve=r;}),'chat1',key,()=>{updates++;});
 stop();resolve(activity);await tick();assert.equal(updates,0);
});
test('completed activity stops polling and malformed evidence becomes unavailable',async()=>{
 let calls=0;const updates:unknown[]=[];
 const stop=watchActivity(async()=>{calls++;return {...activity,done:true};},'chat1',key,v=>updates.push(v));
 await tick();assert.equal(calls,1);assert.equal(updates.length,1);stop();
 const failed=watchActivity(async()=>({private:'payload'}),'chat1',key,v=>updates.push(v));await tick();assert.equal(updates[1],undefined);failed();
});
test('persisted activity remains readable alongside legacy messages',()=>{
 const time='2026-11-19T12:00:00Z';const message={id:'u1',role:'user',text:'A question',created_at:time,proposal_id:null,tool:null};
 const record={chat_id:'c1',title:'Question',created_at:time,updated_at:time,version:1,messages:[message,{...message,id:'a1',role:'assistant',activity:[{...activity.events[0],status:'completed'}]}]};
 assert.equal(ChatRecordSchema.parse(record).messages[1]!.activity!.length,1);
 delete (record.messages[1] as any).activity;assert.doesNotThrow(()=>ChatRecordSchema.parse(record));
});

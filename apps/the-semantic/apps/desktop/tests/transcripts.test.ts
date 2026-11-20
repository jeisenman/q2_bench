import test from 'node:test';import assert from 'node:assert/strict';import {JSDOM} from 'jsdom';
import {TranscriptRecordSchema,TranscriptItemSchema,TranscriptListSchema,type TranscriptRecord} from '../../../packages/runtime/src/transcripts.js';
import {historicalTranscript} from '../src/transcript-view.js';
import {createCodexView} from '../src/codex-view.js';
import {route,validateResponse,ReadSchema} from '../src/api.js';
const time='2026-11-18T20:00:00Z';
const record:TranscriptRecord={transcript_id:'history1',imported_at:time,proposal_id:'proposal1',transcript:{source:'Native Codex rollout JSONL',thread_id:'source1',title:'Scenario modeling and ROE',description:'Public recorded evidence.',redactions:{},items:[
 {type:'message',timestamp:time,role:'user',phase:null,content:[{type:'input_text',text:'Does scenario modeling improve ROE?'}]},
 {type:'message',timestamp:time,role:'assistant',phase:'commentary',content:[{type:'output_text',text:'I will inspect the saved source.'}]},
 {type:'tool_call',timestamp:time,call_id:'call1',name:'exec_command',arguments:'{"cmd":"never execute"}',status:'completed'},
 {type:'tool_output',timestamp:time,call_id:'call1',output:[{type:'input_text',text:'Warning: truncated output\nRecorded source.'}]},
 {type:'tool_call',timestamp:time,call_id:'call2',name:'read',arguments:'{}',status:'completed'},
 {type:'tool_output',timestamp:time,call_id:'call2',output:'<script>never execute</script>'},
 {type:'message',timestamp:time,role:'assistant',phase:'final_answer',content:[{type:'output_text',text:'- **Agent:** Hypothesis v1, Sol 6.1.\n\n```sql\nselect Roe\n```'}]},
]}};
const summary={transcript_id:record.transcript_id,title:record.transcript.title,source_thread_id:'source1',created_at:time,updated_at:time,message_count:3,tool_call_count:2,tool_output_count:2,proposal_id:'proposal1'};
const tick=()=>new Promise(resolve=>setImmediate(resolve));
test('historical source renders all messages and tool records in order with inert Markdown',async()=>{
 const dom=new JSDOM('<main></main>');Object.assign(globalThis,{document:dom.window.document});let opened='';
 const root=historicalTranscript(record,id=>{opened=id;});document.querySelector('main')!.append(root);
 assert.deepEqual([...root.querySelectorAll('[data-source-index]')].map(el=>el.getAttribute('data-source-index')),['0','1','2','3','4','5','6']);
 assert.equal(root.querySelectorAll('.codex-message').length,3);assert.equal(root.querySelectorAll('.codex-tool-record').length,4);assert.ok([...root.querySelectorAll('.codex-tool-group')].every(el=>!el.hasAttribute('open')));
 assert.equal(root.querySelector('li strong')!.textContent,'Agent:');assert.equal(root.querySelector('.chat-markdown pre code')!.textContent,'select Roe');
 const tool=root.querySelector<HTMLDetailsElement>('.codex-tool-record')!;tool.open=true;tool.dispatchEvent(new dom.window.Event('toggle'));assert.equal(tool.querySelector('pre code')!.textContent,'{"cmd":"never execute"}');
 const output=root.querySelectorAll<HTMLDetailsElement>('.codex-tool-record')[1]!;output.open=true;output.dispatchEvent(new dom.window.Event('toggle'));assert.match(output.querySelector('pre code')!.textContent!,/Recorded source/);assert.equal(root.querySelector('script'),null);
 const select=root.querySelector('select')!;select.value='messages';select.dispatchEvent(new dom.window.Event('change'));assert.equal(root.querySelectorAll('.codex-tool-group').length,0);assert.equal(root.querySelectorAll('.codex-message').length,3);
 root.querySelector<HTMLButtonElement>('.codex-proposal-attachment')!.click();assert.equal(opened,'proposal1');dom.window.close();
});
test('single recorded calls are also grouped and collapsed',()=>{
 const dom=new JSDOM('<main></main>');Object.assign(globalThis,{document:dom.window.document});const one=structuredClone(record);one.transcript.items.splice(4,2);
 const root=historicalTranscript(one,()=>{});assert.equal(root.querySelector('.codex-tool-group>summary')!.textContent,'1 tool call');assert.equal(root.querySelector('.codex-tool-group')!.hasAttribute('open'),false);dom.window.close();
});
test('sidebar and deep link open a read-only transcript without sending a model turn',async()=>{
 const dom=new JSDOM('<main></main>',{url:'http://127.0.0.1:4175/?tab=codex&transcript=history1'});Object.assign(globalThis,{document:dom.window.document});let sends=0;const reads:string[]=[];
 const view=createCodexView({reader:async request=>{reads.push(request.operation);if(request.operation==='transcripts.list')return {transcripts:[summary]};if(request.operation==='transcripts.get')return record;if(request.operation==='chats.list')return {chats:[]};throw Error('Unexpected read');},sender:async()=>{sends++;throw Error('No model call');}});
 const host=document.querySelector('main')!;const dispose=view.mount(host);await tick();assert.match(host.textContent!,/Historical conversation/);assert.equal(host.querySelector('.codex-message-composer'),null);assert.equal(host.querySelector('[aria-current=page][data-chat-id]')!.getAttribute('data-chat-id'),'history:history1');assert.equal(sends,0);assert.ok(reads.includes('transcripts.get'));
 host.querySelector<HTMLButtonElement>('.codex-new-chat')!.click();assert.ok(host.querySelector('.codex-message-composer'));assert.equal(host.querySelector('.codex-historical'),null);dispose();dom.window.close();
});
test('finite historical reads validate source and reject executable or private additions',()=>{
 assert.equal(route({operation:'transcripts.list'}),'/api/research/v1/transcripts');assert.equal(route({operation:'transcripts.get',id:'history1'}),'/api/research/v1/transcripts/history1');assert.deepEqual(validateResponse('transcripts.get',record),record);
 assert.throws(()=>ReadSchema.parse({operation:'transcripts.get',id:'../private'}));assert.throws(()=>ReadSchema.parse({operation:'transcripts.import',command:'exec'}));
 assert.throws(()=>TranscriptRecordSchema.parse({...record,reasoning:'private'}));const bad=structuredClone(record);(bad.transcript.items[1] as any).phase='analysis';assert.throws(()=>TranscriptRecordSchema.parse(bad));
});
test('initial transcript deep link survives a remount during its first read',async()=>{
 const dom=new JSDOM('<main></main>',{url:'http://127.0.0.1:4175/?tab=codex&transcript=history1'});Object.assign(globalThis,{document:dom.window.document});const pending:((value:unknown)=>void)[]=[];
 const view=createCodexView({reader:async request=>{if(request.operation==='chats.list')return {chats:[]};if(request.operation==='transcripts.list')return {transcripts:[summary]};if(request.operation==='transcripts.get')return new Promise(resolve=>pending.push(resolve));throw Error('Unexpected read');},sender:async()=>{throw Error('No model call');}});
 const host=document.querySelector('main')!;const first=view.mount(host);await tick();assert.equal(pending.length,1);first();const second=view.mount(host);await tick();assert.equal(pending.length,2);pending[0]!(record);await tick();assert.equal(host.querySelector('.codex-historical'),null);pending[1]!(record);await tick();assert.ok(host.querySelector('.codex-historical'));second();dom.window.close();
});
test('transcript Unicode limits count code points and retain the UTF-8 payload cap',()=>{
 const unicode=structuredClone(record);unicode.transcript.title='😀'.repeat(1000);
 assert.doesNotThrow(()=>TranscriptRecordSchema.parse(unicode));
 assert.doesNotThrow(()=>TranscriptListSchema.parse({transcripts:[{...summary,title:unicode.transcript.title}]}));
 unicode.transcript.title+='😀';assert.equal(TranscriptRecordSchema.safeParse(unicode).success,false);
 assert.equal(TranscriptListSchema.safeParse({transcripts:[{...summary,title:unicode.transcript.title}]}).success,false);
 const message={type:'message',timestamp:time,role:'user',phase:null,content:[{type:'input_text',text:'😀'.repeat(262144)}]};
 assert.doesNotThrow(()=>TranscriptItemSchema.parse(message));
 assert.equal(TranscriptRecordSchema.safeParse({...record,transcript:{...record.transcript,items:[message]}}).success,false);
 message.content[0]!.text+='😀';assert.equal(TranscriptItemSchema.safeParse(message).success,false);
 message.content[0]!.text='x'.repeat(262145);assert.equal(TranscriptItemSchema.safeParse(message).success,false);
});
test('a failed historical proposal read shows an error and keeps the transcript read-only',async()=>{
 const dom=new JSDOM('<main></main>',{url:'http://127.0.0.1:4175/?tab=codex&transcript=history1'});Object.assign(globalThis,{document:dom.window.document});let sends=0;let proposalReads=0;
 const view=createCodexView({reader:async request=>{if(request.operation==='chats.list')return {chats:[]};if(request.operation==='transcripts.list')return {transcripts:[summary]};if(request.operation==='transcripts.get')return record;if(request.operation==='proposals.get'){proposalReads++;throw Error('Unavailable');}throw Error('Unexpected read');},sender:async()=>{sends++;throw Error('No model call');}});
 const host=document.querySelector('main')!;const dispose=view.mount(host);await tick();
 host.querySelector<HTMLButtonElement>('.codex-proposal-attachment')!.click();await tick();
 assert.equal(proposalReads,1);assert.match(host.querySelector('[role=status]')!.textContent!,/Cannot open the saved proposal/);
 assert.ok(host.querySelector('.codex-historical'));assert.equal(host.querySelector('.codex-message-composer'),null);assert.equal(sends,0);
 dispose();dom.window.close();
});
test('historical messages, labels and tool evidence hide internal metadata without changing the import',()=>{
 const dom=new JSDOM('<main></main>');Object.assign(globalThis,{document:dom.window.document});
 const source=structuredClone(record);source.transcript.title='Question\nresearch_id: private-run';source.transcript.description='Public evidence.\ntrace_id: private-trace';
 source.transcript.thread_id='a'.repeat(32);
 const call=source.transcript.items[2]!;if(call.type!=='tool_call')throw Error('Expected call');call.name='b'.repeat(64);call.arguments='{"question":"Check association","attempt_id":"private-attempt","usage":{"total_tokens":750}}';
 const output=source.transcript.items[3]!;if(output.type!=='tool_output')throw Error('Expected output');output.output='Read complete.\nelapsed_ms: 12345\ntrace_id: private-trace';
 const snapshot=JSON.stringify(source);const root=historicalTranscript(source,()=>{});
 for(const details of root.querySelectorAll<HTMLDetailsElement>('.codex-tool-record')){details.open=true;details.dispatchEvent(new dom.window.Event('toggle'));}
 assert.match(root.textContent!,/Check association/);assert.match(root.textContent!,/Read complete/);
 assert.doesNotMatch(root.textContent!,/private-run|private-trace|private-attempt|750|12345|a{32}|b{64}/);assert.equal(JSON.stringify(source),snapshot);dom.window.close();
});

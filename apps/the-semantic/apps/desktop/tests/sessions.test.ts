import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import { SessionRecordSchema, SessionSummarySchema, type SessionRecord } from '../../../packages/runtime/src/sessions.js';
import { route, validateResponse } from '../src/api.js';
import { researchSessionArgument, forwardedResearchSession } from '../src/launch.js';
import { mountSessions, safeSessionText } from '../src/session-view.js';

const record: SessionRecord = { session_id:'session-1',title:'Native fixture',model:'gpt-6.1-sol',cwd:'/fixture',codex_home:'/fixture/codex',codex_binary:'/fixture/bin/codex',
  created_at:'2026-11-18T12:00:00Z',updated_at:'2026-11-18T12:00:01Z',status:'ACTIVE',exit_code:null,event_count:3,message_count:2,trace_id:'trace-1',error:null,
  events:[{event_id:'event-1',at:'2026-11-18T12:00:00Z',kind:'user_message',text:'<img src=x onerror=alert(1)> api_key=do-not-display',tool_name:null,status:null},
    {event_id:'event-2',at:'2026-11-18T12:00:00Z',kind:'assistant_message',text:'Saved answer.',tool_name:null,status:null},
    {event_id:'event-3',at:'2026-11-18T12:00:01Z',kind:'tool',text:null,tool_name:'semantic_research',status:'completed'}] };
const { events: _events, ...summary } = record;
const settle = () => new Promise<void>(resolve=>setImmediate(resolve));
function setup() { const dom=new JSDOM('<main></main>');Object.assign(globalThis,{document:dom.window.document});return {dom,host:dom.window.document.querySelector('main')!}; }
test('session titles and tool labels hide execution metadata without changing saved evidence',async()=>{
  const {dom,host}=setup();const source=structuredClone(record);source.title='Review question\ntrace_id: private-trace';source.events[2]!.tool_name='research_id: private-run';source.events[2]!.status='elapsed_ms: 12345';const snapshot=JSON.stringify(source);
  const {events:ignored,...listing}=source;
  const dispose=mountSessions(host,{selectedID:source.session_id},async request=>request.operation==='sessions.list'?{sessions:[listing]}:source);await settle();
  assert.match(host.textContent!,/Review question/);assert.doesNotMatch(host.textContent!,/private-trace|private-run|12345/);assert.equal(JSON.stringify(source),snapshot);dispose();dom.window.close();
});
test('session routes are finite and launch flag accepts only one bounded ID', () => {
  assert.equal(route({operation:'sessions.list',order:'newest'}),'/api/research/v1/sessions?order=newest');
  assert.equal(route({operation:'sessions.get',id:'session-1'}),'/api/research/v1/sessions/session-1');
  assert.throws(()=>route({operation:'sessions.close',id:'session-1'}));
  assert.throws(()=>route({operation:'sessions.get',id:'../secret'}));
  assert.equal(researchSessionArgument(['electron','app','--research-session','session-1']),'session-1');
  assert.equal(researchSessionArgument(['electron','app']),undefined);
  assert.equal(forwardedResearchSession({research_session:'session-1'}),'session-1');
  assert.equal(forwardedResearchSession({research_session:null}),undefined);
  for(const value of [{research_session:'../secret'},{research_session:'one',url:'bad'},null,{},[]]) assert.throws(()=>forwardedResearchSession(value));
  for(const args of [['--research-session'],['--research-session','https://bad'],['--research-session','one','--research-session','two']]) assert.throws(()=>researchSessionArgument(args));
});
test('session boundary rejects private payloads, invalid counts and unsafe evidence', () => {
  assert.deepEqual(validateResponse('sessions.get',record),record);
  assert.equal(SessionSummarySchema.safeParse(summary).success,true);
  for(const r of [{...record,event_count:99},{...record,message_count:0},{...record,reasoning:'private'},
    {...record,events:[{...record.events[0],tool_payload:'private'}]},
    {...record,event_count:1,message_count:0,events:[{...record.events[2],text:'private tool result'}]},
    {...record,created_at:'2026-11-18T12:00:00+01:00'}]) assert.equal(SessionRecordSchema.safeParse(r).success,false);
});
test('exact selected session renders saved messages and status with credential and HTML defenses', async () => {
  const {dom,host}=setup(); const requests:unknown[]=[];
  const cleanup=mountSessions(host,{selectedID:record.session_id},async request=>{requests.push(request);return request.operation==='sessions.list'?{sessions:[summary]}:record;});
  await settle();
  assert.deepEqual(requests,[{operation:'sessions.list',order:'newest'},{operation:'sessions.get',id:'session-1'}]);
  assert.equal(host.querySelector('.session-detail')?.getAttribute('data-session-id'),record.session_id);
  assert.equal(host.querySelector('.session-detail h2')?.textContent,record.title);
  assert.ok(!host.textContent!.includes(record.session_id)); assert.ok(!host.textContent!.includes(record.trace_id!));
  assert.match(host.textContent!,/Trace evidenceRetained/);
  assert.match(host.textContent!,/gpt-6.1-sol/);assert.match(host.textContent!,/Saved answer/);assert.match(host.textContent!,/semantic_research · completed/);
  assert.match(host.textContent!,/api_key=\[REDACTED\]/);assert.ok(!host.textContent!.includes('do-not-display'));
  assert.equal(host.querySelectorAll('img,script').length,0);assert.match(host.textContent!,/<img src=x/);
  assert.match(host.textContent!,/Counts are not live/);assert.match(host.textContent!,/active/);
  cleanup();dom.window.close();
  assert.ok(!safeSessionText('{"api_key":"private-value"} https://alice:private-value@example.invalid AKIA1234567890123456').includes('private-value'));
  assert.ok(!safeSessionText('Bearer abcdefgh sk-abcdefgh1234567890 password=12345').includes('12345'));
});
test('active empty state, terminal failure, stale read and disposal are explicit', async () => {
  const {dom,host}=setup();let failed=false;
  const empty={...record,events:[],event_count:0,message_count:0};
  const cleanup=mountSessions(host,{selectedID:record.session_id},async request=>{if(failed)throw new Error('offline');return request.operation==='sessions.list'?{sessions:[summary]}:empty;});
  await settle();assert.match(host.textContent!,/saved before the first prompt/);
  failed=true;(host.querySelector('button') as HTMLButtonElement).click();await settle();
  assert.match(host.textContent!,/STALE SNAPSHOT/);assert.match(host.textContent!,/Cannot read/);cleanup();
  host.replaceChildren();const cleanupFailure=mountSessions(host,{selectedID:record.session_id},async request=>request.operation==='sessions.list'?{sessions:[summary]}:{...empty,status:'FAILED',error:'Model access denied; no fallback.'});
  await settle();assert.match(host.textContent!,/Model access denied; no fallback/);cleanupFailure();
  host.replaceChildren();const cleanupEmpty=mountSessions(host,{},async()=>({sessions:[]}));await settle();assert.match(host.textContent!,/No native research sessions/);cleanupEmpty();
  let release:(v:unknown)=>void=()=>{};host.replaceChildren();const cleanupPending=mountSessions(host,{},()=>new Promise(resolve=>{release=resolve;}));
  cleanupPending();const before=host.textContent;release({sessions:[summary]});await settle();assert.equal(host.textContent,before);
  dom.window.close();
});

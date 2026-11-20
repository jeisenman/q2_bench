// Native IPC and renderer verification with isolated API fixtures; no provider call.
const {app}=require('electron');
const fs=require('node:fs');const os=require('node:os');const path=require('node:path');const assert=require('node:assert/strict');
const profile=fs.mkdtempSync(path.join(os.tmpdir(),'semantic-chat-native-'));app.setPath('userData',profile);
const time='2026-11-19T12:00:00Z';
const empty={chat_id:'fixture-chat',title:'Scenario learning',created_at:time,updated_at:time,version:0,messages:[]};
const answer={...empty,version:1,messages:[{id:'u1',role:'user',text:'Does scenario experience improve ROE?',created_at:time,proposal_id:null,tool:null},{id:'a1',role:'assistant',text:'I have enough information to prepare a draft for review. The learning baseline remains open.',created_at:time,proposal_id:'fixture-proposal',tool:{name:'proposal_prepare',status:'completed'}}]};
answer.messages[1].activity=['agent_get','research_list','proposal_list','codex_complete','proposal_prepare','chat_save'].map(name=>({name,status:'completed',elapsed_ms:100}));
let proposal={proposal_id:'fixture-proposal',title:'Scenario experience and ROE',question:'Does prior scenario experience improve ROE?',hypothesis:'A proposed association.',plan:'Verify sources and define the learning baseline.',status:'DRAFT',created_at:time,updated_at:time};
const source={...proposal};let version=0;let sends=0;let writes=0;
const transcript={source:'Native Codex rollout JSONL',thread_id:'fixture-thread',title:'Scenario history',description:'Recorded fixture conversation.',redactions:{},items:[
 {timestamp:time,type:'message',role:'user',phase:null,content:[{type:'input_text',text:'How do scenarios affect ROE?'}]},
 {timestamp:time,type:'message',role:'assistant',phase:'commentary',content:[{type:'output_text',text:'- **Agent:** Review prior research.\n\n```sql\nSELECT roe\n```'}]},
 {timestamp:time,type:'tool_call',call_id:'fixture-call',name:'research_list',arguments:'{"query":"ROE"}',status:'completed'},
 {timestamp:time,type:'tool_output',call_id:'fixture-call',output:'No results'},
 {timestamp:time,type:'message',role:'assistant',phase:'final_answer',content:[{type:'output_text',text:'The source remains unverified.'}]},
]};
const content=()=>Object.fromEntries(['title','question','hypothesis','plan'].map(k=>[k,proposal[k]]));
global.fetch=async(raw,init)=>{
 const url=new URL(String(raw));if(url.origin!=='http://127.0.0.1:5056')throw Error('Unexpected fixture origin');const route=url.pathname;
 let value;
 if(route==='/api/research/v1/transcripts')value={transcripts:[{transcript_id:'fixture-history',title:transcript.title,source_thread_id:transcript.thread_id,created_at:time,updated_at:time,message_count:3,tool_call_count:1,tool_output_count:1,proposal_id:'fixture-proposal'}]};
 else if(route==='/api/research/v1/transcripts/fixture-history')value={transcript_id:'fixture-history',imported_at:time,proposal_id:'fixture-proposal',transcript};
 else if(route==='/api/research/v1/research')value={research:[]};
 else if(route==='/api/research/v1/agents')value={agents:[]};
 else if(route==='/api/research/v1/page-plugins')value={plugins:[]};
 else if(route==='/api/research/v1/chats'&&init?.method==='POST')value=empty;
 else if(route==='/api/research/v1/chats')value={chats:[['fixture-chat','Scenario learning'],['matched-chat','Is matching a competitor offer worthwhile?'],['roe-chat','Understanding ROE']].map(([chat_id,title])=>({chat_id,title,created_at:time,updated_at:time,message_count:0}))};
 else if(route==='/api/research/v1/chats/fixture-chat/messages'){sends++;await new Promise(r=>setTimeout(r,1100));value=answer;}
 else if(route==='/api/research/v1/chats/fixture-chat/activity')value={events:[{name:'codex_complete',status:'running',elapsed_ms:200}],done:false};
 else if(route==='/api/research/v1/chats/fixture-chat')value=sends?answer:empty;
 else if(route==='/api/research/v1/proposals/fixture-proposal')value=proposal;
 else if(route==='/api/research/v1/documents'&&init?.method==='POST'){
  const body=JSON.parse(init.body);assert.equal(body.base_version,version);writes++;version++;proposal={...proposal,...body.content,updated_at:time};value={kind:'proposal',id:'fixture-proposal',version,content:content(),updated_at:time};
 }else if(route==='/api/research/v1/documents')value={kind:'proposal',id:'fixture-proposal',version,content:content(),updated_at:version?time:null};
 else if(route==='/api/research/v1/documents/history')value={versions:[{kind:'proposal',id:'fixture-proposal',version:0,content:Object.fromEntries(['title','question','hypothesis','plan'].map(k=>[k,source[k]])),updated_at:null},{kind:'proposal',id:'fixture-proposal',version,content:content(),updated_at:time}]};
 else throw Error('Unexpected fixture route');
 return new Response(JSON.stringify(value),{headers:{'Content-Type':'application/json'}});
};
const timer=setTimeout(()=>{console.error('Native chat check timed out');app.exit(1);},25000);
app.on('browser-window-created',(_event,win)=>{win.hide();win.webContents.on('console-message',(_event,level,message)=>{if(level>=2)console.error('Renderer:',message);});win.webContents.once('did-finish-load',async()=>{
 try{
  await win.webContents.executeJavaScript(`new Promise(resolve=>{const ready=()=>!document.querySelector('.systems').textContent.includes('READING');if(ready())return resolve();const o=new MutationObserver(()=>{if(ready()){o.disconnect();resolve();}});o.observe(document.querySelector('.systems'),{subtree:true,childList:true,characterData:true});})`);
  const results=await win.webContents.executeJavaScript(`(async()=>{
   const wait=predicate=>new Promise((resolve,reject)=>{if(predicate())return resolve();const timer=setTimeout(()=>{o.disconnect();reject(Error('Expected native chat state did not appear'));},7000);const o=new MutationObserver(()=>{if(predicate()){clearTimeout(timer);o.disconnect();resolve();}});o.observe(document.body,{childList:true,subtree:true,attributes:true,characterData:true});});
   [...document.querySelectorAll('nav button')].find(b=>b.textContent==='Codex').click();
   await wait(()=>document.querySelector('[data-chat-id=fixture-chat][aria-current=page]'));
   const sidebar=document.querySelectorAll('.codex-sidebar [data-chat-id]').length===4;
   const field=document.querySelector('.codex-message-composer textarea');field.value='Does scenario experience improve ROE?';field.dispatchEvent(new Event('input',{bubbles:true}));document.querySelector('.codex-message-composer').requestSubmit();
   await wait(()=>document.querySelector('.codex-live-activity li[data-status=running]'));
   const liveActivity=document.querySelector('.codex-live-activity').textContent.includes('codex_complete');
   await wait(()=>document.querySelector('.codex-proposal-attachment'));
   const savedActivity=document.querySelectorAll('.codex-message-assistant .codex-activity li').length;
   const attachment=document.querySelector('.codex-proposal-attachment');attachment.click();
   await wait(()=>document.querySelector('dialog[open]')&&!document.querySelector('.proposal-modal-edit').disabled);
   document.querySelector('.proposal-modal-edit').click();
   const noCaret=document.activeElement.tagName!=='TEXTAREA'&&document.activeElement.tagName!=='INPUT';
   const allEditable=[...document.querySelectorAll('dialog input,dialog textarea')].every(e=>!e.readOnly);
   const plan=document.querySelector('[name=plan]');plan.value='A reviewed fixture plan.';plan.dispatchEvent(new Event('input',{bubbles:true}));
   [...document.querySelectorAll('.proposal-modal-tabs button')].find(b=>b.textContent==='Plan').click();
   document.querySelector('.proposal-modal-save').click();
   await wait(()=>document.querySelector('.proposal-modal-status').textContent.includes('Version 1'));
   const title=document.querySelector('.codex-proposal-attachment strong').textContent;
   document.querySelector('.proposal-modal-close').click();
   document.querySelector('.codex-proposal-attachment').click();
   await wait(()=>document.querySelector('dialog[open]')&&!document.querySelector('.proposal-modal-edit').disabled);
   const reloaded=document.querySelector('[name=plan]').value;
   return {sidebar,liveActivity,savedActivity,noCaret,allEditable,title,reloaded,bridge:typeof window.semantic.chat,node:typeof window.require,tool:document.querySelector('.codex-message-assistant').textContent.includes('proposal_prepare')};
  })()`);
  assert.equal(results.sidebar,true);assert.equal(results.liveActivity,true);assert.equal(results.savedActivity,6);assert.equal(results.noCaret,true);assert.equal(results.allEditable,true);assert.equal(results.bridge,'function');assert.equal(results.node,'undefined');assert.equal(results.tool,true);assert.equal(results.reloaded,'A reviewed fixture plan.');assert.equal(sends,1);assert.equal(writes,1);
  const coord=async selector=>win.webContents.executeJavaScript(`(()=>{const r=document.querySelector(${JSON.stringify(selector)}).getBoundingClientRect();return {x:Math.round(r.left+r.width/2),y:Math.round(r.top+r.height/2)};})()`);
  const click=async p=>{win.webContents.sendInputEvent({type:'mouseMove',...p});win.webContents.sendInputEvent({type:'mouseDown',...p,button:'left',clickCount:1});win.webContents.sendInputEvent({type:'mouseUp',...p,button:'left',clickCount:1});await new Promise(r=>setTimeout(r,50));};
  const inside=await coord('[name=title]');await click(inside);
  assert.equal(await win.webContents.executeJavaScript("document.querySelector('dialog').open"),true);
  const backdrop=await win.webContents.executeJavaScript(`(()=>{const r=document.querySelector('dialog').getBoundingClientRect();return r.left>2?{x:1,y:1}:{x:Math.round(innerWidth-2),y:1};})()`);
  win.webContents.sendInputEvent({type:'mouseDown',...inside,button:'left',clickCount:1});win.webContents.sendInputEvent({type:'mouseMove',...backdrop,button:'left'});win.webContents.sendInputEvent({type:'mouseUp',...backdrop,button:'left',clickCount:1});
  assert.equal(await win.webContents.executeJavaScript("document.querySelector('dialog').open"),true);
  await click(await coord('.proposal-modal-edit'));
  await win.webContents.executeJavaScript(`(()=>{const f=document.querySelector('[name=title]');f.value+=' unsaved';f.dispatchEvent(new Event('input',{bubbles:true}));})()`);
  await click(backdrop);assert.equal(await win.webContents.executeJavaScript("document.querySelector('dialog').open"),true);
  assert.match(await win.webContents.executeJavaScript("document.querySelector('.proposal-modal-status').textContent"),/Unsaved changes/);
  await click(await coord('.proposal-modal-cancel'));
  await click(backdrop);assert.equal(await win.webContents.executeJavaScript("!document.querySelector('dialog[open]')"),true);
  const history=await win.webContents.executeJavaScript(`(async()=>{const wait=p=>new Promise((resolve,reject)=>{if(p())return resolve();const timer=setTimeout(()=>{o.disconnect();reject(Error('Historical transcript did not appear'));},7000);const o=new MutationObserver(()=>{if(p()){clearTimeout(timer);o.disconnect();resolve();}});o.observe(document.body,{childList:true,subtree:true,attributes:true});});document.querySelector('[data-chat-id="history:fixture-history"]').click();await wait(()=>document.querySelector('.codex-historical'));const groups=[...document.querySelectorAll('.codex-tool-group')];const closed=groups.length===1&&groups.every(g=>!g.open);groups[0].querySelector('summary').click();const call=document.querySelector('.codex-tool-record[data-record-type="tool_call"]');call.querySelector('summary').click();await wait(()=>call.querySelector('pre code'));return {readonly:!document.querySelector('.codex-message-composer'),strong:document.querySelector('.chat-markdown ul li strong')?.textContent,code:document.querySelector('.chat-markdown pre code')?.textContent,closed,args:call.querySelector('pre code').textContent};})()`);
  assert.equal(history.readonly,true);assert.equal(history.strong,'Agent:');assert.match(history.code,/SELECT roe/);assert.equal(history.closed,true);assert.match(history.args,/"query":"ROE"/);assert.equal(sends,1);assert.equal(writes,1);
  const shots=path.resolve(__dirname,'../../../var/codex-preview');fs.mkdirSync(shots,{recursive:true});
  await win.webContents.executeJavaScript(`document.querySelector('.codex-thread').scrollIntoView({block:'start'});new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));`);
  fs.writeFileSync(path.join(shots,'codex-chat.png'),(await win.webContents.capturePage()).toPNG());
  win.setMinimumSize(400,600);win.setSize(600,1000);await win.webContents.executeJavaScript('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))');
  assert.equal(await win.webContents.executeJavaScript('document.documentElement.scrollWidth<=innerWidth'),true);
  await win.webContents.executeJavaScript(`document.querySelector('.codex-proposal-attachment').click();new Promise(r=>setTimeout(r,150));`);
  const fit=await win.webContents.executeJavaScript(`(()=>{const d=document.querySelector('dialog').getBoundingClientRect(),h=document.querySelector('.proposal-modal-header').getBoundingClientRect(),f=document.querySelector('.proposal-modal-footer').getBoundingClientRect();return d.top>=0&&d.bottom<=innerHeight&&h.top>=d.top&&h.bottom<=d.bottom&&f.top>=d.top&&f.bottom<=d.bottom;})()`);
  assert.equal(fit,true);
  console.log('PASS: actual packaged chat IPC, live and saved operation activity, model-selected attachment, modal edit without autofocus, version save/reload, isolation, and narrow layout. Fixture only; no paid model call.');
  clearTimeout(timer);app.exit(0);
 }catch(error){console.error(error);clearTimeout(timer);app.exit(1);}
});});
require(path.resolve(__dirname,'../dist-electron/main.cjs'));

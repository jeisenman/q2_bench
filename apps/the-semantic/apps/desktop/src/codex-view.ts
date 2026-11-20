import {TranscriptListSchema,TranscriptRecordSchema,type TranscriptRecord,type TranscriptSummary} from '../../../packages/runtime/src/transcripts.js';
import {historicalTranscript} from './transcript-view.js';
import {renderChatMarkdown} from './chat-markdown.js';
import {chatDisplayText} from './chat-display.js';
import { type ChatActivity, ChatListSchema, ChatRecordSchema, type ChatRecord, type ChatRequest } from '../../../packages/runtime/src/chats.js';
import { ProposalRecordSchema } from '../../../packages/runtime/src/proposals.js';
import { read, chat } from './client.js';
import { el, button, utc } from './dom.js';
import { chatSidebar, type SidebarChat } from './chat-sidebar.js';
import { activityPanel, watchActivity } from './chat-activity.js';
import { revealReply } from './chat-animation.js';
import { openProposalModal } from './proposal-modal.js';

type Dependencies = { reader?: typeof read; sender?: typeof chat; openProposal?: typeof openProposalModal; animate?: typeof revealReply };
/** A durable research chat. Only explicit user messages request a Codex turn. */
export function createCodexView(deps: Dependencies = {}): { mount(host: HTMLElement): () => void } {
  const reader = deps.reader ?? read; const sender = deps.sender ?? chat;
  const openProposal = deps.openProposal ?? openProposalModal; const animate = deps.animate ?? revealReply;
  const root = el('section', '', 'codex-workspace');
  let record: ChatRecord | undefined; let summaries: SidebarChat[] = [];
  let historical:TranscriptRecord|undefined;let transcripts:TranscriptSummary[]=[];
  const previews=new Map<string,string>();
  let sidebarQuery='';
  let draft = ''; let pending = false; let optimistic = ''; let error = ''; let mounted = false;
  let generation = 0; let initialized = false; let stopAnimation = () => {}; let closeModal = () => {};
  let stopActivity=()=>{};let activity:ChatActivity|undefined;let activityUnavailable=false;let activityHost:HTMLElement|undefined;
  let createKey: string | undefined; let request: Extract<ChatRequest,{operation:'chats.send'}> | undefined;
  function render(animateID?: string): void {
    if (!mounted) return;
    stopAnimation(); stopAnimation = () => {}; root.replaceChildren();
    let beginAnimation: (() => void) | undefined;
    const heading = el('div', '', 'codex-chat-heading');
    heading.append(el('p','06 / CODEX','eyebrow'), el('h1','Work the question.'),
      el('p','Shape a question, review saved research, and prepare a proposal with Codex.','lead'));
    const layout=el('div','','codex-chat-layout');
    const activeID=historical?'history:'+historical.transcript_id:record?.chat_id;
    const chats=record&&!summaries.some(item=>item.chat_id===record!.chat_id)?[{chat_id:record.chat_id,title:record.title},...summaries]:summaries;
    const sidebarChats=chats.map(item=>({...item,preview:previews.get(item.chat_id),...(item.chat_id===record?.chat_id?{updated_at:record.updated_at,message_count:record.messages.length}:{} )}));
    sidebarChats.push(...transcripts.map(item=>({chat_id:'history:'+item.transcript_id,title:item.title,updated_at:item.updated_at,message_count:item.message_count,preview:`Historical · ${item.message_count} messages · ${item.tool_call_count} tool calls`})));
    layout.append(chatSidebar({chats:sidebarChats,currentID:activeID,pending,query:sidebarQuery,
      onQuery:value=>{sidebarQuery=value;},onOpen:id=>{void open(id);},onNew:startNew,onRefresh:()=>{void load();}}));
    root.append(heading,layout);
    const thread = el('section','','codex-thread');thread.setAttribute('aria-label','Codex conversation');
    const top=el('div','','codex-thread-heading');top.append(el('h2',chatDisplayText(historical?.transcript.title??record?.title??'A new question.')),el('span',historical?'Historical evidence':'Codex · gpt-6.1-sol','caption'));thread.append(top);
    if(historical){
      const status=el('p',error,error?'error':'caption');status.setAttribute('role','status');thread.append(status);
      thread.append(historicalTranscript(historical,(id,trigger)=>{void showProposal(id,trigger);}));layout.append(thread);return;
    }
    const messages=el('div','','codex-message-list');messages.setAttribute('aria-label','Chat messages');thread.append(messages);
    if(!record?.messages.length&&!optimistic)thread.append(el('p','Ask a research question. Codex can ask for a missing detail or prepare a draft when the scope is clear.','codex-empty'));
    for(const message of record?.messages??[]){
      const row=el('article','',`codex-message ${message.role==='user'?'codex-message-user':'codex-message-assistant'}`);
      row.dataset.messageId=message.id;
      row.append(el('span',message.role==='user'?'You':'Codex','codex-message-label'));
      const bubble=el('div','','codex-bubble');renderChatMarkdown(bubble,message.text);row.append(bubble);
      const attach=()=>{if(message.proposal_id)row.append(attachment(message.proposal_id));};
      if(message.id===animateID && message.role==='assistant') beginAnimation=()=>{stopAnimation=animate(bubble,chatDisplayText(message.text),()=>{if(mounted&&row.isConnected){renderChatMarkdown(bubble,message.text);attach();}});}; else attach();
      const evidence=el('details','','codex-message-evidence');evidence.append(el('summary',message.tool?'Prepared proposal · Tool evidence':'Message details'),el('p',utc(message.created_at),'caption'));
      if(message.tool)evidence.append(el('code',`${message.tool.name} · ${message.tool.status}`),el('p','A draft was saved. No research run was accepted.','caption'));
      row.append(evidence);if(message.activity?.length)row.append(activityPanel({events:message.activity,done:true}));messages.append(row);
    }
    if(optimistic){const user=el('article','','codex-message codex-message-user');user.append(el('span','You · Sending','codex-message-label'),el('p',chatDisplayText(optimistic),'codex-bubble'));thread.append(user);}
    if(pending){const typing=el('p','Codex is responding…','codex-typing');typing.setAttribute('role','status');thread.append(typing);activityHost=el('div','','codex-live-activity');activityHost.setAttribute('role','status');thread.append(activityHost);renderActivity();}
    const status=el('p',error,error?'error':'caption');status.setAttribute('role','status');thread.append(status);
    const form=el('form','','codex-message-composer');const input=el('textarea');input.value=draft;input.maxLength=16000;input.required=true;input.placeholder='Message Codex…';input.disabled=pending;input.rows=2;input.setAttribute('aria-label','Message Codex');
    input.oninput=()=>{draft=input.value;request=undefined;};
    const send=el('button',pending?'Responding…':'Send ↑','codex-message-send');send.type='submit';send.disabled=pending;
    input.onkeydown=event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing&&!pending){event.preventDefault();form.requestSubmit();}};
    form.append(input,send);form.onsubmit=event=>{event.preventDefault();void submit();};
    thread.append(form,el('p','Draft attachments are saved for review. Research execution requires a separately accepted plan.','codex-chat-footnote'));
    layout.append(thread);beginAnimation?.();
  }
  function remember(chat:ChatRecord):void{
    const last=chat.messages.at(-1);const preview=last?chatDisplayText(last.text).replace(/\s+/g,' ').trim().slice(0,160):undefined;
    if(preview)previews.set(chat.chat_id,preview);
  }
  function renderActivity():void{
    if(!activityHost?.isConnected&&!pending)return;
    activityHost?.replaceChildren();
    if(activity?.events.length)activityHost?.append(activityPanel(activity,true));
    if(activityUnavailable)activityHost?.append(el('p','Live activity is unavailable. The reply request is still pending.','caption'));
  }
  function startActivity():void{
    stopActivity();if(!mounted||!pending||!request)return;
    stopActivity=watchActivity(reader,request.id,request.idempotency_key,value=>{activity=value;activityUnavailable=value===undefined;renderActivity();});
  }
  function attachment(id:string): HTMLElement {
    const file=button('',()=>{void showProposal(id,file);},'codex-proposal-attachment');file.setAttribute('aria-haspopup','dialog');file.setAttribute('aria-label','Open saved research proposal');
    const icon=el('span','▤','codex-file-icon');icon.setAttribute('aria-hidden','true');
    const text=el('span','','codex-file-text');text.append(el('span','RESEARCH PROPOSAL','eyebrow'),el('strong','Question & plan'),el('span','Saved draft · Open to review','caption'));
    file.append(icon,text,el('span','↗','codex-file-arrow'));return file;
  }
  async function showProposal(id:string, trigger:HTMLButtonElement):Promise<void>{
    const current=generation;trigger.disabled=true;
    try{const proposal=ProposalRecordSchema.parse(await reader({operation:'proposals.get',id}));if(proposal.proposal_id!==id)throw Error('Proposal identity mismatch.');if(!mounted||current!==generation)return;
      closeModal();closeModal=openProposal(proposal,saved=>{trigger.querySelector('strong')!.textContent=chatDisplayText(saved.title);},{reader});
    }catch{if(mounted){error='Cannot open the saved proposal. Refresh and try again.';render();}}
    finally{trigger.disabled=false;}
  }
  function startNew():void{
    if(pending)return;if(draft.trim()&&!root.ownerDocument.defaultView!.confirm('Discard the unsent message?'))return;
    generation++;initialized=true;record=undefined;historical=undefined;draft='';request=undefined;createKey=undefined;error='';render();
  }
  async function open(id:string):Promise<void>{
    if(pending||record?.chat_id===id||historical&&'history:'+historical.transcript_id===id)return;if(draft.trim()&&!root.ownerDocument.defaultView!.confirm('Discard the unsent message?'))return;
    const current=++generation;
    try{if(id.startsWith('history:')){const identity=id.slice(8);const next=TranscriptRecordSchema.parse(await reader({operation:'transcripts.get',id:identity}));if(next.transcript_id!==identity)throw Error('Transcript identity mismatch.');if(current!==generation)return;historical=next;initialized=true;record=undefined;draft='';request=undefined;createKey=undefined;error='';render();return;}
      const next=ChatRecordSchema.parse(await reader({operation:'chats.get',id}));if(next.chat_id!==id)throw Error('Chat identity mismatch.');if(current!==generation)return;record=next;initialized=true;historical=undefined;remember(next);draft='';request=undefined;createKey=undefined;error='';render();}
    catch{if(current===generation){error='Cannot read this conversation. Your current text is retained.';render();}}
  }
  async function load():Promise<void>{
    if(pending)return;const current=++generation;
    try{const [rawChats,rawTranscripts]=await Promise.all([reader({operation:'chats.list',order:'newest'}),reader({operation:'transcripts.list'})]);const list=ChatListSchema.parse(rawChats);const catalog=TranscriptListSchema.parse(rawTranscripts);if(current!==generation)return;summaries=list.chats;transcripts=catalog.transcripts;previews.clear();
      if(historical){const next=TranscriptRecordSchema.parse(await reader({operation:'transcripts.get',id:historical.transcript_id}));if(next.transcript_id!==historical.transcript_id)throw Error('Transcript identity mismatch.');if(current!==generation)return;historical=next;error='';render();return;}
      const requested=!initialized?new URL(root.ownerDocument.defaultView!.location.href).searchParams.get('transcript'):null;
      if(requested){await open('history:'+requested);return;}
      const id=record?.chat_id??(!initialized?list.chats[0]?.chat_id:undefined);initialized=true;
      if(id){const next=ChatRecordSchema.parse(await reader({operation:'chats.get',id}));if(next.chat_id!==id)throw Error('Chat identity mismatch.');if(current!==generation)return;record=next;remember(next);}
      error='';render();
    }catch{if(current===generation){initialized=true;error='The chat service is unavailable. Check the local research API, then Refresh.';render();}}
  }
  async function submit():Promise<void>{
    const text=draft.trim();if(pending||!text)return;
    if(text.length>16000){error='Messages must contain at most 16,000 characters.';render();return;}
    generation++;pending=true;optimistic=text;error='';activity=undefined;activityUnavailable=false;render();
    try{
      if(!record){createKey??=crypto.randomUUID();record=ChatRecordSchema.parse(await sender({operation:'chats.create',title:text.slice(0,1000),idempotency_key:createKey}));}
      request??={operation:'chats.send',id:record.chat_id,message:text,base_version:record.version,idempotency_key:crypto.randomUUID()};
      startActivity();
      const next=ChatRecordSchema.parse(await sender(request));if(next.chat_id!==record.chat_id||next.version!==request.base_version+1||next.messages.at(-2)?.text!==request.message)throw Error('Chat response mismatch.');
      stopActivity();record=next;remember(next);summaries=[{chat_id:next.chat_id,title:next.title,updated_at:next.updated_at,message_count:next.messages.length},...summaries.filter(item=>item.chat_id!==next.chat_id)];draft='';request=undefined;createKey=undefined;optimistic='';pending=false;
      const last=record.messages.at(-1);render(last?.role==='assistant'?last.id:undefined);
    }catch{stopActivity();pending=false;optimistic='';error='Codex could not complete this message. Your text is retained. Retry unchanged to resolve the same request; no automatic retry was made.';render();}
  }
  return {mount(host){mounted=true;host.append(root);render();if(!pending)void load();else startActivity();return()=>{mounted=false;generation++;stopActivity();stopAnimation();closeModal();root.remove();};}};
}

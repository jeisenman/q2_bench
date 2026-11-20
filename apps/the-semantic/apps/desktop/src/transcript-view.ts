import type {TranscriptRecord} from '../../../packages/runtime/src/transcripts.js';
import {el,button,utc} from './dom.js';
import {renderChatMarkdown} from './chat-markdown.js';
import {chatDisplayText} from './chat-display.js';
type Item=TranscriptRecord['transcript']['items'][number];
const toolText=(value:string|{text:string}[])=>typeof value==='string'?value:value.map(part=>part.text).join('\n');
const truncated=(text:string)=>/Warning: truncated output|\d+ tokens truncated/i.test(text);
/** Show immutable source messages and grouped recorded tools without executing them. */
export function historicalTranscript(record:TranscriptRecord,onProposal:(id:string,trigger:HTMLButtonElement)=>void):HTMLElement{
  const source=record.transcript;const root=el('section','','codex-historical');
  const messages=source.items.filter(item=>item.type==='message').length;
  const calls=new Map(source.items.filter(item=>item.type==='tool_call').map(item=>[item.call_id,item]));
  const outputCount=source.items.filter(item=>item.type==='tool_output').length;
  const truncations=source.items.filter(item=>item.type==='tool_output'&&truncated(toolText(item.output))).length;
  root.append(el('p',`Historical conversation · ${messages} messages · ${calls.size} tool calls · ${outputCount} outputs`,'caption'));
  const toolbar=el('div','','codex-transcript-toolbar');const select=el('select');select.setAttribute('aria-label','Transcript records');
  for(const [value,label] of [['all','Full conversation + tool records'],['messages','Messages only'],['tools','Tool calls + outputs only']]){const option=el('option',label);option.value=value!;select.append(option);}
  const scroll=el('div','','codex-transcript-scroll');scroll.setAttribute('aria-label','Recorded conversation');
  const latest=button('Jump to latest ↓',()=>{scroll.scrollTop=scroll.scrollHeight;});toolbar.append(select,latest);root.append(toolbar,scroll);
  function render():void{
    scroll.replaceChildren();let batch:{item:Item;node:HTMLElement}[]=[];
    function flush():void{
      if(!batch.length)return;const count=batch.filter(value=>value.item.type==='tool_call').length;
      const results=new Set(batch.flatMap(value=>'call_id' in value.item?[value.item.call_id]:[])).size;
      const group=el('details','','codex-tool-group');group.append(el('summary',count?`${count} tool ${count===1?'call':'calls'}`:`${results} tool ${results===1?'result':'results'}`));
      const body=el('div','','codex-tool-group-body');for(const value of batch)body.append(value.node);group.append(body);scroll.append(group);batch=[];
    }
    source.items.forEach((item,index)=>{
      if(item.type==='message')flush();
      if(select.value==='messages'&&item.type!=='message'||select.value==='tools'&&item.type==='message')return;
      if(item.type==='message'){
        const row=el('article','',`codex-message codex-message-${item.role}`);row.dataset.sourceIndex=String(index);
        const bubble=el('div','','codex-bubble');renderChatMarkdown(bubble,item.content.map(part=>part.text).join('\n'));
        row.append(el('span',`${item.role==='user'?'You':'Codex'} · ${utc(item.timestamp)}`,'codex-message-label'),bubble);scroll.append(row);return;
      }
      const call=item.type==='tool_call'?item:calls.get(item.call_id);const details=el('details','','codex-tool-record');details.dataset.sourceIndex=String(index);details.dataset.recordType=item.type;
      details.append(el('summary',`${chatDisplayText(call?.name??'Recorded tool')} · ${item.type==='tool_call'?'Call':'Output'}`),el('p',utc(item.timestamp),'caption'));
      const text=chatDisplayText(item.type==='tool_call'?item.arguments:toolText(item.output));
      if(item.type==='tool_output'&&truncated(text))details.append(el('p','This output was truncated in the original record.','caption'));
      let loaded=false;details.addEventListener('toggle',()=>{if(!details.open||loaded)return;loaded=true;const pre=el('pre');pre.append(el('code',text));details.append(pre);});
      batch.push({item,node:details});
    });flush();
  }
  select.onchange=render;render();
  if(record.proposal_id){const id=record.proposal_id;const attachment=button('',()=>onProposal(id,attachment),'codex-proposal-attachment');attachment.setAttribute('aria-haspopup','dialog');attachment.setAttribute('aria-label','Open saved research proposal');const text=el('span','','codex-file-text');text.append(el('span','SAVED RESEARCH PROPOSAL','eyebrow'),el('strong','Question & plan'),el('span','Open current version','caption'));attachment.append(el('span','▤','codex-file-icon'),text,el('span','↗','codex-file-arrow'));root.append(attachment);}
  const evidence=el('details','','codex-transcript-evidence');evidence.append(el('summary','Source conversation & limits'),el('p',chatDisplayText(source.title)),el('p',chatDisplayText(source.description)),el('p',`Imported ${utc(record.imported_at)}. ${truncations} captured outputs contain original truncation markers. Private reasoning, system/developer instructions, and non-text media are excluded.`));root.append(evidence,el('p','Historical evidence is read-only. New conversation starts a separate live chat; recorded commands are never executed.','codex-chat-footnote'));
  return root;
}

import { ChatActivitySchema, type ChatActivity } from '../../../packages/runtime/src/chats.js';
import type { ReadRequest } from './api.js';
import { el } from './dom.js';

const labels = {
  agent_get:'Read hypothesis definition', research_list:'Review saved research',
  proposal_list:'Review saved proposals', codex_complete:'Request Codex reply',
  proposal_prepare:'Save proposal draft', chat_save:'Write conversation snapshot',
};
/** Render only observed public operations, without private reasoning or payloads. */
export function activityPanel(activity: ChatActivity, live = false): HTMLDetailsElement {
  const panel = el('details','','codex-activity'); panel.open=live;
  panel.append(el('summary',live?'Working · Operations':`${activity.events.length} operations · View activity`));
  const list=el('ol');
  for(const event of activity.events){
    const row=el('li');row.dataset.status=event.status;
    const mark=event.status==='completed'?'✓':event.status==='failed'?'!':'◌';
    row.append(el('span',`${mark} ${labels[event.name]}`),el('span',`${event.status} · ${(event.elapsed_ms/1000).toFixed(1)}s`,'caption'));
    const evidence=el('code',event.name);row.append(evidence);list.append(row);
  }
  panel.append(list);return panel;
}
/** Poll one existing turn. This read path cannot start or retry a model call. */
export function watchActivity(
  reader:(request:ReadRequest)=>Promise<unknown>, id:string, key:string,
  update:(activity:ChatActivity|undefined)=>void,
):()=>void{
  let stopped=false;let timer:ReturnType<typeof setTimeout>|undefined;
  const deadline=Date.now()+200000;
  async function poll():Promise<void>{
    try{
      const value=ChatActivitySchema.parse(await reader({operation:'chats.activity',id,key}));
      if(stopped)return;update(value);
      if(!value.done && Date.now()<deadline)timer=setTimeout(()=>{void poll();},750);
    }catch{if(!stopped)update(undefined);}
  }
  void poll();
  return()=>{stopped=true;if(timer!==undefined)clearTimeout(timer);};
}

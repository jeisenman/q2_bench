import { button, el, utc } from './dom.js';

export type SidebarChat = {chat_id:string;title:string;updated_at?:string;message_count?:number;preview?:string};
type Options = {
  chats:SidebarChat[]; currentID?:string; pending:boolean; query:string;
  onQuery:(value:string)=>void; onOpen:(id:string)=>void;
  onNew:()=>void; onRefresh:()=>void;
};
/** Build the themed saved-chat navigation using finite existing chat reads. */
export function chatSidebar(options:Options):HTMLElement {
  const sidebar=el('aside','','codex-sidebar');sidebar.setAttribute('aria-label','Chat sidebar');
  const header=el('div','','codex-sidebar-heading');
  header.append(el('p','YOUR WORKSPACE','eyebrow'),el('h2','Conversations'));
  const fresh=button('+ New conversation',options.onNew,'codex-new-chat');fresh.disabled=options.pending;
  if(!options.currentID)fresh.setAttribute('aria-current','page');
  const search=el('input','','codex-chat-search');search.type='search';search.placeholder='Search chats';search.value=options.query;search.setAttribute('aria-label','Search chats');
  const list=el('div','','codex-chat-list');list.setAttribute('role','navigation');list.setAttribute('aria-label','Saved conversations');
  function filter():void{
    list.replaceChildren();const query=search.value.trim().toLocaleLowerCase();
    const matches=options.chats.filter(chat=>chat.title.toLocaleLowerCase().includes(query));
    for(const chat of matches){
      const item=button('',()=>options.onOpen(chat.chat_id),'codex-chat-item');item.disabled=options.pending;item.dataset.chatId=chat.chat_id;item.title=chat.title;
      if(chat.chat_id===options.currentID)item.setAttribute('aria-current','page');
      const initials=chat.title.trim().split(/\s+/).slice(0,2).map(word=>Array.from(word)[0]).join('').toLocaleUpperCase();
      const icon=el('span',initials,'codex-chat-icon');icon.setAttribute('aria-hidden','true');
      const content=el('span','','codex-chat-content');const top=el('span','','codex-chat-row-heading');
      top.append(el('span',chat.title,'codex-chat-title'));
      if(chat.updated_at){const date=el('time',new Date(chat.updated_at).toLocaleDateString('en-US',{month:'short',day:'numeric',timeZone:'UTC'}),'codex-chat-date');date.dateTime=chat.updated_at;date.title=utc(chat.updated_at);top.append(date);}
      const preview=chat.preview??(chat.message_count===0?'Start the conversation':chat.message_count?`${chat.message_count} messages · Open conversation`:'Open conversation');
      content.append(top,el('span',preview,'codex-chat-preview'));
      const arrow=el('span','›','codex-chat-chevron');arrow.setAttribute('aria-hidden','true');
      item.append(icon,content,arrow);list.append(item);
    }
    if(!matches.length)list.append(el('p',query?'No matching chats.':'Your saved chats will appear here.','codex-sidebar-empty'));
  }
  search.oninput=()=>{options.onQuery(search.value);filter();};filter();
  const footer=el('div','','codex-sidebar-footer');const refresh=button('Refresh ↻',options.onRefresh);refresh.disabled=options.pending;
  footer.append(el('span',`${options.chats.length} saved ${options.chats.length===1?'chat':'chats'}`,'caption'),refresh);
  sidebar.append(header,fresh,search,list,footer);return sidebar;
}

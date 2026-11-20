import { chatDisplayText } from './chat-display.js';

/** Render a bounded Markdown subset as inert DOM, without HTML or network loads. */
export function renderChatMarkdown(host:HTMLElement,text:string):void {
  text=chatDisplayText(text);
  const doc=host.ownerDocument;const fragment=doc.createDocumentFragment();
  host.classList.add('chat-markdown');
  function inline(parent:Node,value:string,depth=0):void{
    if(depth>=8){parent.appendChild(doc.createTextNode(value));return;}
    const pattern=/(`+)([^`\n]+)\1|\*\*([^\n]+?)\*\*|__([^\n]+?)__|\*([^*\n]+)\*/g;
    let cursor=0;let match:RegExpExecArray|null;
    while((match=pattern.exec(value))!==null){
      parent.appendChild(doc.createTextNode(value.slice(cursor,match.index)));
      const node=doc.createElement(match[1]?'code':match[3]||match[4]?'strong':'em');
      if(match[1])node.textContent=match[2]!;else inline(node,match[3]??match[4]??match[5]!,depth+1);
      parent.appendChild(node);cursor=pattern.lastIndex;
    }
    parent.appendChild(doc.createTextNode(value.slice(cursor)));
  }
  const lines=text.replace(/\r\n?/g,'\n').split('\n');let index=0;
  const block=(line:string)=>/^\s*(?:`{3,}|~{3,}|#{1,6}\s|>\s?|[-+*]\s+|\d+[.)]\s+)/.test(line);
  while(index<lines.length){
    const line=lines[index]!;if(!line.trim()){index++;continue;}
    const fence=line.match(/^\s*(`{3,}|~{3,})([^\n]*)$/);
    if(fence){
      index++;const code:string[]=[];while(index<lines.length&&!lines[index]!.trim().startsWith(fence[1]!))code.push(lines[index++]!);
      if(index<lines.length)index++;
      const pre=doc.createElement('pre');const content=doc.createElement('code');content.textContent=code.join('\n');
      const language=fence[2]!.trim();if(language)pre.dataset.language=language;
      pre.append(content);fragment.append(pre);continue;
    }
    const heading=line.match(/^\s*(#{1,6})\s+(.+)$/);
    if(heading){const node=doc.createElement(`h${Math.min(6,heading[1]!.length+1)}`);inline(node,heading[2]!);fragment.append(node);index++;continue;}
    const item=line.match(/^\s*(?:([-+*])|(\d+)[.)])\s+(.+)$/);
    if(item){
      const ordered=!!item[2];const list=doc.createElement(ordered?'ol':'ul');if(ordered)(list as HTMLOListElement).start=Number(item[2]);
      while(index<lines.length){const next=lines[index]!.match(/^\s*(?:([-+*])|(\d+)[.)])\s+(.+)$/);if(!next||!!next[2]!==ordered)break;
        const li=doc.createElement('li');inline(li,next[3]!);list.append(li);index++;
      }
      fragment.append(list);continue;
    }
    if(/^\s*>/.test(line)){
      const quote=doc.createElement('blockquote');const rows:string[]=[];
      while(index<lines.length&&/^\s*>/.test(lines[index]!))rows.push(lines[index++]!.replace(/^\s*>\s?/,''));
      inline(quote,rows.join('\n'));fragment.append(quote);continue;
    }
    const paragraph=doc.createElement('p');const rows=[line];index++;
    while(index<lines.length&&lines[index]!.trim()&&!block(lines[index]!))rows.push(lines[index++]!);
    inline(paragraph,rows.join('\n'));fragment.append(paragraph);
  }
  host.replaceChildren(fragment);
}

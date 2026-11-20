import { HelpArticleSchema, HelpListSchema, type HelpArticle } from './help-contracts.js';
import { el,button,utc } from './dom.js';
import type { ReadRequest } from './api.js';
import { read } from './client.js';
export interface HelpState { query:string;source:'snapshot'|'public'; selected?:HelpArticle }
/** Reads only public Help Center knowledge, with explicit scope and safe plain text. */
export function mountHelp(host:HTMLElement,state:HelpState,reader:typeof read=read):()=>void {
  let disposed=false;let generation=0;
  const note=el('p',state.source==='snapshot'?'Retained Zendesk export snapshot. This dated knowledge corpus is not a live Zendesk connection.':'Live Public Help Center. Publicly accessible articles only; protected support content is not included.','session-notice');
  const boundary=el('p','Knowledge references are not SME-approved lineage definitions. No article-to-lineage mapping is implied.','caption');
  const source=el('select');source.setAttribute('aria-label','Knowledge source');
  for(const [value,label] of [['snapshot','Zendesk export snapshot'],['public','Live public Help Center']]){const option=el('option',label);option.value=value!;source.append(option);}source.value=state.source;
  source.onchange=()=>{state.source=source.value as HelpState['source'];state.selected=undefined;note.textContent=state.source==='snapshot'?'Retained Zendesk export snapshot. This dated corpus is not a live Zendesk connection.':'Live Public Help Center. Publicly accessible articles only; protected support content is not included.';void load();};
  const form=el('form','','toolbar');const input=el('input');input.type='search';input.value=state.query;input.maxLength=200;input.placeholder='Search article titles and text';input.setAttribute('aria-label','Search knowledge articles');
  const submit=el('button','Search','refresh');submit.type='submit';const latest=button('Latest articles',()=>{input.value='';state.query='';void load();},'refresh');form.append(source,input,submit,latest);
  const status=el('p','','caption');status.setAttribute('aria-live','polite');const content=el('div','','help-content');host.append(note,boundary,form,status,content);
  function show(article:HelpArticle):void {
    state.selected=article;const body=el('article','','help-article');body.append(el('h2',article.title),el('p',`Updated ${utc(article.updated_at)} · ${article.snapshot?'Retained export snapshot':'Public Help Center'}`,'caption'));
    const link=el('a','Read the source article ↗');link.href=article.url;link.target='_blank';link.rel='noreferrer noopener';body.append(link,el('p',article.text??'No article body is publicly available.','pre-line'));
    if(article.snapshot)body.append(el('p',`Export completed ${utc(article.snapshot.completed_at)} · ${article.snapshot.article_count} retained articles`,'caption'));
    content.replaceChildren(button('← Article results',()=>{state.selected=undefined;void load();},'back'),body);
  }
  async function loadArticle(id:number):Promise<void>{
    const current=++generation;status.textContent=state.source==='snapshot'?'Reading retained export article…':'Reading public article…';
    try{const article=HelpArticleSchema.parse(await reader({operation:state.source==='snapshot'?'knowledge.article':'help.article',id}));if(disposed||current!==generation)return;show(article);status.textContent=state.source==='snapshot'?'Retained export article. Export and article dates are shown below.':'Public article snapshot. Source date is shown below.';}
    catch{if(!disposed&&current===generation)status.textContent=state.source==='snapshot'?'Retained export article unavailable. The previous snapshot is unchanged.':'Public article unavailable. The previous result is not a live view.';}
  }
  async function load():Promise<void>{
    const current=++generation;status.textContent=state.source==='snapshot'?'Reading configured Zendesk export…':'Reading Public Help Center…';content.replaceChildren();
    try{
      const request:ReadRequest=state.query?{operation:state.source==='snapshot'?'knowledge.search':'help.search',query:state.query}:{operation:state.source==='snapshot'?'knowledge.list':'help.list'};
      const result=HelpListSchema.parse(await reader(request));
      if(disposed||current!==generation)return;
      status.textContent=`${result.articles.length} of ${result.count} ${state.source==='snapshot'?'snapshot':'public'} ${state.query?'search results':'articles'} shown${result.has_more?' · Refine the search to read more.':'.'}${result.snapshot?` Export completed ${utc(result.snapshot.completed_at)}; ${result.snapshot.article_count} total retained articles.`:''}`;
      if(!result.articles.length)content.append(el('p','No articles from this selected knowledge source match the search. This result does not describe other sources.','empty'));
      for(const article of result.articles){const row=button('',()=>{void loadArticle(article.id);},'question-row');row.append(el('h3',article.title),el('p',`Updated ${utc(article.updated_at)}`,'caption'));content.append(row);}
    }catch{if(!disposed&&current===generation){status.textContent=state.source==='snapshot'?'Configured Zendesk export unavailable.':'Public Help Center unavailable.';content.append(el('p',state.source==='snapshot'?'The configured read-only export could not be read. No other knowledge source was substituted.':'The public knowledge service could not be read with a trusted HTTPS connection. Refresh or check the service connection.','error'));}}
  }
  form.onsubmit=e=>{e.preventDefault();state.query=input.value.trim();state.selected=undefined;void load();};
  if(state.selected){show(state.selected);status.textContent=state.source==='snapshot'?'Previously read export article. Its export date is shown below.':'Previously read public article snapshot. Use the source link for the current article.';}else void load();
  return()=>{disposed=true;generation++;};
}

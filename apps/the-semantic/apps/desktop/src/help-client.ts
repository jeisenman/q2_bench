import { z } from 'zod';
import { parseFragment, type DefaultTreeAdapterMap } from 'parse5';
import { HelpRequestSchema, HelpArticleSchema, HelpListSchema, helpPath, type HelpRequest } from './help-contracts.js';
import { boundedJSON, type ReadFetch } from './bounded-json.js';
const RawArticle=z.object({id:z.number(),title:z.string(),html_url:z.string(),updated_at:z.string(),locale:z.string(),body:z.string().max(2_000_000).nullable()});
/** Parses inert HTML syntax into text without executing or loading document resources. */
export function articleText(html:string):string {
  const root=parseFragment(html);let visited=0;const output:string[]=[];
  const walk=(node:DefaultTreeAdapterMap['node']):void=>{
    if(++visited>100000)throw new Error('Article markup exceeds the supported complexity.');
    if(node.nodeName==='#text'){output.push((node as DefaultTreeAdapterMap['textNode']).value);return;}
    if('tagName'in node&&['script','style','noscript','template','iframe','svg','form'].includes(node.tagName))return;
    if('childNodes'in node){for(const child of node.childNodes)walk(child);}
    if('tagName'in node&&['p','div','br','li','h1','h2','h3','h4','tr','section'].includes(node.tagName))output.push('\n');
  };
  walk(root);const result=output.join('').replace(/[ \t]+/g,' ').replace(/\n[ \t]+/g,'\n').replace(/\n{3,}/g,'\n\n').trim();
  if(result.length>1_000_000)throw new Error('Article text exceeds the supported size.');return result;
}
function normalize(raw:unknown){const a=RawArticle.parse(raw);return HelpArticleSchema.parse({id:a.id,title:a.title,url:a.html_url,updated_at:a.updated_at,locale:a.locale,text:a.body===null?null:articleText(a.body)});}
/** Reads public articles from one fixed HTTPS host with normal certificate verification. */
export async function readHelpCenter(raw:HelpRequest,fetcher?:ReadFetch):Promise<unknown>{
  const request=HelpRequestSchema.parse(raw);
  const data=await boundedJSON('https://support.precisionlender.com'+helpPath(request),fetcher,16_000_000);
  if(request.operation==='help.article'){
    const article=normalize(z.object({article:RawArticle}).parse(data).article);
    if(article.id!==request.id)throw new Error('Help Center returned a different article.');return article;
  }
  const envelope=z.object({articles:z.array(RawArticle).max(25).optional(),results:z.array(RawArticle).max(25).optional(),count:z.number().int().nonnegative(),next_page:z.string().nullable()}).parse(data);
  const articles=request.operation==='help.list'?envelope.articles:envelope.results;
  if(!articles)throw new Error('Help Center returned an invalid article list.');
  return HelpListSchema.parse({articles:articles.map(normalize),count:envelope.count,has_more:envelope.next_page!==null});
}

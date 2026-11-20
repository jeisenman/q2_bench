import { nodeKey, nodeLabel, type NodeID } from './lineage-contracts.js';
import type { Neighborhood } from './lineage-graph.js';
import {lineageTitle} from './lineage-label.js';
const ns='http://www.w3.org/2000/svg';
function svg<K extends keyof SVGElementTagNameMap>(tag:K,attrs:Record<string,string>={}):SVGElementTagNameMap[K]{const n=document.createElementNS(ns,tag);for(const [k,v]of Object.entries(attrs))n.setAttribute(k,v);return n;}
/** Renders original directed evidence edges with keyboard-selectable source nodes. */
export function graphSVG(part:Neighborhood,selected:NodeID,onSelect:(id:NodeID)=>void):SVGSVGElement {
  const key=nodeKey(selected);const incoming=new Set(part.edges.filter(e=>nodeKey(e.target)===key).map(e=>nodeKey(e.source)));
  const left=part.nodes.filter(n=>nodeKey(n.id)!==key&&incoming.has(nodeKey(n.id)));
  const right=part.nodes.filter(n=>nodeKey(n.id)!==key&&!incoming.has(nodeKey(n.id)));
  const height=Math.max(300,Math.max(left.length,right.length)*90+80);const positions=new Map<string,{x:number;y:number}>();
  positions.set(key,{x:460,y:height/2});left.forEach((n,i)=>positions.set(nodeKey(n.id),{x:150,y:70+i*90}));right.forEach((n,i)=>positions.set(nodeKey(n.id),{x:770,y:70+i*90}));
  const root=svg('svg',{viewBox:`0 0 920 ${height}`,role:'img','aria-label':'Directed one-hop lineage subset'});
  const defs=svg('defs');const marker=svg('marker',{id:'lineage-arrow',viewBox:'0 0 10 10',refX:'9',refY:'5',markerWidth:'7',markerHeight:'7',orient:'auto-start-reverse'});
  marker.append(svg('path',{d:'M 0 0 L 10 5 L 0 10 z',fill:'#9a4329'}));defs.append(marker);root.append(defs);
  for(const edge of part.edges){const a=positions.get(nodeKey(edge.source))!;const b=positions.get(nodeKey(edge.target))!;
    const sign=b.x>=a.x?1:-1;const line=svg('line',{x1:String(a.x+sign*100),y1:String(a.y),x2:String(b.x-sign*105),y2:String(b.y),stroke:'#9a4329','stroke-width':'1.3','marker-end':'url(#lineage-arrow)'});
    const title=svg('title');title.textContent=`${nodeLabel(edge.source)} → ${nodeLabel(edge.target)} · ${edge.kind}`;line.append(title);root.append(line);
  }
  for(const node of part.nodes){const p=positions.get(nodeKey(node.id))!;const active=nodeKey(node.id)===key;
    const group=svg('g',{role:'button',tabindex:'0','aria-label':nodeLabel(node.id),class:'lineage-svg-node'});const title=svg('title');title.textContent=nodeLabel(node.id);
    group.append(title,svg('rect',{x:String(p.x-105),y:String(p.y-29),width:'210',height:'58',fill:active?'#eee9dc':'#fbf9f3',stroke:active?'#9a4329':'#c9c6bb'}));
    const label=svg('text',{x:String(p.x),y:String(p.y-3),'text-anchor':'middle',fill:'#22231f','font-size':'12'});const value=lineageTitle(node.id);label.textContent=value.length>27?value.slice(0,26)+'…':value;
    const kind=svg('text',{x:String(p.x),y:String(p.y+15),'text-anchor':'middle',fill:'#69685f','font-size':'9'});kind.textContent=node.job?'JOB':node.dataset?'DATASET':'COLUMN';group.append(label,kind);
    group.onclick=()=>onSelect(node.id);group.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();onSelect(node.id);}};root.append(group);
  }return root;
}

import test from 'node:test';
import assert from 'node:assert/strict';
import {JSDOM} from 'jsdom';
import {LineageGraphSchema,ExplanationSchema,nodePath,nodeKey,type LineageGraph,type LineageNode} from '../src/lineage-contracts.js';
import {lineageOrigin,lineageRequestFromPath,readLineage} from '../src/lineage-client.js';
import {neighborhood} from '../src/lineage-graph.js';
import {graphSVG} from '../src/lineage-svg.js';
import {mountSemantic,type SemanticState} from '../src/semantic-view.js';
import {route,ReadSchema} from '../src/api.js';
const node=(name:string):LineageNode=>({id:{namespace:'q2://fixture/data',name},dataset:{},facets:{meaning:{}}});
const a=node('upstream/a');const b=node('selected#b');const c=node('downstream c');
const graph:LineageGraph={nodes:[a,b,c],edges:[{source:a.id,target:b.id,kind:'consumes'},{source:b.id,target:c.id,kind:'produces'}],aliases:[],unresolved:['Synthetic scoped coverage is incomplete.']};
const settle=()=>new Promise<void>(resolve=>setImmediate(resolve));
test('full lineage validation, nil slices, nested wire escaping and finite routes',()=>{
 assert.deepEqual(LineageGraphSchema.parse(graph),graph);
 assert.deepEqual(LineageGraphSchema.parse({nodes:null,edges:null,aliases:null,unresolved:null}),{nodes:[],edges:[],aliases:[],unresolved:[]});
 const id={namespace:'q2://fixture/a?b',name:'a/b#c%',column:'strange / # column'};
 const path=nodePath(id);assert.ok(path.includes('%252F'));assert.deepEqual(lineageRequestFromPath(path),{operation:'lineage.node',id});
 assert.equal(route({operation:'lineage.node',id}),path);
 for(const value of [{operation:'lineage.formal',id},{operation:'lineage.graph',url:'http://evil'},{operation:'lineage.node',id:{namespace:' x',name:'a'}}])assert.equal(ReadSchema.safeParse(value).success,false);
 assert.throws(()=>LineageGraphSchema.parse({...graph,nodes:[a,a]}));
 assert.throws(()=>LineageGraphSchema.parse({...graph,nodes:[a,b]}));
 assert.throws(()=>LineageGraphSchema.parse({...graph,nodes:[{...a,job:{}}]}));
 for(const origin of ['https://example.com','http://127.0.0.1:7420/path','http://user:secret@localhost:7420','http://127.0.0.1:7420?url=x'])assert.throws(()=>lineageOrigin(origin));
 assert.equal(lineageOrigin('http://localhost:7420'),'http://localhost:7420');
 for(const path of ['/node/invalid','/graph?version=stale','/definitions/draft','/node/a/formal'])assert.throws(()=>lineageRequestFromPath(path));
});
test('one-hop graph preserves declared direction, excludes indirect nodes, and reports truncation',()=>{
 const extra=node('indirect');const g={...graph,nodes:[...graph.nodes,extra],edges:[...graph.edges,{source:c.id,target:extra.id,kind:'produces'}]};
 const part=neighborhood(g,b.id);assert.deepEqual(part.nodes,[b,a,c]);assert.deepEqual(part.edges,graph.edges);
 const many={nodes:[b,...Array.from({length:50},(_,i)=>node(`input-${i}`))],edges:[]as LineageGraph['edges'],aliases:[],unresolved:[]};
 many.edges=many.nodes.slice(1).map(n=>({source:n.id,target:b.id,kind:'consumes'}));
 const limited=neighborhood(many,b.id);assert.equal(limited.nodes.length,40);assert.equal(limited.candidateNodes,51);assert.equal(limited.edges.length,39);assert.equal(limited.candidateEdges,50);
 assert.equal(neighborhood({...graph,edges:Array.from({length:90},()=>graph.edges[0]!)},b.id).edges.length,80);
 assert.throws(()=>neighborhood(graph,b.id,0));
 const dom=new JSDOM('<main></main>');Object.assign(globalThis,{document:dom.window.document});let selected='';const svg=graphSVG(part,b.id,id=>{selected=nodeKey(id);});
 assert.match(svg.querySelector('line title')!.textContent!,/upstream\/a → selected#b · consumes/);
 assert.equal(svg.querySelector('line')!.getAttribute('marker-end'),'url(#lineage-arrow)');assert.ok([...svg.querySelectorAll('g text')].some(text=>text.textContent==='A'));assert.ok(![...svg.querySelectorAll('g text')].some(text=>text.textContent==='upstream/a'));
 svg.querySelector<SVGGElement>('g')!.dispatchEvent(new dom.window.MouseEvent('click'));assert.equal(selected,nodeKey(b.id));dom.window.close();
});
test('catalog/graph toggles preserve query and selection; offline remains explicit',async()=>{
 const dom=new JSDOM('<main></main>');Object.assign(globalThis,{document:dom.window.document});const host=document.querySelector('main')!;
 const state:SemanticState={mode:'Lineage',query:'selected',help:{query:'',source:'snapshot'}};
 const explanation=ExplanationSchema.parse({node:b,definitions:[],definitions_status:'disabled',unresolved:['Fixture unknown']});
 const cleanup=mountSemantic(host,state,async r=>r.operation==='lineage.graph'?graph:explanation);await settle();
 (host.querySelector('.lineage-display')as HTMLElement).scrollTop=430;(host.querySelector('.lineage-row')as HTMLButtonElement).click();await settle();assert.equal((host.querySelector('.lineage-display')as HTMLElement).scrollTop,430);assert.equal(nodeKey(state.selected!),nodeKey(b.id));assert.match(host.textContent!,/Fixture unknown/);
 assert.ok(!host.querySelector('.lineage-row')!.textContent!.includes('q2://'));assert.ok(host.querySelector('.lineage-row')!.getAttribute('title')!.includes('q2://fixture/data'));
 const graphButton=[...host.querySelectorAll('button')].find(b=>b.textContent==='Graph')!;graphButton.click();assert.ok(host.querySelector('svg'));assert.match(host.textContent!,/Directed one-hop subset/);assert.ok(host.querySelector('.lineage-graph-grid'));assert.equal(host.querySelector('.lineage-graph-grid')!.lastElementChild,host.querySelector('.lineage-detail'));assert.ok(host.classList.contains('semantic-graph-mode'));
 [...host.querySelectorAll('button')].find(b=>b.textContent==='Catalog')!.click();assert.equal((host.querySelector('input')as HTMLInputElement).value,'selected');assert.ok(host.querySelector('.lineage-row.selected'));assert.equal(host.querySelector('.lineage-graph-grid'),null);assert.ok(!host.classList.contains('semantic-graph-mode'));cleanup();
 host.replaceChildren();const offline=mountSemantic(host,{mode:'Lineage',query:'',help:{query:'',source:'snapshot'}},async()=>{throw new Error('offline');});await settle();assert.match(host.textContent!,/Current lineage unavailable/);assert.match(host.textContent!,/No prior staged snapshot/);assert.equal(host.querySelectorAll('.lineage-row').length,0);offline();dom.window.close();
});
test('exact node mismatch and oversized network response fail before display',async()=>{
 await assert.rejects(readLineage({operation:'lineage.node',id:b.id},'http://127.0.0.1:7420',async()=>new Response(JSON.stringify({node:a,definitions:[],definitions_status:'disabled',unresolved:[]}))),/another node/);
 await assert.rejects(readLineage({operation:'lineage.graph'},'http://127.0.0.1:7420',async()=>new Response('{}',{headers:{'content-length':'32000001'}})),/permitted size/);
});

test('failed refresh keeps dated stale evidence and node reads do not leave refresh disabled',async()=>{
 const dom=new JSDOM('<main></main>');Object.assign(globalThis,{document:dom.window.document});const host=document.querySelector('main')!;
 let rejectRefresh:(e:Error)=>void=()=>{};let resolveRefresh:(g:unknown)=>void=()=>{};
 const state:SemanticState={mode:'Lineage',query:'',graph,readAt:'2026-11-18T10:00:00Z',help:{query:'',source:'snapshot'}};
 const explanation={node:a,definitions:[],definitions_status:'disabled',unresolved:[]};
 const cleanup=mountSemantic(host,state,r=>r.operation==='lineage.graph'?new Promise((resolve,reject)=>{resolveRefresh=resolve;rejectRefresh=reject;}):Promise.resolve(explanation));
 const refresh=[...host.querySelectorAll('button')].find(b=>b.textContent==='Refresh source ↻')!;refresh.click();
 (host.querySelector('.lineage-row')as HTMLButtonElement).click();await settle();assert.equal(refresh.disabled,true);
 rejectRefresh(new Error('offline'));await settle();assert.equal(refresh.disabled,false);assert.match(host.textContent!,/STALE SNAPSHOT/);assert.match(host.textContent!,/2026-11-18 · 10:00:00 UTC/);assert.equal(host.querySelectorAll('.lineage-row').length,3);
 refresh.click();resolveRefresh(graph);await settle();assert.equal(refresh.disabled,false);assert.ok(!host.textContent!.includes('STALE SNAPSHOT'));cleanup();dom.window.close();
});

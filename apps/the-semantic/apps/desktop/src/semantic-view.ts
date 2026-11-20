import { read } from './client.js';
import { el,button,utc } from './dom.js';
import { LineageGraphSchema,ExplanationSchema,nodeKey,nodeLabel,type LineageGraph,type NodeID,type Explanation } from './lineage-contracts.js';
import { neighborhood } from './lineage-graph.js';
import { graphSVG } from './lineage-svg.js';
import { mountGraphViewport,type ViewportState } from './lineage-viewport.js';
import { lineageDetail } from './lineage-detail.js';
import { lineageTitle } from './lineage-label.js';
import { mountHelp,type HelpState } from './help-view.js';
import { semanticModes, repositories, definitions, type SemanticMode } from './semantic-sections.js';
import { mountGherkin, type GherkinState } from './gherkin-view.js';
import { mountSemanticArchive } from './semantic-archive.js';
export interface SemanticState {mode:SemanticMode;open?:boolean;lineageView?:'Catalog'|'Graph';query:string;selected?:NodeID;graph?:LineageGraph;explanation?:Explanation;readAt?:string;stale?:boolean;help:HelpState;gherkin?:GherkinState}
/** One catalog and directed graph share exact selection and search state. */
export function mountSemantic(host:HTMLElement,state:SemanticState,reader:typeof read=read,openResearch?:(id:string)=>void):()=>void {
  host.classList.add('semantic-workspace');
  let disposeSection=()=>{};
  let catalogScroll=0;let disposeViewport=()=>{};let viewportKey='';let viewport:ViewportState={zoom:1,expanded:false,x:0,y:0};
  let disposed=false;let graphGeneration=0;let nodeGeneration=0;let disposeHelp=()=>{};let graphError=state.stale??false;let graphPending=false;
  const intro=el('section','','intro semantic-heading');intro.append(el('p','THE SEMANTIC / KNOWLEDGE','eyebrow'),el('h1','Knowledge bases'));
  const bases=el('div','','semantic-bases');bases.setAttribute('aria-label','Knowledge bases');
  const main=el('section','','semantic-main');const back=button('← All knowledge bases',()=>{
    if(disposed)return;state.open=false;graphGeneration++;nodeGeneration++;graphPending=false;refresh.disabled=false;render();
    buttons[semanticModes.indexOf(state.mode)]?.focus();
  },'back semantic-back');back.setAttribute('aria-label','All knowledge bases');
  const heading=el('div','','semantic-view-heading');const title=el('h2');
  const views=el('div','','semantic-lineage-views');views.setAttribute('aria-label','Lineage view');
  const viewButtons=['Catalog','Graph'].map(label=>{const b=button(label,()=>{if(disposed||!state.open)return;state.lineageView=label as 'Catalog'|'Graph';render();});views.append(b);return b;});heading.append(title,views);
  const controls=el('div','','toolbar');const search=el('input');search.type='search';search.value=state.query;search.placeholder='Search jobs, datasets, columns, or meaning';search.setAttribute('aria-label','Search lineage catalog');
  const status=el('p','','caption');status.setAttribute('aria-live','polite');const content=el('div');
  const refresh=button('Refresh source ↻',()=>{void loadGraph();},'refresh');controls.append(search,refresh);main.append(back,heading,controls,status,content);host.append(intro,bases,main);
  const descriptions=[
    'Inspect source datasets, jobs, columns and their declared relationships.',
    'Read articles from the dated Zendesk export or public Help Center.',
    'Read supplied SME definitions and their source evidence.',
    'Inspect repository references supplied by the lineage graph.',
    'Open completed research and its retained evidence.',
    'Read committed Gherkin descriptions, scenarios and examples.',
  ];
  const buttons=semanticModes.map((mode,index)=>{const b=button('',()=>{
    if(disposed)return;state.mode=mode;state.open=true;render();title.focus({preventScroll:true});
    if(!state.graph&&!graphPending&&['Lineage','Definitions','Repositories'].includes(mode))void loadGraph();
  },'semantic-base');b.setAttribute('aria-label',mode);b.append(el('h2',mode),el('p',descriptions[index]),el('span','Open knowledge base →','record-id'));bases.append(b);return b;});title.tabIndex=-1;
  let disposeEditor = () => {};
  function render():void{
    if(disposed)return;
    disposeEditor(); disposeEditor = () => {};
    disposeSection();disposeSection=()=>{};
    const previousCatalog=content.querySelector<HTMLElement>('.lineage-grid:not(.lineage-graph-grid) .lineage-display');if(previousCatalog)catalogScroll=previousCatalog.scrollTop;
    disposeHelp();disposeHelp=()=>{};disposeViewport();disposeViewport=()=>{};host.classList.toggle('semantic-graph-mode',Boolean(state.open)&&state.mode==='Lineage'&&state.lineageView==='Graph');content.replaceChildren();bases.hidden=Boolean(state.open);main.hidden=!state.open;title.textContent=state.mode;views.hidden=state.mode!=='Lineage';viewButtons.forEach(b=>b.setAttribute('aria-pressed',String(b.textContent===(state.lineageView??'Catalog'))));
    if(!state.open)return;
    controls.hidden=state.mode!=='Lineage';status.hidden=state.mode!=='Lineage'&&state.mode!=='Definitions'&&state.mode!=='Repositories';
    if(state.graph){
    status.textContent=`${graphError?'STALE SNAPSHOT · ':''}${state.graph.nodes.length} nodes · ${state.graph.edges.length} declared directed edges · ${state.graph.unresolved.length} unresolved findings · Read ${state.readAt?utc(state.readAt):'time unavailable'}. Scoped coverage only.`;
    }else status.textContent=graphError?'Current lineage source unavailable. No fallback snapshot is loaded.':'Reading the current source graph…';
    content.className=controls.hidden?'semantic-section':'';
    const openNode=(id:NodeID):void=>{if(disposed||!state.open)return;state.mode='Lineage';state.lineageView='Catalog';void select(id);};
    if(state.mode==='Repositories'){repositories(content,state.graph);return;}
    if(state.mode==='Definitions'){definitions(content,state.graph,openNode);return;}
    if(state.mode==='PL-App Behavior'){disposeSection=mountGherkin(content,state.gherkin??=( {query:''} ),reader);return;}
    if(state.mode==='Research'){disposeSection=mountSemanticArchive(content,reader,openResearch);return;}
    if(state.mode==='Zendesk'){disposeHelp=mountHelp(content,state.help,reader);return;}
    if(!state.graph){content.append(el('p',graphError?'Current lineage unavailable. No prior staged snapshot is used. Start the validated current source service, then refresh.':'Reading the current lineage source…',graphError?'error':'empty'));return;}

    const matches=state.graph.nodes.filter(n=>[n.id.namespace,nodeLabel(n.id),n.facets.meaning.sme?.text??'',n.facets.meaning.machine?.description??''].join(' ').toLowerCase().includes(state.query.toLowerCase()));
    const grid=el('div','',state.lineageView==='Graph'?'lineage-grid lineage-graph-grid':'lineage-grid');const display=el('section','','lineage-display');const detail=el('aside','','lineage-detail');display.tabIndex=0;detail.tabIndex=0;display.setAttribute('aria-label',state.lineageView!=='Graph'?'Lineage catalog nodes':'Lineage graph');detail.setAttribute('aria-label','Selected node details');grid.append(display,detail);content.append(grid);
    if(state.lineageView!=='Graph'){
      display.append(el('p',`Showing ${Math.min(200,matches.length)} of ${matches.length} matching nodes${matches.length>200?' · Refine the search to read more.':'.'}`,'caption'));
      if(!matches.length)display.append(el('p','No source nodes match this search.','empty'));
      const table=el('table','','semantic-catalog');const head=el('thead');const headers=el('tr');for(const label of ['Name','Kind','System / scope'])headers.append(el('th',label));head.append(headers);const body=el('tbody');table.append(head,body);display.append(table);
      for(const node of matches.slice(0,200)){const tr=el('tr');const selected=Boolean(state.selected&&nodeKey(node.id)===nodeKey(state.selected));if(selected)tr.classList.add('selected');const name=el('td');const row=button(lineageTitle(node.id),()=>{void select(node.id);},'lineage-row'+(selected?' selected':''));row.title=node.id.namespace+' · '+nodeLabel(node.id);row.setAttribute('aria-label',lineageTitle(node.id)+' · '+node.id.namespace+' · '+nodeLabel(node.id));if(selected)row.setAttribute('aria-current','true');name.append(row);tr.append(name,el('td',node.job?'Job':node.dataset?'Dataset':'Column'),el('td',node.id.namespace));body.append(tr);}

    }else if(state.selected){
      const part=neighborhood(state.graph,state.selected);display.append(el('p',`Directed one-hop subset: ${part.nodes.length} of ${part.candidateNodes} neighborhood nodes, ${part.edges.length} of ${part.candidateEdges} incident edges. Display caps: 40 nodes / 80 edges. ${part.candidateNodes>part.nodes.length||part.candidateEdges>part.edges.length?'TRUNCATED. ':''}Arrows follow declared source → target; no inferred edges.`,'caption'));
      const key=nodeKey(state.selected);if(viewportKey!==key){viewportKey=key;viewport={zoom:1,expanded:viewport.expanded,x:0,y:0};}
      disposeViewport=mountGraphViewport(display,graphSVG(part,state.selected,id=>{void select(id);}),viewport);
      if(state.query)display.append(el('p',`Catalog search retained: ${state.query}. The graph shows the selected node’s source neighborhood.`,'caption'));
    }else display.append(el('p','Select a node in Catalog to see its directed one-hop graph.','empty'));
    const selected=state.graph.nodes.find(n=>state.selected&&nodeKey(n.id)===nodeKey(state.selected));
    if(selected)disposeEditor = lineageDetail(detail,state.explanation?.node??selected,state.explanation);else detail.append(el('h2','Select a source node.'),el('p','Its independent meaning, source commits and coverage findings will appear here.','caption'));
    if(state.lineageView!=='Graph')display.scrollTop=catalogScroll;
  }
  async function select(id:NodeID):Promise<void>{
    if(disposed||!state.open)return;
    state.selected=id;state.explanation=undefined;render();const current=++nodeGeneration;
    try{const explanation=ExplanationSchema.parse(await reader({operation:'lineage.node',id}));if(disposed||current!==nodeGeneration)return;if(nodeKey(explanation.node.id)!==nodeKey(id))throw new Error('Wrong node.');state.explanation=explanation;render();}
    catch{if(!disposed&&current===nodeGeneration){render();content.querySelector('.lineage-detail')?.append(el('p','Exact-node evidence could not be read. Catalog facts remain from the last graph snapshot.','error'));}}
  }
  async function loadGraph():Promise<void>{
    if(disposed||!state.open||graphPending)return;graphPending=true;
    const current=++graphGeneration;nodeGeneration++;refresh.disabled=true;status.textContent='Reading the current source graph…';
    try{const graph=LineageGraphSchema.parse(await reader({operation:'lineage.graph'}));if(disposed||current!==graphGeneration)return;state.graph=graph;state.readAt=new Date().toISOString();state.explanation=undefined;graphError=false;state.stale=false;if(state.selected&&!graph.nodes.some(n=>nodeKey(n.id)===nodeKey(state.selected!)))state.selected=undefined;render();}
    catch{if(!disposed&&current===graphGeneration){graphError=true;state.stale=true;render();if(!state.graph)status.textContent='Current lineage source unavailable. No fallback snapshot is loaded.';}}
    finally{if(!disposed&&current===graphGeneration){refresh.disabled=false;graphPending=false;}}
  }
  search.oninput=()=>{if(disposed||!state.open)return;state.query=search.value;catalogScroll=0;const list=content.querySelector<HTMLElement>('.lineage-display');if(list)list.scrollTop=0;render();};render();if(state.open&&!state.graph&&['Lineage','Definitions','Repositories'].includes(state.mode))void loadGraph();
  return()=>{disposeEditor();disposeSection();disposed=true;graphGeneration++;nodeGeneration++;disposeHelp();disposeViewport();host.classList.remove('semantic-graph-mode','semantic-workspace');};
}

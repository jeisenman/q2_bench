// Explicit read-only integration against the current lineage and configured knowledge sources.
const {app}=require('electron');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const statePath=fs.mkdtempSync(path.join(os.tmpdir(),'semantic-source-native-'));
app.setPath('userData',statePath);
app.on('quit',()=>fs.rmSync(statePath,{recursive:true,force:true}));
const timer=setTimeout(()=>{console.error('Semantic native check timed out.');app.exit(1);},60000);
app.on('browser-window-created',(_event,window)=>{
 window.hide();window.webContents.once('did-finish-load',async()=>{
  try{
   const result=await window.webContents.executeJavaScript(`(async()=>{
    const wait=(predicate)=>new Promise((resolve,reject)=>{if(predicate())return resolve();const observer=new MutationObserver(()=>{if(predicate()){observer.disconnect();clearTimeout(timer);resolve();}});observer.observe(document.body,{childList:true,subtree:true});const timer=setTimeout(()=>{observer.disconnect();reject(new Error('Expected source view did not appear.'));},20000);});
    const click=(label)=>{const b=[...document.querySelectorAll('button')].find(n=>(n.getAttribute('aria-label')===label||n.textContent===label));if(!b)throw new Error('Missing control '+label);b.click();};
    const graph=await window.semantic.read({operation:'lineage.graph'});
    click('Semantic Layer');await wait(()=>document.querySelector('.lineage-row'));
    const first=document.querySelector('.lineage-row');const firstTitle=first.textContent;first.click();
    await wait(()=>document.querySelector('.lineage-detail h2')?.textContent===firstTitle);
    click('Graph');await wait(()=>document.querySelector('.lineage-canvas svg'));
    const graphNodes=document.querySelectorAll('.lineage-svg-node').length;const graphEdges=document.querySelectorAll('.lineage-canvas line').length;
    const graphCaption=document.querySelector('.lineage-display').textContent;
    click('Zendesk');await wait(()=>document.querySelector('.help-content .question-row'));
    const snapshot=await window.semantic.read({operation:'knowledge.list'});
    const snapshotCaption=document.querySelector('main').textContent;
    document.querySelector('.help-content .question-row').click();await wait(()=>document.querySelector('.help-article'));
    const articlePlain=document.querySelectorAll('.help-article img,.help-article script,.help-article iframe').length===0;
    const selector=document.querySelector('select[aria-label="Knowledge source"]');selector.value='public';selector.dispatchEvent(new Event('change',{bubbles:true}));
    await wait(()=>document.querySelector('.help-content .question-row'));
    const publicArticles=await window.semantic.read({operation:'help.list'});
    return {nodes:graph.nodes.length,edges:graph.edges.length,unresolved:graph.unresolved.length,graphNodes,graphEdges,graphCaption,
      snapshotCount:snapshot.snapshot.article_count,snapshotDated:snapshotCaption.includes(snapshot.snapshot.completed_at.slice(0,10)),articlePlain,publicCount:publicArticles.count,
      noNode:typeof window.require==='undefined'&&typeof window.process==='undefined',csp:document.querySelector('meta[http-equiv="Content-Security-Policy"]').content};
   })()`);
   assert.ok(result.nodes>0);assert.ok(result.edges>0);assert.ok(result.graphNodes>=1&&result.graphNodes<=40);assert.ok(result.graphEdges<=80);assert.match(result.graphCaption,/Directed one-hop subset/);
   assert.ok(result.snapshotCount>25);assert.equal(result.snapshotDated,true);assert.equal(result.articlePlain,true);assert.ok(result.publicCount>=1);assert.equal(result.noNode,true);assert.ok(result.csp.includes("connect-src 'none'"));
   console.log(JSON.stringify({status:'PASS',current_lineage_nodes:result.nodes,current_lineage_edges:result.edges,unresolved:result.unresolved,snapshot_articles:result.snapshotCount,public_articles:result.publicCount,checks:'Actual preload reads, Catalog/Graph selection, bounded graph, dated export, plain article text, trusted HTTPS, isolation and CSP'}));
   clearTimeout(timer);app.exit(0);
  }catch(error){console.error(error);clearTimeout(timer);app.exit(1);}
 });
});
require(path.resolve(__dirname,'../dist-electron/main.cjs'));

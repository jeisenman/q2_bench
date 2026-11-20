// Read-only navigation and layout check against the actual main/preload.
const {app}=require('electron');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const statePath=fs.mkdtempSync(path.join(os.tmpdir(),'knowledge-index-native-'));
app.setPath('userData',statePath);
app.on('quit',()=>fs.rmSync(statePath,{recursive:true,force:true}));
const timeout=setTimeout(()=>{console.error('Knowledge index check timed out.');app.exit(1);},40000);
app.on('browser-window-created',(_event,window)=>{
  window.hide();
  window.webContents.once('did-finish-load',async()=>{
    try{
      const result=await window.webContents.executeJavaScript(`(async()=>{
        const wait=predicate=>new Promise((resolve,reject)=>{
          if(predicate())return resolve();
          const observer=new MutationObserver(()=>{if(predicate()){observer.disconnect();clearTimeout(timer);resolve();}});
          observer.observe(document.body,{childList:true,subtree:true,attributes:true});
          const timer=setTimeout(()=>{observer.disconnect();reject(new Error('Expected knowledge view did not appear.'));},15000);
        });
        const click=label=>{const b=[...document.querySelectorAll('button')].find(n=>n.getAttribute('aria-label')===label||n.textContent===label);if(!b)throw new Error('Missing control '+label);b.click();};
        const back=()=>{const b=[...document.querySelectorAll('button')].find(n=>n.textContent.includes('All knowledge bases'));if(!b)throw new Error('Missing knowledge index return');b.click();};
        await wait(()=>document.querySelector('.systems')?.textContent.includes('CONNECTED'));
        const researchHeading=document.querySelector('main h1').textContent;
        click('Semantic Layer');await wait(()=>document.querySelectorAll('.semantic-base').length===6);
        const labels=[...document.querySelectorAll('.semantic-base')].map(n=>n.getAttribute('aria-label'));
        const noSidebar=!document.querySelector('.semantic-sidebar');
        click('Zendesk');await wait(()=>document.querySelector('.help-content .question-row'));
        const articleRow=document.querySelector('.help-content .question-row');articleRow.click();await wait(()=>document.querySelector('.help-article'));
        const selectedTitle=document.querySelector('.help-article h2').textContent;
        back();click('Zendesk');await wait(()=>document.querySelector('.help-article'));
        const retainedArticle=document.querySelector('.help-article h2').textContent===selectedTitle;
        back();
        window.__knowledgeResearchHeading=researchHeading;
        return {labels,noSidebar,retainedArticle,rows:document.querySelectorAll('.semantic-base').length,
          indexVisible:getComputedStyle(document.querySelector('.semantic-bases')).display!=='none'&&document.querySelector('.semantic-main').hidden,
          noCatalogOnIndex:!document.querySelector('.semantic-catalog'),isolated:typeof window.require==='undefined'&&typeof window.process==='undefined'};
      })()`);
      assert.deepEqual(result.labels,['Lineage','Zendesk','Definitions','Repositories','Research','PL-App Behavior']);
      for(const key of ['noSidebar','retainedArticle','noCatalogOnIndex','indexVisible','isolated'])assert.equal(result[key],true,key);
      assert.equal(result.rows,6);
      if(process.env.SEMANTIC_KNOWLEDGE_SCREENSHOT){
        await window.webContents.executeJavaScript('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))');
        const picture=await window.webContents.capturePage();fs.writeFileSync(process.env.SEMANTIC_KNOWLEDGE_SCREENSHOT,picture.toPNG());
      }
      window.setMinimumSize(320,320);window.setContentSize(620,900);
      const narrow=await window.webContents.executeJavaScript(`new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>{
        resolve(document.documentElement.scrollWidth<=innerWidth+1);
      })))`);
      assert.equal(narrow,true,'Narrow index must not overflow');
      const preserved=await window.webContents.executeJavaScript(`(async()=>{
        [...document.querySelectorAll('nav[aria-label="Main navigation"] button')].find(n=>n.textContent==='Research').click();
        await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
        return document.querySelector('main h1').textContent===window.__knowledgeResearchHeading&&Boolean(document.querySelector('.editorial-grid'))&&!document.querySelector('.semantic-workspace');
      })()`);
      assert.equal(preserved,true,'Editorial Research must remain intact');
      console.log('PASS: six editorial knowledge rows, no sidebar, open/back, retained article, narrow layout and original Research view.');
      clearTimeout(timeout);app.exit(0);
    }catch(error){console.error(error);clearTimeout(timeout);app.exit(1);}
  });
});
require(path.resolve(__dirname,'../dist-electron/main.cjs'));

// Read-only click-to-detail check against the actual bundled main and preload.
const {app}=require('electron');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const statePath=fs.mkdtempSync(path.join(os.tmpdir(),'gherkin-detail-native-'));
app.setPath('userData',statePath);
app.on('quit',()=>fs.rmSync(statePath,{recursive:true,force:true}));
const timeout=setTimeout(()=>{console.error('Gherkin detail check timed out.');app.exit(1);},40000);
app.on('browser-window-created',(_event,window)=>{
  window.hide();
  window.webContents.once('did-finish-load',async()=>{
    try{
      const result=await window.webContents.executeJavaScript(`(async()=>{
        const wait=predicate=>new Promise((resolve,reject)=>{
          if(predicate())return resolve();
          const observer=new MutationObserver(()=>{if(predicate()){observer.disconnect();clearTimeout(timer);resolve();}});
          observer.observe(document.body,{childList:true,subtree:true,attributes:true});
          const timer=setTimeout(()=>{observer.disconnect();reject(new Error('Expected Gherkin detail did not appear.'));},15000);
        });
        const click=label=>{const control=[...document.querySelectorAll('button')].find(b=>b.getAttribute('aria-label')===label||b.textContent===label);if(!control)throw new Error('Missing control '+label);control.click();};
        await wait(()=>document.querySelector('.systems')?.textContent.includes('CONNECTED'));
        click('Semantic Layer');
        await wait(()=>document.querySelector('.semantic-base'));
        click('PL-App Behavior');
        await wait(()=>document.querySelector('.gherkin-feature-row'));
        const row=[...document.querySelectorAll('.gherkin-feature-row')].find(b=>b.dataset.path.endsWith('/AndiMarks.feature'));
        if(!row)throw new Error('Expected source specification is not on the first page.');
        row.click();
        const loading=document.querySelector('.gherkin-detail').getAttribute('aria-busy')==='true';
        await wait(()=>document.querySelector('.gherkin-source')&&document.querySelector('.gherkin-detail').getAttribute('aria-busy')==='false');
        const list=await window.semantic.read({operation:'gherkin.list',offset:0});
        const feature=await window.semantic.read({operation:'gherkin.feature',path:row.dataset.path,commit:list.commit});
        const detail=document.querySelector('.gherkin-detail'),left=document.querySelector('.gherkin-list-panel');
        const a=left.getBoundingClientRect(),b=detail.getBoundingClientRect();
        const lineageSearch=document.querySelector('[aria-label="Search lineage catalog"]');
        return {selected:row.getAttribute('aria-pressed')==='true',loading,linked:row.getAttribute('aria-controls')===detail.id,
          focused:document.activeElement===detail,sourceExact:document.querySelector('.gherkin-source').textContent===feature.text,
          hasScenarios:feature.text.includes('Scenario:'),hasIndex:Boolean(detail.querySelector('.gherkin-outline')),
          adjacent:b.left>=a.right-1&&Math.abs(a.top-b.top)<2,
          lineageSearchHidden:lineageSearch&&getComputedStyle(lineageSearch.parentElement).display==='none',
          isolated:typeof window.require==='undefined'&&typeof window.process==='undefined'};
      })()`);
      for(const [name,value] of Object.entries(result))assert.equal(value,true,name);
      if(process.env.SEMANTIC_GHERKIN_SCREENSHOT){
        const picture=await window.webContents.capturePage();
        fs.writeFileSync(process.env.SEMANTIC_GHERKIN_SCREENSHOT,picture.toPNG());
      }
      window.setMinimumSize(320,320);window.setContentSize(620,900);
      const narrow=await window.webContents.executeJavaScript(`new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>{
        const a=document.querySelector('.gherkin-list-panel').getBoundingClientRect(),b=document.querySelector('.gherkin-detail').getBoundingClientRect();
        resolve({stacked:b.top>=a.bottom-1,noPageOverflow:document.documentElement.scrollWidth<=innerWidth+1});
      })))`);
      assert.equal(narrow.stacked,true);assert.equal(narrow.noPageOverflow,true);
      console.log('PASS: actual Gherkin row reveals exact full source, accessible selection/loading, desktop detail panel, narrow stacking and renderer isolation.');
      clearTimeout(timeout);app.exit(0);
    }catch(error){console.error(error);clearTimeout(timeout);app.exit(1);}
  });
});
require(path.resolve(__dirname,'../dist-electron/main.cjs'));

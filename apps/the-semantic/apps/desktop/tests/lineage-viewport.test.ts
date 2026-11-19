import test from 'node:test';
import assert from 'node:assert/strict';
import {JSDOM} from 'jsdom';
import {fitGraph,graphZoom,mountGraphViewport,type ViewportState} from '../src/lineage-viewport.js';

test('Fit contains tall and wide graph bounds for narrow and wide canvases',()=>{
 for(const bounds of [{x:0,y:0,width:920,height:3590},{x:0,y:0,width:920,height:300}]){
  for(const [width,height] of [[1400,560],[320,480],[1800,900]]){
   const fit=fitGraph(bounds,width!,height!);
   assert.ok(fit.x<bounds.x&&fit.y<bounds.y);
   assert.ok(fit.x+fit.width>bounds.x+bounds.width);
   assert.ok(fit.y+fit.height>bounds.y+bounds.height);
   assert.ok(Math.abs(fit.width/fit.height-width!/height!)<0.00001);
  }
 }
 assert.throws(()=>fitGraph({x:0,y:0,width:0,height:300},100,100));
 assert.throws(()=>fitGraph({x:0,y:0,width:920,height:300},0,100));
 assert.throws(()=>graphZoom(NaN));assert.equal(graphZoom(0),0.25);assert.equal(graphZoom(99),8);
});

test('zoom, Fit, resize and expand restore the viewport without changing graph selection',()=>{
 const dom=new JSDOM('<main></main>');Object.assign(globalThis,{document:dom.window.document});
 const host=document.querySelector('main')!;const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 920 3590');
 const selected=document.createElementNS('http://www.w3.org/2000/svg','g');selected.setAttribute('aria-label','selected node');let selections=0;selected.onclick=()=>{selections++;};svg.append(selected);
 const state:ViewportState={zoom:1,expanded:false,x:0,y:0};const dispose=mountGraphViewport(host,svg,state);
 const click=(label:string)=>{const control=[...host.querySelectorAll('button')].find(b=>b.textContent===label||b.getAttribute('aria-label')===label)!;control.click();return control;};
 const initial=svg.getAttribute('viewBox');click('Zoom out');assert.ok(state.zoom<1);assert.notEqual(svg.getAttribute('viewBox'),initial);
 click('Zoom in');click('Zoom in');assert.ok(state.zoom>1);
 const canvas=host.querySelector('.lineage-canvas')!;canvas.dispatchEvent(new dom.window.KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true}));assert.ok(state.x>0);
 click('Fit to view');assert.equal(state.zoom,1);assert.equal(state.x,0);assert.equal(svg.getAttribute('viewBox'),initial);
 for(let i=0;i<10;i++)click('Zoom out');assert.equal(state.zoom,.25);assert.equal(host.querySelector<HTMLButtonElement>('[aria-label="Zoom out"]')!.disabled,true);
 click('Fit to view');const expand=click('Expand graph');assert.equal(expand.getAttribute('aria-expanded'),'true');assert.ok(host.querySelector('.lineage-viewport.expanded'));
 selected.dispatchEvent(new dom.window.MouseEvent('click',{bubbles:true}));assert.equal(selections,1);assert.equal(state.expanded,true);
 canvas.dispatchEvent(new dom.window.KeyboardEvent('keydown',{key:'Escape',bubbles:true}));assert.equal(state.expanded,false);assert.equal(expand.textContent,'Expand graph');
 click('Expand graph');click('Restore graph');assert.equal(state.expanded,false);
 Object.defineProperty(canvas,'clientWidth',{value:1400,configurable:true});Object.defineProperty(canvas,'clientHeight',{value:560});dom.window.dispatchEvent(new dom.window.Event('resize'));assert.notEqual(svg.getAttribute('viewBox'),initial);
 const resized=svg.getAttribute('viewBox');dispose();Object.defineProperty(canvas,'clientWidth',{value:900});dom.window.dispatchEvent(new dom.window.Event('resize'));assert.equal(svg.getAttribute('viewBox'),resized);dom.window.close();
});

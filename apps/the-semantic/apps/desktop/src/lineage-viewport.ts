import {button,el} from './dom.js';
export interface GraphBox {x:number;y:number;width:number;height:number}
export interface ViewportState {zoom:number;expanded:boolean;x:number;y:number}
const minZoom=0.25;const maxZoom=8;
/** Fits all graph bounds with padding into the available canvas aspect ratio. */
export function fitGraph(bounds:GraphBox,width:number,height:number):GraphBox {
  if(![bounds.x,bounds.y,bounds.width,bounds.height,width,height].every(Number.isFinite)||bounds.width<=0||bounds.height<=0||width<=0||height<=0)throw new Error('Graph bounds and viewport dimensions must be finite and positive.');
  const scale=Math.max((bounds.width+48)/width,(bounds.height+48)/height);
  return {x:bounds.x+bounds.width/2-width*scale/2,y:bounds.y+bounds.height/2-height*scale/2,width:width*scale,height:height*scale};
}
/** Limits graph zoom relative to the fitted view without dropping any nodes. */
export function graphZoom(value:number):number {
  if(!Number.isFinite(value))throw new Error('Graph zoom must be finite.');
  return Math.max(minZoom,Math.min(maxZoom,value));
}
/** Mounts fit, zoom, pan and expansion controls; disposal releases resize listeners. */
export function mountGraphViewport(host:HTMLElement,svg:SVGSVGElement,state:ViewportState):()=>void {
  const boundsValues=svg.getAttribute('viewBox')!.split(' ').map(Number);
  const bounds={x:boundsValues[0]!,y:boundsValues[1]!,width:boundsValues[2]!,height:boundsValues[3]!};
  const panel=el('div','','lineage-viewport');const toolbar=el('div','','graph-toolbar');toolbar.setAttribute('aria-label','Graph view controls');
  const canvas=el('div','','lineage-canvas');canvas.tabIndex=0;canvas.setAttribute('aria-label','Directed lineage graph. Drag to pan, or use arrow keys.');
  const scale=el('output','','graph-scale');scale.setAttribute('aria-label','Zoom relative to Fit');
  let frame:GraphBox;let drag:{x:number;y:number;offsetX:number;offsetY:number}|undefined;let moved=false;
  function draw():void {
    panel.classList.toggle('expanded',state.expanded);expand.textContent=state.expanded?'Restore graph':'Expand graph';expand.setAttribute('aria-expanded',String(state.expanded));
    frame=fitGraph(bounds,canvas.clientWidth||1000,canvas.clientHeight||560);
    const width=frame.width/state.zoom;const height=frame.height/state.zoom;
    svg.setAttribute('viewBox',`${frame.x+frame.width/2-width/2+state.x} ${frame.y+frame.height/2-height/2+state.y} ${width} ${height}`);
    scale.textContent=`${Math.round(state.zoom*100)}% of Fit`;minus.disabled=state.zoom<=minZoom;plus.disabled=state.zoom>=maxZoom;
  }
  function zoom(factor:number):void {state.zoom=graphZoom(state.zoom*factor);draw();}
  const minus=button('−',()=>zoom(1/1.5));minus.setAttribute('aria-label','Zoom out');
  const plus=button('+',()=>zoom(1.5));plus.setAttribute('aria-label','Zoom in');
  const fit=button('Fit to view',()=>{state.zoom=1;state.x=0;state.y=0;draw();});
  const expand=button('',()=>{state.expanded=!state.expanded;draw();});
  toolbar.append(minus,plus,fit,scale,expand);canvas.append(svg);panel.append(toolbar,el('p','Drag to pan · Use + and − to zoom · Fit to view shows all displayed nodes.','caption graph-hint'),canvas);host.append(panel);draw();
  canvas.onpointerdown=e=>{if(e.button!==0)return;drag={x:e.clientX,y:e.clientY,offsetX:state.x,offsetY:state.y};moved=false;};
  canvas.onpointermove=e=>{if(!drag)return;const dx=e.clientX-drag.x;const dy=e.clientY-drag.y;if(Math.abs(dx)+Math.abs(dy)<4&&!moved)return;moved=true;canvas.setPointerCapture?.(e.pointerId);state.x=drag.offsetX-dx*frame.width/state.zoom/(canvas.clientWidth||1000);state.y=drag.offsetY-dy*frame.height/state.zoom/(canvas.clientHeight||560);draw();};
  canvas.onpointerup=canvas.onpointercancel=()=>{drag=undefined;};
  canvas.addEventListener('click',e=>{if(moved){e.stopPropagation();moved=false;}},true);
  panel.onkeydown=e=>{
    if(e.key==='Escape'&&state.expanded){state.expanded=false;draw();expand.focus();return;}
    if(e.target!==canvas)return;
    const directions:Record<string,[number,number]>={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]};
    const direction=directions[e.key];if(!direction)return;e.preventDefault();state.x+=direction[0]*frame.width/state.zoom/10;state.y+=direction[1]*frame.height/state.zoom/10;draw();
  };
  const view=host.ownerDocument.defaultView;const observer=view?.ResizeObserver?new view.ResizeObserver(draw):undefined;observer?.observe(canvas);view?.addEventListener('resize',draw);
  return()=>{observer?.disconnect();view?.removeEventListener('resize',draw);};
}

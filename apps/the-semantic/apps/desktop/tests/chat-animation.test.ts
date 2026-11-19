import test from 'node:test';import assert from 'node:assert/strict';import {JSDOM} from 'jsdom';import {revealReply} from '../src/chat-animation.js';
test('reply reveal is bounded and cancellation releases pending work',async()=>{
 const dom=new JSDOM('<p></p>');const host=dom.window.document.querySelector('p')!;let complete=0;
 const short=revealReply(host,'A draft.',()=>{complete++;});assert.equal(host.textContent,'A draft.');assert.equal(complete,1);short();
 const stop=revealReply(host,'A long reply '.repeat(100),()=>{complete++;});assert.ok(host.textContent!.length<1200);stop();const partial=host.textContent;await new Promise(r=>setTimeout(r,30));assert.equal(host.textContent,partial);assert.equal(complete,1);dom.window.close();
});

import test from 'node:test';
import assert from 'node:assert/strict';
import {drawingWorkspace} from '../src/drawing-ui.js';

test('reprocessing validation errors enter the shared visible error boundary without a POST',async()=>{
  const nativeFetch=globalThis.fetch,nativeFormData=globalThis.FormData;
  const record={drawing_id:'drawing_test',source:{name:'synthetic.png',hash:'test',file_id:'file_test'},created_at:'now',revision:1,input:{page:1},result:{page:{page:1,page_count:1},width:100,height:100,candidates:[],limitations:[]},reviews:{}};
  const nodes=new Map(['#drawing-record','#drawing-result','#drawing-links','#drawing-history','#drawing-history-result','#drawing-reprocess','#drawing-upload'].map(id=>[id,{isConnected:true,options:[{value:'drawing_test'}]}]));
  const host={isConnected:true,querySelector:id=>nodes.get(id)||null};
  const calls=[],errors=[],pending=[];
  globalThis.FormData=class extends Map{constructor(){super([['deskew_mode','manual'],['angle_degrees','']]);}};
  globalThis.fetch=async(url,options)=>{calls.push({url,method:options.method||'GET'});return new Response(JSON.stringify(url.endsWith('/drawings')?[record]:record),{status:200});};
  const action=fn=>{const p=Promise.resolve().then(fn).catch(e=>errors.push(e.message));pending.push(p);return p;};
  try{
    await drawingWorkspace({project:{project_id:'project_test'}},host,action);
    assert.doesNotThrow(()=>nodes.get('#drawing-reprocess').onsubmit({preventDefault(){},submitter:{}}));
    await Promise.all(pending);
    assert.deepEqual(errors,['请输入明确的旋转角度。']);
    assert.ok(calls.every(x=>x.method==='GET'));
  }finally{globalThis.fetch=nativeFetch;globalThis.FormData=nativeFormData;}
});

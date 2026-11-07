import test from 'node:test';
import assert from 'node:assert/strict';
import {captureTaskEditor} from '../src/task-editor.js';

function surface(){
 const input={id:'command',name:'',type:'textarea',value:'review selected scenario',checked:false};
 const select={id:'agent-mode',name:'',type:'select-one',value:'local',checked:false};
 const controls=[input,select],form={querySelectorAll:()=>controls,contains:el=>controls.includes(el)};
 const editor={open:true,isConnected:true,querySelector:()=>form};
 const doc={activeElement:input,body:{}};let focused=0,scrolled=0;
 const target={isConnected:true,ownerDocument:doc,closest:()=>({querySelector:()=>editor}),focus:()=>focused++,scrollIntoView:()=>scrolled++};
 return {input,select,controls,editor,doc,target,observed:()=>({focused,scrolled})};
}
test('accepted unchanged draft collapses and moves focus to result without clearing fields',()=>{
 const s=surface();const accepted=captureTaskEditor(s.target);assert.equal(s.editor.open,true);
 assert.equal(accepted(),true);assert.equal(s.editor.open,false);assert.equal(s.input.value,'review selected scenario');assert.equal(s.select.value,'local');
 assert.deepEqual(s.observed(),{focused:1,scrolled:1});s.editor.open=true;assert.equal(s.input.value,'review selected scenario');
});
test('edits and new read controls entered during pending request remain open and focused',()=>{
 for(const change of [s=>s.input.value='new draft',s=>s.select.value='local_model',s=>s.controls.push({id:'new-scope',value:'scenario_new'})]){
  const s=surface(),accepted=captureTaskEditor(s.target);change(s);assert.equal(accepted(),false);assert.equal(s.editor.open,true);assert.deepEqual(s.observed(),{focused:0,scrolled:0});
 }
});
test('detached project cannot change editor or focus; existing external focus stays put',()=>{
 for(const key of ['target','editor']){const s=surface(),accepted=captureTaskEditor(s.target);s[key].isConnected=false;assert.equal(accepted(),false);assert.equal(s.editor.open,true);}
 const s=surface(),accepted=captureTaskEditor(s.target);s.doc.activeElement={otherControl:true};assert.equal(accepted(),true);assert.deepEqual(s.observed(),{focused:0,scrolled:0});
});
test('capturing pending submission alone neither closes input nor moves focus',()=>{
 const s=surface();captureTaskEditor(s.target);assert.equal(s.editor.open,true);assert.deepEqual(s.observed(),{focused:0,scrolled:0});
 assert.equal(captureTaskEditor({})(),false);
});

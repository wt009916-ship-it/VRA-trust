import test from 'node:test';
import assert from 'node:assert/strict';
import {refreshAgentMode, createAgentModePreference} from '../src/agent-mode-status.js';

const mode=()=>({isConnected:true,value:'local_model',options:[{},{},{}]});
test('same-project rerender retains explicitly selected mode; other project and logout reset it',()=>{
 const preference=createAgentModePreference();const first=mode();
 preference.bind(first,'owner','projectA');assert.equal(first.value,'local');
 first.value='local_model';first.onchange();first.isConnected=false;
 const afterEdit=mode();preference.bind(afterEdit,'owner','projectA');assert.equal(afterEdit.value,'local_model');
 const other=mode();preference.bind(other,'owner','projectB');assert.equal(other.value,'local');
 afterEdit.value='provider';afterEdit.onchange();
 const sameOther=mode();preference.bind(sameOther,'owner','projectB');assert.equal(sameOther.value,'local');
 sameOther.value='provider';sameOther.onchange();preference.clear();
 const afterLogin=mode();preference.bind(afterLogin,'owner','projectB');assert.equal(afterLogin.value,'local');
 afterLogin.value='provider';afterLogin.onchange();
 const otherOwner=mode();preference.bind(otherOwner,'otherOwner','projectB');assert.equal(otherOwner.value,'local');
});
test('configuration readiness refreshes without changing mode or claiming connectivity',async()=>{
 const m=mode();await refreshAgentMode(m,async()=>({provider_ready:false,local_model_ready:true,local_model:'test model'}));
 assert.equal(m.options[2].textContent,'本机 AI · test model');assert.equal(m.value,'local_model');
 await refreshAgentMode(m,async()=>({provider_ready:false,local_model_ready:false}));
 assert.equal(m.options[2].textContent,'本机 AI · 请先配置');
});
test('failed status read shows unknown rather than stale readiness',async()=>{
 const m=mode();await refreshAgentMode(m,async()=>{throw Error('offline');});
 assert.equal(m.options[2].textContent,'本机 AI · 配置状态待核实');
});
test('late pre-save response cannot replace newer configuration state',async()=>{
 const m=mode();let resolve;const old=refreshAgentMode(m,()=>new Promise(r=>{resolve=r;}));
 await refreshAgentMode(m,async()=>({local_model_ready:true,local_model:'new'}));
 resolve({local_model_ready:false});await old;assert.equal(m.options[2].textContent,'本机 AI · new');
});

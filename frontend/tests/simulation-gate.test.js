import test from 'node:test';
import assert from 'node:assert/strict';
import {bindSimulationGate} from '../src/simulation-gate.js';

function fixture(initialGate,loadGate) {
 const button={isConnected:true,disabled:false},scheme={value:'baseline',disabled:false,addEventListener(){}};
 const status={textContent:''};return {button,scheme,status,control:bindSimulationGate({button,scheme,status,initialGate,loadGate})};
}
test('invalid weather disables submission and displays its source error',()=>{
 const f=fixture({can_simulate:false,blockers:[{message:'EPW line 9 dry_bulb'}]},async()=>({can_simulate:false}));
 assert.equal(f.button.disabled,true);assert.equal(f.control.ready,false);assert.match(f.status.textContent,/line 9/);
});
test('out-of-order readiness cannot enable the wrong scheme',async()=>{
 const pending=[];const f=fixture({can_simulate:true},()=>new Promise(resolve=>pending.push(resolve)));
 f.scheme.value='R1';const first=f.control.refresh();assert.equal(f.button.disabled,true);
 f.scheme.value='R2';const second=f.control.refresh();pending[1]({can_simulate:false});await second;
 pending[0]({can_simulate:true});await first;assert.equal(f.button.disabled,true);
});
test('a different valid scheme can enable and a failed refresh disables again',async()=>{
 let fail=false;const f=fixture({can_simulate:false},async()=>{if(fail)throw Error('network');return {can_simulate:true};});
 f.scheme.value='R1';await f.control.refresh();assert.equal(f.button.disabled,false);
 f.control.begin();assert.equal(f.button.disabled,true);assert.equal(f.scheme.disabled,true);
 fail=true;await f.control.end();assert.equal(f.button.disabled,true);assert.equal(f.scheme.disabled,false);
 assert.match(f.status.textContent,/network/);
});

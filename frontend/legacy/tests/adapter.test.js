import test from 'node:test'
import assert from 'node:assert/strict'
import {normalizeExternalResult,comparisonToDashboard} from '../src/apiAdapter.js'
import {finiteOrNull,safeObject,fmt} from '../src/safety.js'
test('all failure states clear results',()=>{for(const status of ['failed','stale','running','queued','unknown'])assert.equal(normalizeExternalResult({run_id:'x',status,plans:[{}]}).hasResults,false)})
test('success alias requires run identity',()=>{assert.equal(normalizeExternalResult({status:'success',plans:[{}]}).hasResults,false);assert.equal(normalizeExternalResult({status:'succeeded',run_id:'x',plans:[{}]}).hasResults,true)})
test('missing LCA and credit never zero',()=>{const p=normalizeExternalResult({status:'success',run_id:'x',plans:[{}]}).dashboard.plans[0];assert.equal(p.carbon.lca_total_tCO2,null);assert.equal(p.ccer.annual_value_yuan,null)})
test('nonfinite and strings not numbers',()=>{for(const v of [NaN,Infinity,null,undefined,'2',true])assert.equal(finiteOrNull(v),null);assert.equal(finiteOrNull(0),0);assert.equal(fmt(null),'未提供')})
test('HTML escaped and prototype keys blocked',()=>{const v=safeObject(JSON.parse('{"x":"<img onerror=x>","__proto__":{"polluted":true}}'));assert.equal(v.x,'&lt;img onerror=x&gt;');assert.equal(Object.hasOwn(v,'__proto__'),false)})
test('unvalidated comparison rejected',()=>assert.throws(()=>comparisonToDashboard({schema_version:'bad'},{})))

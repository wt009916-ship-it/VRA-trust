import test from 'node:test';
import assert from 'node:assert/strict';
import {validateReadRequests,readRequestProgressMarkup,readRequestMarkup} from '../src/agent-requests.js';
const options={mode:'local_model',allowCompute:false,objective:'open_ended'};
const req={request_key:'scope',kind:'thermal',purpose:'availability',record_id:''};

test('explicit result scope cannot silently become latest, change kind, or enable compute',()=>{
 assert.deepEqual(validateReadRequests([req],options),[{...req,record_id:null}]);
 for(const bad of [{...req,purpose:'results'},{...req,record_id:'cost_'+'a'.repeat(32)},
  {...req,request_key:'bad key'},{...req,purpose:'invented'}])assert.throws(()=>validateReadRequests([bad],options));
 for(const changed of [{mode:'local'},{allowCompute:true},{objective:'inspect_results'},{calculationPlans:[{}]}])assert.throws(()=>validateReadRequests([req],{...options,...changed}));
 assert.deepEqual(validateReadRequests([], {...options,mode:'local'}),[]);
});

test('same-kind distinct IDs stay distinct but duplicate scopes fail',()=>{
 const a={...req,purpose:'results',record_id:'thermal_'+'a'.repeat(32)};
 const b={...a,request_key:'second',record_id:'thermal_'+'b'.repeat(32)};
 assert.equal(validateReadRequests([a,b],options).length,2);
 assert.throws(()=>validateReadRequests([a,{...a,request_key:'other'}],options));
 assert.throws(()=>validateReadRequests(Array.from({length:7},(_,i)=>({...req,request_key:'r'+i})),options));
});

test('scope progress separates presence, current values, missing records and unfinished work',()=>{
 const html=readRequestProgressMarkup({read_request_progress:[{...req,state:'availability_verified'},
  {...req,request_key:'missing',record_id:'thermal_<script>',purpose:'results',state:'record_unavailable'},
  {...req,request_key:'waiting',state:'unfulfilled'}],answer:{checked_availability:[{request_key:'scope',state:'records_present'}]}});
 for(const text of ['可用性已核验','指定记录不可用','尚未交付','存在不等于结果有效','清单外问题'])assert.ok(html.includes(text));
 assert.ok(!html.includes('<script>')&&html.includes('&lt;script&gt;'));
 assert.equal(readRequestProgressMarkup({}), '');
});

test('read-scope editor uses labeled controls without requiring JSON',()=>{
 const html=readRequestMarkup();
 assert.ok(html.includes('添加读取目标')&&html.includes('关闭“允许计算”'));
 assert.ok(!html.includes('textarea')&&!html.includes('JSON'));
});

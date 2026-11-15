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

test('budget termination retains separate incomplete request state',()=>{
  const html=readRequestProgressMarkup({termination:{reason:'response_budget_exhausted'},
    read_request_progress:[{kind:'thermal',purpose:'results',request_key:'wall',record_id:'thermal_x',state:'unfulfilled'}]});
  assert.ok(html.includes('已到模型轮次上限') && html.includes('尚未交付'));
  assert.ok(!html.includes('全部任务已完成'));
});

test('user metric contract survives validation and cannot be empty or duplicated',()=>{
 const row={...req,purpose:'results',record_id:'thermal_'+'a'.repeat(32),output_contract:{fact_keys:['u_w_m2k'],explanation_topics:['area']}};
 assert.deepEqual(validateReadRequests([row],options)[0].output_contract,row.output_contract);
 for(const c of [{fact_keys:[],explanation_topics:[]},{fact_keys:['u_w_m2k','u_w_m2k'],explanation_topics:[]}])assert.throws(()=>validateReadRequests([{...row,output_contract:c}],options));
 assert.throws(()=>validateReadRequests([{...row,purpose:'availability'}],options));
});

test('explicit selector escapes source labels and separates availability topics',async()=>{
 const {explicitOutputMarkup}=await import('../src/agent-requests.js');
 const entry={facts:[{key:'x',label:'<script>bad</script>'}],topics:['meaning','period','scope']};
 const numeric=explicitOutputMarkup(entry,'results');
 assert.ok(numeric.includes('&lt;script&gt;')&&!numeric.includes('<script>'));
 assert.ok(numeric.includes('multiple')&&numeric.includes('最多12项'));
 const availability=explicitOutputMarkup(entry,'availability');
 assert.ok(!availability.includes('data-output-facts')&&availability.includes('记录历史边界'));
});

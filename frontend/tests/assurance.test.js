import test from 'node:test';
import assert from 'node:assert/strict';
import { weatherFacts, agentAssurance, importDiagnostics } from '../src/assurance-ui.js';
import { request, checkUpload, uploadLimitMB } from '../src/api.js';

test('weather facts preserve zero, null, source and invalid-source boundaries', () => {
  const html=weatherFacts([{name:'<script>bad</script>',kind:'epw',quality:{records:8760,full_year:true,duplicate_records:0,missing_records:0},annual:{temperature_c:0,solar_kwh_m2:null},source_hash:'abc123',options:{heating_base_c:18,cooling_base_c:26}}]);
  assert.match(html,/8,760/);assert.match(html,/<b>0<\/b>/);assert.match(html,/<b>—<\/b>/);assert.match(html,/abc123/);assert.match(html,/HDD18/);
  assert.ok(!html.includes('<script>'));
  const invalid=weatherFacts([{name:'old',invalid:true,error:'changed',annual:{temperature_c:999}}]);
  assert.ok(!invalid.includes('999'));assert.match(invalid,/来源失效/);
  assert.match(agentAssurance({tool_status:'succeeded',explanation_status:'invalid',explanation_error:'empty'}),/工程工具 <b>已完成/);
});

test('IFC diagnostics expose repair actions without inventing candidates',()=>{
  const html=importDiagnostics({import_id:'import_x',source:{hash:'abc'},diagnostics:{total:100,extracted:6,blocked:94,spaces:[{status:'blocked',global_id:'guid',name:'room',code:'MISSING_BODY',representations:[],action:'export Body',error:'<unsafe>'}]}},'/projects/p');
  assert.match(html,/94/);assert.match(html,/guid/);assert.match(html,/export Body/);assert.match(html,/report.json/);assert.ok(!html.includes('<unsafe>'));
});

test('upload policy follows server configuration and refuses oversized files before fetch',async t=>{
  let calls=0;
  t.mock.method(globalThis,'fetch',async()=>{calls++;return Response.json({upload_policy:{max_file_bytes:1024}});});
  await request('/health');assert.equal(uploadLimitMB(),1024/1024/1024);
  assert.doesNotThrow(()=>checkUpload({size:1024}));assert.throws(()=>checkUpload({size:0}),/非空/);
  const body=new FormData();body.set('file',new File([new Uint8Array(1025)],'large.ifc'));
  await assert.rejects(request('/projects/p/files',{method:'POST',body}),/超过服务端/);
  assert.equal(calls,1);
});

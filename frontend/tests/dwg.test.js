import test from 'node:test';
import assert from 'node:assert/strict';
import {conversionMarkup} from '../src/cad-ui.js';
const record={cad_id:'cad_'+'a'.repeat(32),status:'parsed',result:{},conversion:{engine:'ACadSharp 3.8.35',notifications:[{phase:'write',type:'NotImplemented',message:'<script>bad</script>'}]}};
test('DWG partial conversion retains escaped warnings and guarded download',()=>{
 const text=conversionMarkup(record,'/projects/p');
 assert.ok(text.includes('部分信息'));assert.ok(text.includes('NotImplemented'));
 assert.ok(text.includes('&lt;script&gt;'));assert.ok(!text.includes('<script>'));
 assert.ok(text.includes('/converted.dxf'));assert.ok(text.includes('不能代替原始工程图'));
});
test('invalidated DWG conversion withdraws download',()=>{
 for(const status of ['stale','unverified'])assert.ok(!conversionMarkup({...record,status,result:null},'/projects/p').includes('/converted.dxf'));
 assert.equal(conversionMarkup({status:'parsed'},'/projects/p'),'');
});

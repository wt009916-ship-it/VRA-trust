import test from 'node:test';
import assert from 'node:assert/strict';
import {standardQueryBody,standardResultMarkup,standardAgentMarkup,createStandardMonitor} from '../src/standard-results.js';
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const group=(code,clause,text='SYNTHETIC_QUOTE')=>({status:'CITATIONS_FOUND',query:{standard_code:code,edition:'2024',clause_id:clause},conflicts:[],excluded:[],total_matches:1,citations:[{standard_id:'standard_a',standard_code:code,edition:'2024',clause_id:clause,pdf_page:2,printed_page:'ii',title:'Synthetic <img>',text,scope:'Test <script>',jurisdiction:'TEST',source_url:'https://example.org/test',coverage:'excerpt'}]});
const batch={status:'PARTIAL_TARGETS_FOUND',notice:'Test only',targets:[group('TEST A','1.0.1'),{...group('TEST B','2.0.2'),status:'NOT_FOUND_IN_REVIEWED_INDEX',citations:[],total_matches:0}]};

test('batch submit never carries hidden single-query fields or loses target order',()=>{
 const body=standardQueryBody({mode:'batch',text:'stale search',standard_code:'WRONG',as_of:'2025-01-01'},[{standard_code:' TEST A ',edition:' ',clause_id:'1.0.1'},{standard_code:'TEST B',edition:'2024',clause_id:'2.0.2'}]);
 assert.deepEqual(body,{as_of:'2025-01-01',targets:[{key:'target_1',standard_code:'TEST A',edition:null,clause_id:'1.0.1'},{key:'target_2',standard_code:'TEST B',edition:'2024',clause_id:'2.0.2'}]});
 assert.throws(()=>standardQueryBody({mode:'batch'},[]));
 assert.throws(()=>standardQueryBody({mode:'batch'},[{standard_code:'',edition:'',clause_id:'1'}]));
});
test('partial results retain unmatched target and quote/page pairing; text is escaped',()=>{
 const html=standardResultMarkup(batch,'project_a');
 assert.match(html,/TEST A.*1.0.1/);assert.match(html,/TEST B.*2.0.2/);assert.match(html,/索引中未找到/);
 assert.match(html,/PDF第2页/);assert.match(html,/source.pdf#page=2/);
 assert.ok(html.includes('&lt;img&gt;')&&!html.includes('<img>')&&!html.includes('<script>'));
 assert.ok(!standardResultMarkup(null,'project_a').includes('SYNTHETIC_QUOTE'));
});
test('Agent current-state flag gates cached standard cards',()=>{
 const answer={standard_query_progress:[{query_index:1,state:'source_unverified'}],checked_standards:[{query_index:1,project_id:'project_a',result:batch}]};
 assert.ok(!standardAgentMarkup(answer).includes('SYNTHETIC_QUOTE'));
 answer.standard_query_progress[0].state='current';assert.ok(standardAgentMarkup(answer).includes('SYNTHETIC_QUOTE'));
});
test('late old response cannot restore quotes after selecting another query',async()=>{
 const pending=[],paints=[];
 const m=createStandardMonitor({fetchQuery:()=>new Promise(resolve=>pending.push(resolve)),paint:(r,msg)=>paints.push(r),isActive:()=>true});
 m.select('old');const a=m.refresh();m.select('new');const b=m.refresh();
 pending[1]({normquery_id:'new',status:'current'});await b;pending[0]({normquery_id:'old',status:'current'});await a;
 assert.equal(paints.at(-1).normquery_id,'new');assert.ok(!paints.some(r=>r?.normquery_id==='old'));m.stop();
});
test('stale, network failure, timeout and detached result never expose old quotes',async()=>{
 for(const type of ['stale','network','timeout','detached']){
  const paints=[];let active=true,resolve;
  const m=createStandardMonitor({timeoutMs:5,isActive:()=>active,paint:(r,msg)=>paints.push({r,msg}),fetchQuery:()=>type==='network'?Promise.reject(Error('offline')):new Promise(r=>resolve=r)});
  m.select('q');const task=m.refresh();
  if(type==='timeout')await delay(12);
  if(type==='detached')active=false;
  if(resolve)resolve({status:type==='stale'?'stale':'current',result:batch});
  await task;assert.ok(paints.every(p=>p.r===null));m.stop();
 }
});

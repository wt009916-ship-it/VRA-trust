import test from 'node:test';
import assert from 'node:assert/strict';
import {assistedClause} from '../src/standard-ocr.js';
const r={status:'review_required',normocr_id:'normocr_x',input:{page:5},result:{candidates:[{candidate_id:'text_1',text:'uncertain 0.5'},{candidate_id:'text_2',text:'next line'}]}};
test('assisted excerpt preserves selected line order and original page without confirming',()=>{
 assert.deepEqual(assistedClause(r,['text_2','text_1']),{ocr_id:'normocr_x',candidate_ids:['text_2','text_1'],pdf_page:5,transcription:'ocr_assisted',text:'next line\nuncertain 0.5'});
});
test('stale, missing and duplicate candidates cannot populate a clause',()=>{
 for(const [record,ids] of [[{...r,status:'stale',result:null},['text_1']],[r,[]],[r,['text_9']],[r,['text_1','text_1']]])assert.throws(()=>assistedClause(record,ids));
});

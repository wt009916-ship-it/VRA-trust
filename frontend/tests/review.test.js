import test from 'node:test';
import assert from 'node:assert/strict';
import {filterFindings,findingMarkup} from '../src/review-ui.js';
import {readRoute} from '../src/workspace-ui.js';

const issue={finding_id:'finding_'+'a'.repeat(24),kind:'BLOCKER',title:'<源楼层>：用途待核对',action:'补原图与用途',room_ids:['R1'],ifc_global_ids:['actual-ifc-guid'],storey_ids:['floor'],locator:'<source>',basis:null,review:null,prior_review_stale:true};
test('review findings search by actual IFC/room and retain stale items as pending',()=>{
  const done={...issue,kind:'ASSUMPTION',review:{note:'Accepted test condition',actor:'Reviewer',decision:'accepted_scenario'}};
  assert.equal(filterFindings([issue,done],{kind:'BLOCKER',query:'actual-ifc',pending:true}).length,1);
  assert.equal(filterFindings([issue,done],{pending:true}).length,1);
  assert.equal(filterFindings([issue],{query:'missing'}).length,0);
  assert.equal(filterFindings([{...issue,source_element_ids:['actual-column-source']}],{query:'actual-column'}).length,1);
});
test('review markup preserves refusal nature, location and safely escapes source text',()=>{
  const html=findingMarkup(issue);assert.ok(html.includes('旧复核已失效'));assert.ok(html.includes('定位空间'));
  assert.ok(html.includes('&lt;源楼层&gt;'));assert.ok(!html.includes('<source>'));assert.ok(!html.includes('已签署'));
  assert.deepEqual(readRoute('#project/project_'+'a'.repeat(32)+'/review'),{projectId:'project_'+'a'.repeat(32),view:'review'});
});

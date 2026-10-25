import test from 'node:test';
import assert from 'node:assert/strict';
import {filterProjects,projectRows,readRoute,dateLabel} from '../src/workspace-ui.js';

const p={project_id:'project_'+'a'.repeat(32),name:'<校园项目>',building:{location:'南昌',use:'学校',area_m2:200},pending_count:2,status:'review',evidence_count:2,run_count:0,updated_at:'2026-10-25T01:00:00Z',next_action:{view:'evidence',label:'核对资料'}};
test('project filters search location/use, handle attention and keep original order immutable',()=>{
  const projects=[p,{...p,project_id:'project_'+'b'.repeat(32),name:'医院',pending_count:0,status:'succeeded',building:{...p.building,area_m2:500}}];
  assert.equal(filterProjects(projects,{query:'南昌'}).length,2);
  assert.equal(filterProjects(projects,{filter:'attention'}).length,1);
  assert.equal(filterProjects(projects,{filter:'running'}).length,0);
  assert.equal(filterProjects(projects,{sort:'area'})[0].name,'医院');
  assert.equal(projects[0],p);
});
test('project records escape source names, distinguish reference and never invent results',()=>{
  const html=projectRows([p]);assert.ok(html.includes('&lt;校园项目&gt;'));assert.ok(!html.includes('<校园项目>'));assert.ok(html.includes('待复核'));assert.ok(!html.includes('kWh'));
});
test('routes restore only known project views and tolerate invalid bookmarks',()=>{
  assert.deepEqual(readRoute('#project/'+p.project_id+'/spatial'),{projectId:p.project_id,view:'spatial'});
  assert.equal(readRoute('#project/'+p.project_id+'/admin').projectId,null);
  assert.equal(readRoute('#tasks').view,'tasks');assert.equal(dateLabel('invalid'),'—');
});

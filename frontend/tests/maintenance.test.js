import test from 'node:test';
import assert from 'node:assert/strict';
import {maintenanceActions,maintenanceResult,readMaintenanceAction} from '../src/maintenance-ui.js';
test('work action sends explicit time and evidence, never a forged actor',()=>{
 const f=new FormData();for(const [k,v] of Object.entries({action:'record_work',note:'Declared repair note',responsible_person:'Human technician',work_completed_at:'2026-01-01T00:30:00Z',actor_user_id:'fake',after_operation_id:'unused'}))f.set(k,v);f.append('evidence_ids','evidence_a');
 const r=readMaintenanceAction(f,3);assert.equal(r.expected_revision,3);assert.equal(r.work_completed_at,'2026-01-01T00:30:00Z');assert.deepEqual(r.evidence_ids,['evidence_a']);assert(!('actor_user_id' in r));assert(!('after_operation_id' in r));
});
test('closure attestation is explicit and state choices do not skip verification',()=>{
 assert.deepEqual(maintenanceActions.open,['triage']);assert(!maintenanceActions.work_recorded.includes('close'));assert(maintenanceActions.rechecked.includes('close'));
 const f=new FormData();f.set('action','close');assert.equal(readMaintenanceAction(f,1).same_equipment_and_conditions,false);f.set('same_equipment_and_conditions','on');assert.equal(readMaintenanceAction(f,1).same_equipment_and_conditions,true);
});
test('stale result suppressed and external text escaped',()=>{
 const r={input:{name:'<script>bad</script>'},equipment:'<b>asset</b>',status:'stale',revision:5,data_nature:'synthetic',actions:[],recheck:{outcome:'no_violation_in_observed_window',observed_seconds:12345678,required_seconds:10,gaps:[]}};
 const html=maintenanceResult(r);assert(!html.includes('<script>'));assert(html.includes('&lt;script&gt;'));assert(html.includes('当前复验结论已撤下'));assert(!html.includes('12,345,678'));assert(!html.includes('本观测窗口未发现规则越限'));
});
test('remaining violation and incomplete coverage never display a health certificate',()=>{
 const html=maintenanceResult({input:{name:'Test'},equipment:'asset',status:'recheck_failed',revision:4,data_nature:'synthetic',actions:[],recheck:{outcome:'rule_violation_remains',observed_seconds:180,required_seconds:120,gaps:['source_quality_or_cadence']}});
 assert(html.includes('仍存在规则越限'));assert(html.includes('原始数据质量或采样间隔不符'));assert(html.includes('不证明设备健康'));
});

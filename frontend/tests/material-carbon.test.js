import test from 'node:test';
import assert from 'node:assert/strict';
import {readCarbonEditors,carbonBoundaryMarkup,evidenceSelect} from '../src/material-carbon-ui.js';

test('common boundaries stay explicit and do not invent activities',()=>{
 const data=new FormData();data.set('boundary_operation','on');data.set('boundary_reason_operation','Declared annual electricity over 30 years');
 const body=readCarbonEditors(data);
 assert.deepEqual(body.boundaries.filter(b=>b.included).map(b=>b.stage),['production','operation']);
 assert.equal(body.boundaries.find(b=>b.stage==='transport').reason,'');
 assert(body.alternatives.every(a=>a.other_activities.length===0&&a.transport_legs.length===0));
 assert(carbonBoundaryMarkup().includes('排除不等于零排放'));
});

test('transport uses selected layer references and explicit zeros, never client mass',()=>{
 const data=new FormData(),p='carbon_transport_1_12_';
 for(const [k,v] of Object.entries({id:'rail_leg',name:'Rail route',purchase_fraction:'0.5',distance:'250',additional_mass:'0',factor_value:'0.02',year:'2026',factor_id:'rail-2026'}))data.set(p+k,v);
 data.append(p+'layers','10');data.append(p+'layers','20');data.set(p+'source_evidence','evidence_route');data.set(p+'factor_evidence','evidence_factor');data.set(p+'shipped_mass_kg','999999');
 const body=readCarbonEditors(data),leg=body.alternatives[1].transport_legs[0];
 assert.equal(body.alternatives[0].transport_legs.length,0);
 assert.deepEqual(leg.layer_ids,[10,20]);assert.equal(leg.purchase_fraction,0.5);assert.equal(leg.additional_mass_kg,0);
 assert.equal(leg.factor.denominator,'tkm');assert.equal(leg.factor.evidence_id,'evidence_factor');assert.deepEqual(leg.evidence_ids,['evidence_route']);
 assert(!('shipped_mass_kg' in leg));
 data.delete(p+'additional_mass');assert.equal(readCarbonEditors(data).alternatives[1].transport_legs[0].additional_mass_kg,null);
});

test('activity carries annual quantity, source evidence and factor version without pre-multiplication',()=>{
 const data=new FormData(),p='carbon_activity_0_3_';
 for(const [k,v] of Object.entries({id:'electricity',name:'Electricity',stage:'operation',quantity:'100',unit:'kWh',period:'annual',denominator:'kWh',version:'v2026',factor_value:'0.4',factor_method:'QA arithmetic'}))data.set(p+k,v);
 data.append(p+'source_evidence','evidence_bill');data.append(p+'source_evidence','evidence_schedule');
 const a=readCarbonEditors(data).alternatives[0].other_activities[0];
 assert.equal(a.quantity,100);assert.equal(a.period,'annual');assert.equal(a.factor.stage,'operation');assert.equal(a.factor.version,'v2026');
 assert.deepEqual(a.source_evidence_ids,['evidence_bill','evidence_schedule']);
 data.set(p+'quantity','');data.set(p+'factor_value','');
 const missing=readCarbonEditors(data).alternatives[0].other_activities[0];assert.equal(missing.quantity,null);assert.equal(missing.factor.value,null);
});

test('evidence picker escapes imported labels and identifies revision without claiming certification',()=>{
 const html=evidenceSelect('source','Source',[{evidence_id:'a" onclick="bad',name:'<script>bad</script>',revision:3}],true);
 assert(!html.includes('<script>'));assert(html.includes('&lt;script&gt;'));assert(html.includes('v3'));assert(html.includes('multiple'));
});

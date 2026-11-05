import test from 'node:test';
import assert from 'node:assert/strict';
import {createBeamDraft} from '../src/beam-draft.js';

const project={project_id:'project_a', revision:2};
const sources=[{evidence_id:'source_a', revision:3, hash:'original', review_state:'confirmed'}];
const input={name:'梁 <A>', span:6, elastic_modulus:null, evidence_ids:['source_a'], loads:[{type:'point', magnitude:0}]};
function setup(clock){const drafts=createBeamDraft(clock);drafts.capture('owner',project,sources,input);return drafts;}
test('same owner resumes exact input once, without substituting unknowns or changing zero',()=>{
  const d=setup();assert.equal(d.target('owner'),'project_a');
  const result=d.take('owner',project,sources);assert.deepEqual(result,input);assert.notEqual(result,input);
  assert.equal(d.take('owner',project,sources),null);
});
test('different account irreversibly discards draft; later original account cannot recover it',()=>{
  const d=setup();assert.equal(d.target('other'),null);assert.equal(d.target('owner'),null);
});
test('different project or revised declaration refuses recovery',()=>{
  for(const p of [{...project,project_id:'project_b'},{...project,revision:3}])assert.equal(setup().take('owner',p,sources),null);
});
test('withdrawn, changed or missing evidence refuses recovery',()=>{
  for(const s of [[],[{...sources[0],revision:4}],[{...sources[0],hash:'changed'}],[{...sources[0],review_state:'rejected'}]])assert.equal(setup().take('owner',project,s),null);
});
test('draft expires at fifteen minutes and explicit logout/discard removes it',()=>{
  let time=100;const d=setup(()=>time);time+=15*60*1000-1;assert.equal(d.target('owner'),project.project_id);
  time++;assert.equal(d.target('owner'),null);const d2=setup();d2.clear();assert.equal(d2.target('owner'),null);
});
test('captured input is independent of later form mutations',()=>{
  const d=createBeamDraft();const value=structuredClone(input);d.capture('owner',project,sources,value);value.loads[0].magnitude=99;
  assert.equal(d.take('owner',project,sources).loads[0].magnitude,0);
});

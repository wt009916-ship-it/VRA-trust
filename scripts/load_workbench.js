import http from 'k6/http';
import { check, sleep } from 'k6';
import { SharedArray } from 'k6/data';
import { Rate, Trend, Counter } from 'k6/metrics';

const base=__ENV.VRA_LOAD_URL||'http://127.0.0.1:8895';
if(!/^http:\/\/127\.0\.0\.1:889[5-9]$/.test(base))throw Error('Use an isolated loopback load service on ports 8895–8899');
const fixture=JSON.parse(open(__ENV.VRA_LOAD_FIXTURE));
const users=new SharedArray('isolated sessions',()=>fixture.sessions);
const failure=new Rate('business_failures'),read=new Trend('workspace_read_ms'),write=new Trend('model_save_ms'),validation=new Trend('geometry_validation_ms'),writes=new Counter('successful_model_saves');
export const options={
  scenarios:{
    workspace:{executor:'ramping-vus',startVUs:1,stages:[{duration:'10s',target:5},{duration:'20s',target:5},{duration:'10s',target:10},{duration:'20s',target:10},{duration:'10s',target:20},{duration:'40s',target:20},{duration:'10s',target:0}],gracefulRampDown:'15s',exec:'workspace'},
    geometry:{executor:'constant-vus',vus:2,duration:'120s',exec:'geometry'},
  },
  thresholds:{business_failures:['rate<0.01'],workspace_read_ms:['p(95)<1500'],model_save_ms:['p(95)<2500'],geometry_validation_ms:['p(95)<10000'],successful_model_saves:['count>20']},
};
function config(u,name){return{headers:{Cookie:'vra_session='+u.cookie,'X-CSRF-Token':u.csrf,'Content-Type':'application/json'},tags:{name},timeout:'30s'};}
function record(r,metric,label){metric.add(r.timings.duration);const ok=check(r,{[label]:r=>r.status===200});failure.add(!ok);return ok;}
export function workspace(){
  const u=users[(__VU-1)%users.length],pid=u.project_id;
  for(const route of ['/api/workspace','/api/projects/'+pid,'/api/projects/'+pid+'/model','/api/projects/'+pid+'/runs','/api/auth/security']){
    record(http.get(base+route,config(u,route.replace(pid,':project'))),read,'authenticated read 200');
  }
  if(__ITER%5===0){
    const r=http.get(base+'/api/projects/'+pid+'/model',config(u,'model before write'));
    if(record(r,read,'fresh model 200')){
      const model=r.json(),data={};for(const key of fixture.draft_fields)if(key in model)data[key]=model[key];
      data.expected_revision=model.revision;data.review_note='Isolated load save; public IFC geometry unchanged';
      const saved=http.put(base+'/api/projects/'+pid+'/model',JSON.stringify(data),config(u,'model save'));
      if(record(saved,write,'model save 200'))writes.add(1);
    }
  }
  sleep(0.5);
}
export function geometry(){
  const u=users[(__VU-1)%users.length];
  const r=http.get(base+'/api/projects/'+u.project_id+'/model/validate',config(u,'thermal geometry validation'));
  if(record(r,validation,'geometry response 200')){
    const b=r.json();failure.add(!check(b,{'independent geometry audit present':b=>b.geometry_review?.independent_audit?.passed===true}));
  }
  sleep(2);
}
export function handleSummary(data){return{[__ENV.VRA_LOAD_RESULT||'load-result.json']:JSON.stringify(data,null,2)};}

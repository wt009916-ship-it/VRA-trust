import http from 'k6/http';
import { check } from 'k6';
import { Counter, Trend } from 'k6/metrics';

const base=__ENV.VRA_LOAD_URL||'http://127.0.0.1:8895';
if(!/^http:\/\/127\.0\.0\.1:889[5-9]$/.test(base))throw Error('Authentication admission test requires an isolated load service');
const accepted=new Counter('credential_failures'),limited=new Counter('admission_denials'),serverErrors=new Counter('server_errors'),health=new Trend('health_during_auth_ms');
export const options={scenarios:{burst:{executor:'shared-iterations',vus:20,iterations:100,maxDuration:'60s'}},thresholds:{checks:['rate==1'],server_errors:['count==0'],admission_denials:['count>0'],health_during_auth_ms:['p(95)<2000']}};
export default function(){
  const r=http.post(base+'/api/auth/login',JSON.stringify({username:'load_engineer_'+String(__VU%22).padStart(3,'0'),password:'Deliberately-wrong-load-fixture-password!'}),{headers:{'Content-Type':'application/json'},responseCallback:http.expectedStatuses(401,429)});
  if(r.status===401)accepted.add(1);else if(r.status===429)limited.add(1);else serverErrors.add(1);
  check(r,{'failed credentials or explicit admission denial':r=>[401,429].includes(r.status),'never issue session for invalid credentials':r=>!r.headers['Set-Cookie']});
  const h=http.get(base+'/api/health');health.add(h.timings.duration);check(h,{'health remains available':r=>r.status===200});
}
export function handleSummary(data){return{[__ENV.VRA_LOAD_RESULT||'load-auth-result.json']:JSON.stringify(data,null,2)};}

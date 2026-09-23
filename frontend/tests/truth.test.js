import test from 'node:test';
import assert from 'node:assert/strict';
import { escape, number, latestSchemes, resultValue, comparisonIsCurrent } from '../src/api.js';
import { authView, appShell } from '../src/layout.js';
test('missing, NaN and strings never become zero', () => {
  for (const x of [null, undefined, NaN, Infinity, '1']) assert.equal(number(x), '—');
  assert.equal(number(0), '0');
});
test('failed and stale cached metrics are suppressed', () => {
  for (const status of ['failed','stale','queued','running']) assert.equal(resultValue({status, metrics:{annual_energy_kwh:123}}, 'annual_energy_kwh'), null);
  assert.equal(resultValue({status:'succeeded',metrics:{annual_energy_kwh:0}},'annual_energy_kwh'),0);
});
test('latest scheme choice does not fall back to previous success', () => {
  const runs=[{scheme_id:'R1',status:'failed'},{scheme_id:'R1',status:'succeeded'}];
  assert.equal(latestSchemes(runs)[0].status,'failed');
});
test('untrusted evidence text is escaped', () => assert.equal(escape('<img onerror="x">'), '&lt;img onerror=&quot;x&quot;&gt;'));
test('account and project names cannot inject workspace markup', () => {
  const html = appShell({user:{display_name:'<img onerror="x">'},projects:[{project_id:'project_1',name:'<script>bad</script>'}],project:null});
  assert.ok(!html.includes('<img'));
  assert.ok(!html.includes('<script>bad'));
  assert.ok(html.includes('&lt;script&gt;bad'));
});
test('login fields use password autocomplete and valid HTML username pattern', () => {
  const login = authView({});
  assert.ok(login.includes('type="password"'));
  assert.ok(login.includes('autocomplete="current-password"'));
  assert.ok(authView({setup:true}).includes('autocomplete="new-password"'));
  const pattern = login.match(/pattern="([^"]+)"/)[1];
  const valid = new RegExp('^(?:'+pattern+')$', 'v');
  assert.equal(valid.test('my-user_2'), true);
  assert.equal(valid.test('invalid name'), false);
});
test('comparison survives stale history but not changed participants or a newer run', () => {
  const runs = [
    {run_id:'r2', scheme_id:'R2', status:'succeeded'},
    {run_id:'r1', scheme_id:'R1', status:'succeeded'},
    {run_id:'b', scheme_id:'baseline', status:'succeeded'},
    {run_id:'old', scheme_id:'baseline', status:'stale'}
  ];
  const ids = ['b','r1','r2'];
  assert.equal(comparisonIsCurrent(runs, ids), true);
  assert.equal(comparisonIsCurrent(runs.map(r => r.run_id === 'b' ? {...r,status:'stale'} : r), ids), false);
  assert.equal(comparisonIsCurrent([{run_id:'new',scheme_id:'R2',status:'queued'}, ...runs], ids), false);
  assert.equal(comparisonIsCurrent(runs.filter(r => r.run_id !== 'r1'), ids), false);
});

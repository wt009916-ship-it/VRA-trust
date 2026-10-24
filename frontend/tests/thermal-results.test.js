import test from 'node:test';
import assert from 'node:assert/strict';
import { thermalResults } from '../src/thermal-results.js';

test('thermal result hides stale output and distinguishes equipment from demand',()=>{
  const run={status:'succeeded',warnings_count:0,metrics:{hvac_scope:'packaged_heat_pump_electricity',end_uses_kwh:{Fans:{Electricity:0}},comfort_hours:{'Time Setpoint Not Met During Occupied Heating / Facility':27}}};
  assert.equal(thermalResults({...run,status:'stale'}),'');
  const markup=thermalResults(run);
  assert.match(markup,/定容热泵/);
  assert.match(markup,/27/);
  assert.match(markup,/<td>—<\/td>/);
  assert.match(markup,/容量与舒适性/);
  assert.match(thermalResults({...run,metrics:{hvac_scope:'ideal_thermal_loads'}}),/不代表空调耗电/);
});

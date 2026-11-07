import test from 'node:test';
import assert from 'node:assert/strict';
import {checkedDeliveryMarkup, modelCommentaryMarkup} from '../src/agent-artifacts.js';

test('current native delivery displays coverage separately and reuses original load rows', () => {
  const html = checkedDeliveryMarkup({simulation_artifact: {
    run_id: 'run_test', status: 'succeeded', verified: true, metrics: {annual_energy_kwh: 1200, area_m2: 100, eui_kwh_m2a: 12,
      zone_design_loads: {status: 'calculated_model_scenario', rows: [{zone_name: '<img src=x onerror=alert(1)>', load_type: 'Heating',
        calculated_sensible_load_W: 1542, user_adjusted_sensible_load_W: 1600, peak: null}]}}},
    sizing_read_progress: {state: 'partial', read_rows: 5, total_rows: 10}});
  assert.match(html, /5 \/ 10/); assert.match(html, /仍有未读行/); assert.match(html, /1\.542/);
  assert.match(html, /原生运行/); assert.match(html, /report\.html/); assert.ok(!html.includes('<img'));
});

test('stale state suppresses even accidentally retained historical numeric payload', () => {
  const html = checkedDeliveryMarkup({simulation_artifact: {status: 'stale', verified: true,
    metrics: {annual_energy_kwh: 987654321, zone_design_loads: {rows: [{zone_name: 'old-secret-row'}]}}}});
  assert.match(html, /未显示历史数值/); assert.ok(!html.includes('987654321') && !html.includes('old-secret-row'));
  assert.ok(!modelCommentaryMarkup({llm_commentary_policy: 'audit_only', llm_commentary: 'Invented total'}).includes('Invented total'));
});

import test from 'node:test';
import assert from 'node:assert/strict';
import {levelingMarkup} from '../src/schedule-leveling.js';

function record(){return {calculation_type:'resource_leveling',status:'calculated',result:{leveled:{schedule:{duration_days:'6.5',cpm_duration_days:'3.5',delay_vs_cpm_days:'3',rows:[{task_id:'A',name:'<img src=x onerror=alert(1)>',start_day:'0',finish_day:'2',start_delay_days:'0'}],resource_peaks:[{resource_id:'crew',peak_units:'2',capacity_units:'2'}]},lower_bound:{days_floor_6dp:'3.5',attained:false}}}};}
test('Nonoptimal feasible schedule shows dates, lower bound and lack of proof',()=>{const html=levelingMarkup(record());assert.match(html,/6.5/);assert.match(html,/尚未证明全局最优/);assert.match(html,/不是现场可施工证明/);assert.doesNotMatch(html,/<img/);assert.match(html,/&lt;img/);});
test('Stale results do not render old derived numbers even with a hostile stale payload',()=>{const r=record();r.status='stale';const html=levelingMarkup(r);assert.doesNotMatch(html,/6.5/);assert.match(html,/已撤下历史排程数值/);});
test('Budget exhaustion does not become feasible or zero',()=>{const r=record();r.result.leveled={schedule:null,reasons:['execution_budget_exhausted']};const html=levelingMarkup(r);assert.match(html,/达到预算/);assert.doesNotMatch(html,/满足声明容量|<strong>0/);});
test('Bound equality is qualified by declared model; original CPM gets no derived card',()=>{const r=record();r.result.leveled.lower_bound.attained=true;assert.match(levelingMarkup(r),/仅在声明模型内证明最短/);assert.equal(levelingMarkup({status:'calculated',result:{planned:{duration_days:'7'}}}),'');});

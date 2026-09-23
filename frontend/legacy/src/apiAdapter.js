import { finiteOrNull, safeObject } from './safety.js'
const statusMap = {success:'succeeded', succeeded:'succeeded', pending:'queued', queued:'queued', running:'running', failed:'failed', stale:'stale'}
export function normalizeExternalResult(raw = {}) {
  const sim=raw.simulation || raw
  const status=statusMap[sim.status] || 'failed'
  const meta={run_id:sim.run_id || null,status,source:sim.source || '外部导入，未由本机核验',error:sim.error || (status==='failed'?{message:'未知或失败的结果状态'}:null)}
  const plans=raw.plans ?? raw.result?.plans
  if(status!=='succeeded'||!Array.isArray(plans)||plans.length===0||!meta.run_id) return {mode:'live',meta,dashboard:null,missing:[],hasResults:false}
  const normalized=plans.map(p=>({
    ...p,energy:Object.fromEntries(['annual_cooling_kWh','annual_heating_kWh','intensity_kWh_m2a','saving_rate_pct'].map(k=>[k,finiteOrNull(p.energy?.[k])])),
    carbon:{annual_operation_tCO2:finiteOrNull(p.carbon?.annual_operation_tCO2),lca_total_tCO2:null},
    carbon_stages_tCO2:null,ccer:{annual_reduction_tCO2:null,price_yuan_t:null,annual_value_yuan:null,total_10y_yuan:null},
    recommend_tag:'导入结果，待核验'
  }))
  return {mode:'live',meta,dashboard:safeObject({building:raw.building || {},plans:normalized,charts:{},all_schemes_for_switching:[]}),missing:['完整LCA','正式碳信用'],hasResults:true}
}
export function comparisonToDashboard(comparison, caseInfo) {
  if(comparison.schema_version!=='vra.compare.v2'||!Array.isArray(comparison.results)||comparison.results.some(r=>r.status!=='succeeded'))throw new Error('比较结果未通过验证')
  const plans=comparison.results.map(r=>{
    const s=caseInfo.schemes.find(s=>s.scheme_id===r.scheme_id)
    if(!s)throw new Error('方案不在当前案例中')
    const energy=r.metrics;const carbon=r.carbon
    if(finiteOrNull(energy.annual_energy_kwh)==null||finiteOrNull(energy.area_m2)==null||energy.area_m2<=0)throw new Error('关键指标不合法')
    return {plan_label:r.scheme_id,scheme_id:r.scheme_id,scheme_name:r.scheme_name,thickness_mm:s.added_insulation_mm,layers:s.construction_layers,u_value:s.u_value_scenario,material_key:null,
      energy:{annual_total_kWh:energy.annual_energy_kwh,intensity_kWh_m2a:energy.eui_kwh_m2a,saving_rate_pct:r.saving_rate_pct,annual_cooling_kWh:null,annual_heating_kWh:null},
      cost:{},carbon:{annual_operation_tCO2:carbon.operating_carbon_kg==null?null:carbon.operating_carbon_kg/1000,lca_total_tCO2:null},carbon_stages_tCO2:null,
      ccer:{annual_reduction_tCO2:null,annual_value_yuan:null,total_10y_yuan:null,price_yuan_t:null},recommend_tag:carbon.scenario?'真实仿真／碳因子假设':'真实仿真／参考算例',run_id:r.run_id}
  })
  return safeObject({schema_version:'vra.dashboard.v2',building:{name:caseInfo.name,building_id:caseInfo.case_id,city:caseInfo.region,area_m2:comparison.results[0].metrics.area_m2,geometry_note:'外观为历史示意；构造层来自参考IDF，非现场建筑模型'},plans,charts:{},all_schemes_for_switching:[]})
}

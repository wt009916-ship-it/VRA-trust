// 独立数据适配层：把外部仿真结果（龚）转成现有页面使用的 dashboard 结构
// 约定：接口没有的碳收益（ccer）与 LCA 值不做任何自动推算，只保留 null 并登记 missing

const RUN_STATUS = ['queued', 'running', 'failed', 'success']

function pickStatus(raw) {
  const s = raw?.simulation?.status ?? raw?.status ?? raw?.run_status
  if (typeof s === 'string' && RUN_STATUS.includes(s.toLowerCase())) {
    return s.toLowerCase()
  }
  return 'queued'
}

function nullCcer() {
  return {
    annual_reduction_tCO2: null,
    price_yuan_t: null,
    annual_value_yuan: null,
    total_10y_yuan: null
  }
}

function nullCarbon(carbon) {
  return {
    ...(carbon || {}),
    annual_operation_tCO2: carbon?.annual_operation_tCO2 ?? null,
    lca_total_tCO2: carbon?.lca_total_tCO2 ?? null
  }
}

export function normalizeExternalResult(raw = {}) {
  const sim = raw.simulation || {}
  const meta = {
    run_id: sim.run_id ?? raw.run_id ?? null,
    status: pickStatus(raw),
    source: sim.source ?? raw.source ?? null,
    submitted_at: sim.submitted_at ?? raw.submitted_at ?? null,
    finished_at: sim.finished_at ?? raw.finished_at ?? null,
    error: sim.error ?? raw.error ?? null
  }

  const plansRaw = raw.plans ?? raw.results?.plans ?? raw.result?.plans ?? null
  const chartsRaw = raw.charts ?? raw.results?.charts ?? raw.result?.charts ?? null
  const buildingRaw = raw.building ?? raw.results?.building ?? raw.result?.building ?? null
  const missing = []

  let dashboard = null
  if (Array.isArray(plansRaw)) {
    const plans = plansRaw.map(p => {
      const label = p.plan_label ?? p.scheme_id ?? '?'
      if (p.ccer == null) missing.push(`plans[${label}].ccer`)
      if (p.carbon == null || p.carbon.lca_total_tCO2 == null) {
        missing.push(`plans[${label}].carbon.lca_total_tCO2`)
      }
      return {
        ...p,
        ccer: p.ccer ?? nullCcer(),
        carbon: nullCarbon(p.carbon)
      }
    })

    dashboard = {
      schema_version: raw.schema_version ?? 'external_v1',
      building: buildingRaw || {},
      plans,
      charts: chartsRaw || {},
      all_schemes_for_switching: raw.all_schemes_for_switching ?? []
    }
  }

  return {
    mode: 'live',
    meta,
    dashboard,
    missing,
    // 状态未成功或没有结果体时，页面只显示状态，不沿用上一次成功数值
    hasResults: meta.status === 'success' && dashboard != null
  }
}

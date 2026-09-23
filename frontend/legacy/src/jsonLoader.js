import { state, SCENE_CONFIG } from './config.js'
import { bindCarbonTooltip } from './tooltip.js'
import { initCharts, updateCharts, updateHomeCharts, updateDetailWaterfall, showHomeWaterfallStages, showDetailWaterfallStages, clearCharts } from './charts.js'
import { buildBuilding, BUILDING_GEO } from './building.js'
import jsonData from '../../../fixtures/demo/frontend-data/data.json'
import { buildLayers, getPlans, getAllSchemes, getBuildingInfo, resolveBuildingGeo } from './data.js'
import { initHome, renderHome } from './home.js'
import { initDetail, renderDetail } from './detail.js'
import constructionLib from '../../../fixtures/demo/frontend-data/construction_lib_final.json'
import { normalizeExternalResult } from './apiAdapter.js'
import { safeObject } from './safety.js'
import { updateRunStatusUI, clearRunOutputs } from './runStatus.js'

// ===================== 安全工具函数 =====================

/** 把任意值安全转成数字，转不了就返回 fallback */
function toNum(val, fallback = 0) {
  const n = Number(val)
  return isNaN(n) ? fallback : n
}

/** 安全调用 toFixed，如果值不是数字就返回 '-' */
function toFixedSafe(val, digits = 1) {
  const n = Number(val)
  return isNaN(n) ? '-' : n.toFixed(digits)
}

let _currentJSON = null  // 模块私有，不直接暴露

export function switchJSONScheme(index) {
  if (_currentJSON) {
    loadFromJSON(_currentJSON, index)
    return true
  }
  return false
}

export function hasExternalJSON() {
  return _currentJSON !== null
}

// ===================== 材质外观库 =====================
const MATERIAL_LIBRARY = {
  '饰面层':     { color: 0xE8E8E8, roughness: 0.06, metalness: 0.25, clearcoat: 0.4 },
  '保温层':     { color: 0x9cf8bb, roughness: 0.5,  metalness: 0.1,  transparent: true, opacity: 0.75, minThickness: 0.02, maxThickness: 0.20, step: 0.01 },
  '基层':       { color: 0x8B7355, roughness: 0.95, metalness: 0.05 },
  '混凝土基层': { color: 0x707070, roughness: 0.95, metalness: 0.05 },
  '外墙饰面层': { color: 0xf8f8f8, roughness: 0.06, metalness: 0.25, clearcoat: 0.4 },
}

function hexToNumber(hex) {
  if (!hex) return 0x999999
  return parseInt(hex.replace('#', ''), 16)
}

// 几何来源：后端动态 JSON 优先，静态 BUILDING_GEO 兜底
function resolveGeometrySource(json) {
  // 1. 动态：JSON 自带建筑几何（和 geo/ 文件结构一致）
  if (Array.isArray(json.walls) && json.walls.length > 0) {
    return { geo: json, source: 'dynamic' }
  }
  // 2. 静态：building_id 直接匹配
  if (json.building_id && BUILDING_GEO[json.building_id]) {
    return { geo: BUILDING_GEO[json.building_id], source: 'static' }
  }
  // 3. 静态：project_info.building_type 映射
  const typeAlias = {
    office: 'office',
    dorm: 'dorm',
    dormitory: 'dorm',
    school: 'school',
    teaching: 'school'
  }
  const key = typeAlias[json.project_info?.building_type]
  if (key && BUILDING_GEO[key]) {
    return { geo: BUILDING_GEO[key], source: 'static' }
  }
  return null
}

// ===================== 核心：解析JSON并渲染 =====================
export function loadFromJSON(json, schemeIndex = 0) {
  _currentJSON = json

  // 几何来源：动态 JSON 优先，找不到才用静态表
  const geomSource = resolveGeometrySource(json)
  const geo = geomSource ? geomSource.geo : BUILDING_GEO.office
  state.geometrySource = geomSource ? geomSource.source : 'static'
  state.currentBuildingType = json.project_info?.building_type || geo.building_id || 'office'

  // 方案数据：导入 JSON 有 schemes 就用它，否则用内置 data.json 兜底
  const schemeSource = json.schemes?.length ? json : jsonData
  const scheme = schemeSource.schemes[schemeIndex] || schemeSource.schemes[0]
  if (!scheme?.construction?.layers) {
    console.error('JSON 结构不完整，缺少 schemes/construction/layers')
    alert('JSON 文件格式错误，缺少必要的构造层数据')
    return
  }

  const layers = scheme.construction.layers
    .slice()
    .reverse()
    .map(l => {
      const look = MATERIAL_LIBRARY[l.name] || {}
      if (l.thickness === undefined) {
        l.thickness = l.thickness_mm / 1000
      }
      l.lambda = l.lambda_W_mK
      l.price = l.price_yuan_m2
      l.color = l.color_hex ? hexToNumber(l.color_hex) : (look.color || 0x999999)
      l.roughness = look.roughness ?? 0.5
      l.metalness = look.metalness ?? 0.1
      l.density = l.density_kg_m3
      if (look.transparent) {
        l.transparent = true
        l.opacity = look.opacity
        l.depthWrite = false
      }
      if (look.clearcoat !== undefined) l.clearcoat = look.clearcoat
      if (look.minThickness !== undefined) {
        l.minThickness = look.minThickness
        l.maxThickness = look.maxThickness
        l.step = look.step
      }
      return l
    })

  // 更新state
  state.layers = layers
  state.heatLayerIndex = layers.findIndex(l => l.is_insulation || l.name === '保温层')
  state.totalThickness = layers.reduce((s, l) => s + l.thickness, 0)
  state.currentSchemeIndex = schemeIndex

    state.entranceProgress = 0

  buildBuilding(geo)
  // 重建UI
  if (typeof createLayerToggles === 'function') createLayerToggles()
  if (typeof updateSlider === 'function') updateSlider()
  updateCharts(json)
  fillExtraInfo(json, scheme)

  // ========== 新增：同步方案按钮高亮状态 ==========
  document.querySelectorAll('.scheme-btn').forEach((btn, i) => {
    btn.style.background = i === schemeIndex ? '#21aba5' : '#f8fafc'
    btn.style.color = i === schemeIndex ? '#fff' : '#1e293b'
  })

  console.log('✅ JSON方案加载完成:', scheme.scheme_name)
}

// ===================== 拖入文件支持 =====================
export function initDragDrop() {
  window.addEventListener('dragover', e => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'copy'
  })
  
  window.addEventListener('drop', e => {
    e.preventDefault()
    const file = e.dataTransfer.files[0]
    if (!file || !file.name.endsWith('.json')) {
      alert('请拖入 .json 文件')
      return
    }
    
    const reader = new FileReader()
    reader.onload = ev => {
      try {
        const json = JSON.parse(ev.target.result)
        if (json?.simulation || json?.run_id || json?.status) {
          loadRunResult(json)
        } else {
          state.dataMode = 'demo'
          state.validatedComparison = null
          state.runMeta = null
          updateRunStatusUI(null)
          loadDashboard(safeObject(json), 'A')
        }
      } catch (err) {
        alert('JSON解析失败: ' + err.message)
        console.error(err)
      }
    }
    reader.readAsText(file)
  })
  
  // 暴露到全局方便控制台测试
  window.loadJSON = (json, idx) => { state.dataMode='demo';state.validatedComparison=null;state.runMeta=null;return loadDashboard(safeObject(json), 'A') }
  window.loadRunResult = json => loadRunResult(json)
  console.log('💡 提示：可在控制台执行 loadJSON({...}) 测试')
}

// ===================== 外部仿真结果入口（龚的接口字段） =====================
export function loadRunResult(raw) {
  state.validatedComparison = null
  const res = normalizeExternalResult(raw)
  state.dataMode = 'live'
  state.runMeta = res.meta
  updateRunStatusUI(res.meta)

  if (res.hasResults) {
    clearCharts()
    _currentJSON = res.dashboard
    loadDashboard(res.dashboard, 'A')
    console.log('[run] results loaded', res.meta.run_id, 'missing:', res.missing)
  } else {
    // queued / running / failed：清空上一次成功数值与旧推荐语
    state.dashboardData = null
    state.layers = []
    state.validatedComparison = null
    _currentJSON = null
    document.querySelectorAll('#home-cards, #drawer-schemes').forEach(el => el.replaceChildren())
    clearRunOutputs(res.meta)
  }
  return res
}

// ===================== 新版 dashboard 数据入口 =====================

let _homeInited = false
let _detailInited = false
let _chartsInited = false

export function getCurrentJSON() {
  return _currentJSON
}

// A/B/C 用 plans，S0-S5 用 all_schemes_for_switching
function resolvePlan(json, key) {
  const found = getPlans(json).find(p => p.plan_label === key)
  if (found) return found

  const scheme = getAllSchemes(json).find(s => s.scheme_id === key)
  if (scheme) return schemeToPlan(scheme)

  return getPlans(json)[0]
}

function schemeToPlan(s) {
  return {
    plan_label: s.scheme_id,
    scheme_id: s.scheme_id,
    scheme_name: s.scheme_name,
    material_key: s.material_key,
    thickness_mm: s.thickness_mm,
    u_value: s.u_value,
    energy: s.energy,
    cost: s.cost,
    carbon: s.carbon,
    carbon_stages_tCO2: s.carbon_stages_tCO2,
    ccer: s.ccer,
    recommend_tag: s.scheme_id === 'S0' ? '基准' : ''
  }
}

export function loadDashboard(json = jsonData, planKey = 'A') {
  _currentJSON = json
  state.dashboardData = json
  state.constructionLib = constructionLib

  const plan = resolvePlan(json, planKey)
  if (!plan) return false

  const building = getBuildingInfo(json)
  const geoRes = resolveBuildingGeo(building, json, BUILDING_GEO)
  state.geometrySource = geoRes.source
  state.currentBuildingType = building.building_id || building.building_type || 'office'

  state.layers = buildLayers(plan, constructionLib)
  state.heatLayerIndex = state.layers.findIndex(l => l.is_insulation)
  state.totalThickness = state.layers.reduce((s, l) => s + l.thickness, 0)
  state.currentPlanKey = plan.plan_label
  state.currentSchemeId = plan.scheme_id

  buildBuilding(geoRes.geo)

  if (!_homeInited) {
    initHome(json)
    _homeInited = true
  } else {
    renderHome(json, plan.plan_label)
  }

  if (!_detailInited) {
    initDetail(json)
    _detailInited = true
  } else {
    renderDetail(json, plan.plan_label)
  }

  // 图表容器创建后再初始化 ECharts，并同步数据
  if (!_chartsInited) {
    initCharts()
    _chartsInited = true
  }

  // 雷达/柱状走 dashboard charts，瀑布统一用方案自身五阶段数据
  updateHomeCharts(json, plan.plan_label)
  
  renderHome(json, plan.plan_label)
  renderDetail(json, plan.plan_label)
  updateRunStatusUI(state.runMeta)

  return true
}

// 安全设置文本的工具函数
function setText(id, text) {
  const el = document.getElementById(id)
  if (el) el.textContent = text
}

// 数字计数动画（easeOutCubic）
function animateValue(id, target, decimals = 0, suffix = '', duration = 800) {
  const el = document.getElementById(id)
  if (!el) return
  if (isNaN(target)) {
    el.textContent = '-' + suffix
    return
  }
  const start = performance.now()
  function easeOutCubic(t) {
    return 1 - Math.pow(1 - t, 3)
  }
  function update(now) {
    const progress = Math.min((now - start) / duration, 1)
    const eased = easeOutCubic(progress)
    const current = target * eased
    let text
    if (decimals === 0 && Number.isInteger(target)) {
      text = Math.round(current).toLocaleString()
    } else {
      text = current.toFixed(decimals)
    }
    el.textContent = text + suffix
    if (progress < 1) requestAnimationFrame(update)
  }
  requestAnimationFrame(update)
}

// 填充JSON带来的额外信息
function fillExtraInfo(json, scheme) {
  // --- 1. 项目信息 ---
  const proj = json.project_info
  if (proj) {
    const box = document.getElementById('project-info')
    if (box) {
      box.style.display = 'block'
      setText('proj-city', proj.city || '-')
      const typeMap = {
        office: '办公楼',
        school: '教学楼',
        dormitory: '宿舍楼',
        hospital: '医院',
        commercial: '商业建筑'
      };
      setText('proj-type', typeMap[proj.building_type] || (proj.building_type || '-'));
      setText('proj-area', (proj.area_m2 || 0).toLocaleString())
      setText('proj-life', proj.lifespan_years ?? '-')
      const budgetNum = toNum(proj.budget_yuan, -1)
      setText('proj-budget', budgetNum >= 0 ? (budgetNum / 10000).toFixed(0) : '-')
      setText('proj-target', proj.energy_target_pct ?? '-')
      setText('proj-pref', proj.material_pref ?? '-')
    }
  }

  // --- 2. 物理参数 ---
  const c = scheme.construction
  if (c) {
    const phys = document.getElementById('physics-card')
    if (phys) phys.style.display = 'block'
    animateValue('physics-k', c.wall_K_value, 2, ' W/(㎡·K)')
    animateValue('physics-thick', c.total_thickness_mm ?? 0, 0, ' mm')
    animateValue('physics-cost', c.cost_yuan_m2 ?? 0, 0, ' 元/㎡')
  }

  // --- 2.5 能耗数据 ---
  const e = scheme.energy
  if (e) {
    animateValue('physics-energy-m2', e.annual_total_kWh_m2, 1, ' kWh/(㎡·年)')
    animateValue('physics-energy-total', e.annual_total_kWh ?? 0, 0, ' kWh')
    setText('energy-cool', (e.annual_cooling_kWh ?? 0).toLocaleString())
    setText('energy-heat', (e.annual_heating_kWh ?? 0).toLocaleString())
  }

  // --- 3. 碳排放阶段条 ---
  const phases = scheme.carbon?.phases
  if (phases) {
    const box = document.getElementById('carbon-phases')
    const bars = document.getElementById('carbon-bars')
    if (box && bars) {
      box.style.display = 'block'
      const total = Object.values(phases).reduce((a, b) => a + b, 0)
      const gradients = [
        'linear-gradient(90deg, #1f7974, #21aba5)',
        'linear-gradient(90deg, #21aba5, #42b899)',
        'linear-gradient(90deg, #42b899, #64d4a0)',
        'linear-gradient(90deg, #64a89e, #94a3b8)',
        'linear-gradient(90deg, #94a3b8, #cbd5e1)'
      ]
      const keys = ['A1_A3_production', 'A4_transport', 'A5_construction', 'B1_B7_operation', 'C1_C4_demolition']
      const labels = ['生产', '运输', '施工', '运营', '拆除']
      
      bars.innerHTML = keys.map((k, i) => {
        const v = phases[k] || 0
        const pct = total > 0 ? (v / total * 100).toFixed(1) : 0
        const tipText = `${labels[i]}: ${(v/1000).toFixed(1)} tCO₂ (${pct}%)`
                return `<div class="carbon-bar-segment" data-tip="${tipText}" style="flex:${pct}; background:${gradients[i]}; cursor:pointer;"></div>`
      }).join('')

      // 绑定自定义 tooltip
      bindCarbonTooltip(bars)
    }
  }

    // 碳排放汇总数据
  const carb = scheme.carbon
  if (carb) {
    setText('carbon-total', '全周期总排放 ' + ((carb.total_kgCO2 ?? 0) / 1000).toFixed(1) + ' tCO₂')
    animateValue('carbon-saving', carb.carbon_saving_vs_baseline_pct, 1, '')
    setText('carbon-per-m2', toFixedSafe(carb.per_m2_kgCO2, 0))
  }

  // CCER 明细
  const ccer = scheme.ccer
  if (ccer) {
    animateValue('ccer-annual', ccer.annual_reduction_tCO2 ?? 0, 0, '')
    setText('ccer-price', ccer.price_yuan_per_ton ?? '-')
  }

  // --- 4. 智能推荐 ---
  const rec = json.comparison?.recommendation
  if (rec) {
    const box = document.getElementById('recommendation-box')
    if (box) {
      box.style.display = 'block'
      setText('rec-best', rec.best_scheme || 'C')
      setText('rec-payback', rec.payback_years ?? '-')
      const reasonEl = document.getElementById('rec-reason')
      if (reasonEl) reasonEl.textContent = rec.reason || ''
    }
  }
}

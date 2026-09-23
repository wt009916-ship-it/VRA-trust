import dashboardData from '../../../fixtures/demo/frontend-data/dashboard_data.json'
import constructionLib from '../../../fixtures/demo/frontend-data/construction_lib_final.json'

// 当前前端所有数值均来自本地静态 JSON，用于仿真验收时区分演示数据
export const DATA_SOURCE_FLAG = {
  label: '演示数据',
  demo: true,
  files: ['dashboard_data.json', 'data.json', 'construction_lib_final.json']
}

// 材料 -> 3D 颜色（构造库没有颜色字段，前端统一维护一套）
export const MATERIAL_COLORS = {
  cement_mortar: 0xe8e8e8,
  reinforced_concrete: 0x9b8f7a,
  rockwool: 0xffb347,
  rareearth_board: 0x00b894,
  rareearth_aerogel: 0x3fbdb1,
  xps: 0xf1c40f,
  pu: 0xe67e22
}

export function getDefaultData() {
  return dashboardData
}

export function getDefaultLib() {
  return constructionLib
}

export function getPlans(data) {
  return data?.plans || []
}

export function getAllSchemes(data) {
  return data?.all_schemes_for_switching || []
}

export function getBuildingInfo(data) {
  return data?.building || {}
}

export function getChartData(data) {
  return data?.charts || {}
}

export function getPlanByKey(data, planKey) {
  return getPlans(data).find(p => p.plan_label === planKey) || null
}

export function resolvePlanLike(data, planKey) {
  const plan = getPlanByKey(data, planKey)
  if (plan) return plan
  const scheme = getAllSchemes(data).find(s => s.scheme_id === planKey)
  if (scheme) return { ...scheme, plan_label: scheme.scheme_id }
  return null
}

// 在构造库中查找与方案匹配的墙体构造（按保温材料 key 匹配）
export function findLibScheme(plan, lib = constructionLib) {
  const schemes = lib?.schemes || []
  if (!plan?.material_key) {
    return schemes.find(s => s.scheme_id === 'S0') || schemes[0]
  }
  return schemes.find(s =>
    (s.layers || []).some(l => l.role === '保温层' && l.material === plan.material_key)
  ) || schemes[0]
}

// 把构造库层结构转成前端层数组，顺序 内->外：内抹灰 -> 基层 -> 保温层 -> 饰面层
export function buildLayers(plan, lib = constructionLib) {
  if (Array.isArray(plan?.layers)) return plan.layers.map(l => ({ ...l, color: l.color ?? 0x94a3b8 }))
  const libScheme = findLibScheme(plan, lib)
  const libLayers = libScheme?.layers || []
  const order = { '内抹灰': 0, '结构基层': 1, '保温层': 2, '饰面层': 3 }
  const insulThickness = plan?.thickness_mm ? plan.thickness_mm / 1000 : null

  return libLayers
    .slice()
    .sort((a, b) => (order[a.role] ?? 9) - (order[b.role] ?? 9))
    .map(l => {
      const mat = lib?.materials?.[l.material] || {}
      const isInsul = l.role === '保温层'
      return {
        name: mat.name || l.role,
        role: l.role,
        materialKey: l.material,
        thickness: isInsul && insulThickness != null
          ? insulThickness
          : (l.thickness_m ?? mat.thickness_m ?? 0),
        lambda: mat.lambda ?? 0,
        density: mat.density ?? 0,
        price: mat.price_yuan_m2 ?? 0,
        color: MATERIAL_COLORS[l.material] ?? 0x94a3b8,
        is_insulation: isInsul,
        transparent: isInsul,
        opacity: isInsul ? 0.75 : 1
      }
    })
}

// 根据建筑信息 + 动态几何解析几何来源
export function resolveBuildingGeo(building, json, staticGeoMap) {
  // 1. 动态：JSON 自带 walls
  if (Array.isArray(json.walls) && json.walls.length > 0) {
    return { geo: json, source: 'dynamic' }
  }
  // 2. building_id 直接匹配
  const id = building?.building_id || json.building_id
  if (id && staticGeoMap[id]) {
    return { geo: staticGeoMap[id], source: 'static' }
  }
  // 3. geometry_ref 文件名里提取建筑类型
  const ref = building?.geometry_ref || ''
  const match = ref.match(/(office|dorm|teaching|school)/i)
  if (match) {
    const key = match[1].toLowerCase() === 'school' ? 'school' : match[1].toLowerCase()
    if (staticGeoMap[key]) {
      return { geo: staticGeoMap[key], source: 'static' }
    }
  }
  // 4. 兜底办公楼
  return { geo: staticGeoMap.office, source: 'static' }
}

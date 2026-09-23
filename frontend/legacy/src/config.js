// ===================== 配置中心 =====================

// 墙体各层配置
export const LAYERS_CONFIG = [
  { 
    name: '基层', 
    thickness: 0.20,      // 200mm
    lambda: 1.74, 
    price: 280, 
    color: 0x8B7355, 
    roughness: 0.95, 
    metalness: 0.05,
    density: 2400
  },
  { 
    name: '保温层', 
    thickness: 0.00,      // 初始0mm
    minThickness: 0.02,   // 最小厚度 20mm
    maxThickness: 0.20,   // 最大厚度 200mm
    step: 0.01,           // 滑块步长 10mm
    lambda: 0.035, 
    price: 68, 
    color: 0xCCCCCC, 
    roughness: 0.5, 
    metalness: 0.1, 
    transparent: true, 
    opacity: 0.75,
    density: 0
  },
  { 
    name: '饰面层', 
    thickness: 0.02,      // 20mm
    lambda: 0.8, 
    price: 45, 
    color: 0xE8E8E8, 
    roughness: 0.06, 
    metalness: 0.25, 
    clearcoat: 0.4,
    density: 1500
  }
]

// 预设方案
export const SCHEMES = [
  {
    name: '基准方案(无保温)',
    layers: [
      { name: '基层', thickness: 0.20, color: 0x8B7355, roughness: 0.95, metalness: 0.05, lambda: 1.74, price: 280, density: 2400 },
      { name: '保温层', thickness: 0.00, color: 0xCCCCCC, roughness: 0.5, metalness: 0.1, transparent: true, opacity: 0.75, lambda: 0, price: 0, density: 0 },
      { name: '饰面层', thickness: 0.02, color: 0xE8E8E8, roughness: 0.06, metalness: 0.25, clearcoat: 0.4, lambda: 0.8, price: 45, density: 1500 }
    ],
    data: { energySaving: '0%', investment: '低', carbon: '高', ccer: '0' }
  },
  {
    name: '传统岩棉方案',
    layers: [
      { name: '基层', thickness: 0.20, color: 0x8B7355, roughness: 0.95, metalness: 0.05, lambda: 1.74, price: 280, density: 2400 },
      { name: '保温层', thickness: 0.08, color: 0xFFB347, roughness: 0.5, metalness: 0.1, transparent: true, opacity: 0.75, lambda: 0.045, price: 68, density: 120 },
      { name: '饰面层', thickness: 0.02, color: 0xE8E8E8, roughness: 0.06, metalness: 0.25, clearcoat: 0.4, lambda: 0.8, price: 45, density: 1500 }
    ],
    data: { energySaving: '35%', investment: '中', carbon: '中', ccer: '2100' }
  },
  {
    name: '稀土保温方案',
    layers: [
      { name: '基层', thickness: 0.20, color: 0x8B7355, roughness: 0.95, metalness: 0.05, lambda: 1.74, price: 280, density: 2400 },
      { name: '保温层', thickness: 0.06, color: 0x00B894, roughness: 0.3, metalness: 0.2, transparent: true, opacity: 0.85, lambda: 0.03, price: 85, density: 150 },
      { name: '饰面层', thickness: 0.02, color: 0xE8E8E8, roughness: 0.06, metalness: 0.25, clearcoat: 0.4, lambda: 0.8, price: 45, density: 1500 }
    ],
    data: { energySaving: '40%', investment: '高', carbon: '低', ccer: '2400' }
  }
]

// 给 SCHEMES 补充 LAYERS_CONFIG 里的元数据（min/max/step）
SCHEMES.forEach(scheme => {
  scheme.layers.forEach((layer, i) => {
    const base = LAYERS_CONFIG[i]
    if (base) {
      layer.minThickness = base.minThickness
      layer.maxThickness = base.maxThickness
      layer.step = base.step
    }
  })
})

// 场景参数
export const SCENE_CONFIG = {
  wallHeight: 2.5,
  wallWidth: 3,
  gap: 0.05,              // 剖面展示时的层间距
  animSpeed: 0.06,        // 分层展开动画速度
  bgColor: 0xe6f7f5       // 场景画布的背景底色
}

// 查找保温层索引
export function findHeatLayerIndex(layers) {
  return layers.findIndex(layer => layer.name === '保温层')
}

// 计算总厚度
export function getTotalThickness(layers) {
  return layers.reduce((sum, l) => sum + l.thickness, 0)
}

// 当前状态 —— 直接引用方案A的数据，不再拷贝
export const state = {
  layers: [],
  heatLayerIndex: -1,
  totalThickness: 0,
  entranceProgress: 0,
  currentSchemeIndex: 0,
  currentPlanKey: 'A',
  currentSchemeId: 'S1',
  isExpanded: false,
  // ========== 新增：建筑相关状态 ==========
  buildingMeshes: [],      // 建筑mesh数组
  buildingGroup: null,     // 建筑Group容器
  currentGeo: null,        // 当前建筑几何JSON
  currentBuildingId: null, // 当前建筑ID
  currentBuildingType: 'office', // 当前建筑类型
  geometrySource: 'static', // 当前几何来源：dynamic(后端JSON) | static(内置geo)
  dashboardData: null,     // 当前 dashboard JSON
  constructionLib: null,   // 构造库 JSON
  dataMode: 'demo',        // demo=演示数据 / live=外部仿真结果
  runMeta: null,           // 外部任务元信息（run_id/status/source/error）
  view: 'home'             // 当前视图：home | detail
}

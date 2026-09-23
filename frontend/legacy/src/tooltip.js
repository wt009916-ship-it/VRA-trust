import * as THREE from 'three'
import { camera, renderer } from './scene.js'
import { state } from './config.js'

// ===================== Tooltip =====================

// 射线投射器
const raycaster = new THREE.Raycaster()
// 标准化鼠标坐标（不是屏幕像素，是 -1 ~ +1 区间，射线专用格式）
const mouse = new THREE.Vector2()

// 创建 tooltip DOM 元素
// 固定定位，跟随鼠标窗口移动，不受页面滚动影响
// pointer-events: none 气泡不会拦截鼠标事件，鼠标可以穿透气泡继续拾取 3D 墙体
// z-index: 999 层级拉满，保证气泡盖在 canvas、其他页面元素最上层
const tooltip = document.createElement('div')
tooltip.className = 'wall-tooltip'
tooltip.style.cssText = `
  position: fixed;
  padding: 14px 18px;
  background: rgba(15, 42, 38, 0.95);
  color: #fff;
  border-radius: 10px;
  font-size: 13px;
  line-height: 1.6;
  pointer-events: none;
  display: none;
  z-index: 999;
  backdrop-filter: blur(8px);
  border: 1px solid rgba(255,255,255,0.1);
  box-shadow: 0 10px 40px rgba(0,0,0,0.3);
  max-width: 280px;
`
document.body.appendChild(tooltip)

/**
 * 初始化鼠标移动监听
 */
export function initTooltip() {
  window.addEventListener('mousemove', (event) => {
    const rect = renderer.domElement.getBoundingClientRect()
    
    if (
      event.clientX < rect.left || event.clientX > rect.right ||
      event.clientY < rect.top || event.clientY > rect.bottom
    ) {
      resetHighlight()
      tooltip.style.display = 'none'
      document.body.style.cursor = 'default'
      return
    }
    
    mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1
    mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1
    raycaster.setFromCamera(mouse, camera)

    // 严格过滤：只检测可见的墙面 mesh
    const wallMeshes = state.buildingMeshes.filter(m => 
      m.userData.type === 'wall' && 
      m.visible === true &&
      m.userData.layer &&  // 确保有 layer 数据
      m.userData.layerName  // 确保有 layerName
    )
    const intersects = raycaster.intersectObjects(wallMeshes)

    resetHighlight()

    if (intersects.length > 0) {
      const hit = intersects[0].object
      const info = hit.userData
      
      // 再次安全检查
      if (info.type !== 'wall' || !info.layer || !hit.visible) {
        tooltip.style.display = 'none'
        document.body.style.cursor = 'default'
        return
      }
      
      if (hit.material && hit.material.emissive) {
        hit.material.emissive.setHex(0x333333)
      }
      
      const layer = info.layer
      
      tooltip.innerHTML = `
        <div style="font-weight:600; font-size:15px; margin-bottom:8px; color:#42b899;">
          ${layer.name || info.layerName || '墙体'}
          ${info.orientation ? `(${info.orientation})` : ''}
        </div>
        <div style="display:grid; gap:4px;">
          <div style="display:flex; justify-content:space-between; gap:20px;">
            <span style="color:#64a89e;">厚度</span>
            <span style="font-weight:500;">${((layer.thickness || 0) * 1000).toFixed(0)} mm</span>
          </div>
          <div style="display:flex; justify-content:space-between;">
            <span style="color:#64a89e;">导热系数 λ</span>
            <span style="font-weight:500;">${layer.lambda !== undefined ? layer.lambda : '-'} W/(m·K)</span>
          </div>
          <div style="display:flex; justify-content:space-between;">
            <span style="color:#64a89e;">单方造价</span>
            <span style="font-weight:500;">${layer.price == null ? '未提供' : layer.price + ' 元/㎡'}</span>
          </div>
          <div style="display:flex; justify-content:space-between;">
            <span style="color:#64a89e;">密度</span>
            <span style="font-weight:500;">${layer.density || '-'} kg/m³</span>
          </div>
        </div>
      `
      
      const tipRect = tooltip.getBoundingClientRect()
      let left = event.clientX + 20
      let top = event.clientY + 20
      
      if (left + 280 > window.innerWidth) left = event.clientX - 300
      if (top + 150 > window.innerHeight) top = event.clientY - 160
      
      tooltip.style.left = left + 'px'
      tooltip.style.top = top + 'px'
      tooltip.style.display = 'block'
      document.body.style.cursor = 'pointer'
    } else {
      tooltip.style.display = 'none'
      document.body.style.cursor = 'default'
    }
  })
}

// 提取重置函数
function resetHighlight() {
  state.buildingMeshes.forEach(m => {
    if (m.material.emissive) {
      m.material.emissive.setHex(0x000000)
    }
  })
}

// ===================== 碳排放条 Tooltip =====================

const carbonTooltip = document.createElement('div')
carbonTooltip.style.cssText = `
  position: fixed;
  padding: 10px 16px;
  background: rgba(255, 255, 255, 0.95);
  color: #1e293b;
  border-radius: 8px;
  font-size: 13px;
  font-family: system-ui, -apple-system, sans-serif;
  pointer-events: none;
  display: none;
  z-index: 1000;
  backdrop-filter: blur(8px);
  border: 1px solid rgba(33,171,165,0.15);
  box-shadow: 0 4px 16px rgba(0,0,0,0.08);
  white-space: nowrap;
  line-height: 1.5;
`
document.body.appendChild(carbonTooltip)

/**
 * 给碳排放条形图的色块绑定自定义 tooltip
 * @param {HTMLElement} barsContainer - 色条容器（#carbon-bars）
 */
export function bindCarbonTooltip(barsContainer) {
  if (!barsContainer) return
  barsContainer.querySelectorAll('.carbon-bar-segment').forEach(seg => {
    seg.addEventListener('mouseenter', () => {
      carbonTooltip.innerHTML = seg.dataset.tip
      carbonTooltip.style.display = 'block'
      carbonTooltip.style.opacity = '1'
    })
    seg.addEventListener('mousemove', (e) => {
  const tipRect = carbonTooltip.getBoundingClientRect()
  const containerRect = barsContainer.getBoundingClientRect()
  const gap = 12
  
  // 默认：鼠标上方
  let left = e.clientX + gap
  let top = e.clientY - tipRect.height - gap
  
  // 右边界：超出容器右边缘 → 翻到左侧（防止盖住右侧面板）
  if (left + tipRect.width > containerRect.right) {
    left = e.clientX - tipRect.width - gap
  }
  // 左边界兜底
  if (left < containerRect.left) {
    left = containerRect.left + gap
  }
  
  // 上边界：只有真正贴近屏幕顶部时才翻到下方
  if (top < 0) {
    top = e.clientY + gap
  }
  
  carbonTooltip.style.left = left + 'px'
  carbonTooltip.style.top = top + 'px'
})
    seg.addEventListener('mouseleave', () => {
      carbonTooltip.style.display = 'none'
    })
  })
}

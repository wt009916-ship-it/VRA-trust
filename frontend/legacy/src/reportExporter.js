import html2canvas from 'html2canvas'
import { jsPDF } from 'jspdf'
import { scene, camera, renderer } from './scene.js'
import { state } from './config.js'
import { resolvePlanLike, getBuildingInfo, getPlans } from './data.js'

// ===================== PDF 报告导出器 =====================

const A4_WIDTH = 595.28   // pt
const A4_HEIGHT = 841.89  // pt
const MARGIN = 40         // pt
const CONTENT_W = A4_WIDTH - MARGIN * 2

const THEME = {
  primary: '#21aba5',
  dark: '#1e293b',
  gray: '#64748b',
  lightGray: '#94a3b8',
  border: '#e2f0ee',
  bg: '#f0fffd',
  white: '#ffffff'
}

function trimCanvas(canvas) {
  const ctx = canvas.getContext('2d')
  const { width, height } = canvas
  const data = ctx.getImageData(0, 0, width, height).data
  let top = height, bottom = 0, left = width, right = 0
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const a = data[(y * width + x) * 4 + 3]
      if (a > 8) {
        if (x < left) left = x
        if (x > right) right = x
        if (y < top) top = y
        if (y > bottom) bottom = y
      }
    }
  }
  if (right <= left || bottom <= top) return canvas
  const trimmed = document.createElement('canvas')
  trimmed.width = right - left + 1
  trimmed.height = bottom - top + 1
  trimmed.getContext('2d').drawImage(
    canvas, left, top, trimmed.width, trimmed.height, 0, 0, trimmed.width, trimmed.height
  )
  return trimmed
}

function sizedImg(dataUrl, maxW, maxH) {
  return new Promise(resolve => {
    const img = new Image()
    img.onload = () => {
      const ratio = img.height / img.width || 1
      let width = maxW
      let height = Math.round(maxW * ratio)
      if (maxH && height > maxH) {
        height = maxH
        width = Math.round(maxH / ratio)
      }
      resolve({ src: dataUrl, width, height })
    }
    img.onerror = () => resolve({ src: dataUrl, width: maxW, height: 180 })
    img.src = dataUrl
  })
}

/**
 * 截取 Three.js 画布为图片
 */
function capture3DCanvas() {
  renderer.render(scene, camera)
  return renderer.domElement.toDataURL('image/png')
}

/**
 * 等待所有图表渲染完成
 */
async function waitForCharts() {
  // 如果用了 ECharts，等动画结束
  const charts = document.querySelectorAll('#radar-chart canvas, #bar-chart canvas, #waterfall-chart canvas')
  if (charts.length > 0) {
    await new Promise(r => setTimeout(r, 500))
  }
}

/**
 * 创建离屏 A4 容器
 */
function createA4Page() {
  const div = document.createElement('div')
  div.style.cssText = `
    width: ${A4_WIDTH}px;
    height: ${A4_HEIGHT}px;
    position: fixed;
    left: -9999px;
    top: 0;
    z-index: -1;
    overflow: hidden;
    box-sizing: border-box;
    background: ${THEME.white};
    font-family: system-ui, -apple-system, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
  `
  document.body.appendChild(div)
  return div
}

/**
 * 通用页眉
 */
function pageHeaderHTML(title) {
  return `
    <div style="color:#a33;font-size:12px;padding:8px 40px">历史演示数据 · 不得用于工程决策、成果申报或碳信用证明</div>
    <div style="height: 6px; background: ${THEME.primary};"></div>
    <div style="padding: 0 ${MARGIN}px;">
      <div style="display: flex; align-items: center; gap: 8px; margin-top: 24px; margin-bottom: 8px;">
        <div style="width: 4px; height: 16px; background: ${THEME.primary}; border-radius: 2px;"></div>
        <h2 style="margin: 0; font-size: 16px; color: ${THEME.dark}; font-weight: 700;">${title}</h2>
      </div>
      <div style="height: 1px; background: ${THEME.border}; margin-bottom: 20px;"></div>
    </div>
  `
}

/**
 * 通用页脚
 */
function pageFooterHTML(pageNum) {
  return `
    <div style="position: absolute; bottom: 20px; left: ${MARGIN}px; right: ${MARGIN}px; 
                display: flex; justify-content: space-between; align-items: center;
                font-size: 9px; color: ${THEME.lightGray}; border-top: 1px solid ${THEME.border}; padding-top: 8px;">
      <span>建筑墙体节能分析报告</span>
      <span>第 ${pageNum} 页</span>
    </div>
  `
}

/**
 * 第1页：封面
 */
async function addCoverPage(pdf, projectInfo) {
  const container = createA4Page()
  container.style.background = THEME.bg

  container.innerHTML = `
    <div style="height: 8px; background: ${THEME.primary};"></div>
    <div style="color:#a33;font-size:14px;padding:10px 40px">历史演示数据 · 非真实工程结果</div>
    <div style="padding: 0 ${MARGIN}px;">
      <h1 style="font-size: 28px; color: ${THEME.dark}; margin-top: 100px; font-weight: 700; letter-spacing: 2px;">
        建筑墙体节能分析报告
      </h1>
      <p style="font-size: 14px; color: ${THEME.gray}; margin-top: 12px; font-weight: 400;">
        Building Wall Energy Efficiency Analysis Report
      </p>
      <div style="height: 2px; background: ${THEME.primary}; margin: 40px 0; width: 100%; border-radius: 1px;"></div>
      
      <div style="font-size: 13px; color: ${THEME.dark}; line-height: 2.6; margin-top: 50px;">
        <div style="display: flex; gap: 8px;">
          <span style="color: ${THEME.gray}; min-width: 80px;">项目名称</span>
          <span style="font-weight: 600;">${projectInfo.name || '未命名项目'}</span>
        </div>
        <div style="display: flex; gap: 8px;">
          <span style="color: ${THEME.gray}; min-width: 80px;">建筑类型</span>
          <span>${projectInfo.type || '-'}</span>
        </div>
        <div style="display: flex; gap: 8px;">
          <span style="color: ${THEME.gray}; min-width: 80px;">建筑面积</span>
          <span>${projectInfo.area || '-'} ㎡</span>
        </div>
        <div style="display: flex; gap: 8px;">
          <span style="color: ${THEME.gray}; min-width: 80px;">分析日期</span>
          <span>${new Date().toLocaleDateString('zh-CN')}</span>
        </div>
        <div style="display: flex; gap: 8px;">
          <span style="color: ${THEME.gray}; min-width: 80px;">当前方案</span>
          <span style="color: ${THEME.primary}; font-weight: 600;">${projectInfo.scheme || '方案A'}</span>
        </div>
      </div>
    </div>
    <div style="position: absolute; bottom: 0; left: 0; right: 0; height: 8px; background: ${THEME.primary};"></div>
  `

  const imgData = await html2canvas(container, { scale: 2, backgroundColor: null, logging: false })
  pdf.addImage(imgData.toDataURL('image/png'), 'PNG', 0, 0, A4_WIDTH, A4_HEIGHT)
  document.body.removeChild(container)
}

/**
 * 第2页：3D 模型
 */
async function addModelPage(pdf, imgData) {
  const container = createA4Page()

  const img = new Image()
  img.src = imgData
  await new Promise(resolve => {
    img.onload = resolve
    img.onerror = resolve
  })

  const imgRatio = (img.width && img.height) ? img.width / img.height : 1
  const maxW = CONTENT_W
  const maxH = A4_HEIGHT - 140
  let drawW = maxW
  let drawH = drawW / imgRatio
  if (drawH > maxH) {
    drawH = maxH
    drawW = drawH * imgRatio
  }
  const x = MARGIN + (CONTENT_W - drawW) / 2

  container.innerHTML = `
    ${pageHeaderHTML('建筑三维模型')}
    <div style="padding: 0 ${MARGIN}px;">
      <div style="display: flex; justify-content: center; align-items: center; 
                  height: ${A4_HEIGHT - 120}px; padding-top: 10px;">
        <img src="${imgData}" style="max-width: 100%; max-height: ${maxH}px; object-fit: contain; 
                                     border-radius: 8px; box-shadow: 0 2px 12px rgba(0,0,0,0.08);">
      </div>
    </div>
    ${pageFooterHTML(2)}
  `

  const canvas = await html2canvas(container, { scale: 2, backgroundColor: null, logging: false })
  pdf.addPage()   // 切到第 2 页
  pdf.addImage(canvas.toDataURL('image/png'), 'PNG', 0, 0, A4_WIDTH, A4_HEIGHT)
  document.body.removeChild(container)
}

/**
 * 第3页：墙体构造与性能（文字总结版，不截图面板）
 */
async function addWallStructurePage(pdf) {
  const container = createA4Page()

  // 收集当前方案数据
  const heatLayer = state.layers.find(l => l.name === '保温层')
  const totalThick = state.layers.reduce((sum, l) => sum + l.thickness, 0)
  const kVal = document.getElementById('physics-k')?.textContent || '-'
  const costVal = document.getElementById('physics-cost')?.textContent || '-'
  const energyVal = document.getElementById('physics-energy-total')?.textContent || '-'

  const layersHTML = state.layers
    .filter(l => l.thickness > 0)
    .map((l, i) => {
      const color = '#' + l.color.toString(16).padStart(6, '0')
      const thickMm = (l.thickness * 1000).toFixed(0)
      const isHeat = l.name === '保温层'
      return `
        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 14px; 
                    padding: 10px 14px; background: ${isHeat ? THEME.bg : '#f8fafc'}; 
                    border-radius: 8px; border: ${isHeat ? `1px solid ${THEME.primary}` : '1px solid transparent'};">
          <div style="width: 32px; height: 32px; border-radius: 6px; background: ${color}; 
                      flex-shrink: 0; box-shadow: 0 1px 4px rgba(0,0,0,0.1);"></div>
          <div style="flex: 1;">
            <div style="font-size: 13px; font-weight: 600; color: ${THEME.dark};">${l.name}</div>
            <div style="font-size: 11px; color: ${THEME.gray}; margin-top: 2px;">
              ${isHeat ? '可调节厚度 · ' : ''}${thickMm} mm
            </div>
          </div>
          <div style="font-size: 14px; font-weight: 700; color: ${isHeat ? THEME.primary : THEME.dark};">
            ${thickMm}<span style="font-size: 11px; font-weight: 400; color: ${THEME.gray};">mm</span>
          </div>
        </div>
      `
    }).join('')

  container.innerHTML = `
    ${pageHeaderHTML('墙体构造与性能分析')}
    <div style="padding: 0 ${MARGIN}px;">
      
      <!-- 构造层列表 -->
      <div style="margin-bottom: 28px;">
        <div style="font-size: 12px; color: ${THEME.gray}; font-weight: 600; margin-bottom: 12px; 
                    text-transform: uppercase; letter-spacing: 1px;">构造层配置</div>
        ${layersHTML}
        <div style="display: flex; justify-content: space-between; align-items: center; 
                    margin-top: 8px; padding: 10px 14px; background: ${THEME.dark}; border-radius: 8px;">
          <span style="font-size: 12px; color: rgba(255,255,255,0.7);">墙体总厚度</span>
          <span style="font-size: 16px; font-weight: 700; color: #fff;">${(totalThick * 1000).toFixed(0)} mm</span>
        </div>
      </div>

      <!-- 性能参数卡片 -->
      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 20px;">
        <div style="padding: 14px; background: ${THEME.bg}; border-radius: 10px; border: 1px solid #c5f5e8;">
          <div style="font-size: 11px; color: ${THEME.gray}; margin-bottom: 4px;">传热系数 K</div>
          <div style="font-size: 18px; font-weight: 700; color: ${THEME.primary};">${kVal}</div>
          <div style="font-size: 10px; color: ${THEME.lightGray}; margin-top: 2px;">W/(㎡·K)</div>
        </div>
        <div style="padding: 14px; background: #f8fafc; border-radius: 10px; border: 1px solid ${THEME.border};">
          <div style="font-size: 11px; color: ${THEME.gray}; margin-bottom: 4px;">单方造价</div>
          <div style="font-size: 18px; font-weight: 700; color: ${THEME.dark};">${costVal}</div>
        </div>
        <div style="padding: 14px; background: #f8fafc; border-radius: 10px; border: 1px solid ${THEME.border};">
          <div style="font-size: 11px; color: ${THEME.gray}; margin-bottom: 4px;">年能耗</div>
          <div style="font-size: 18px; font-weight: 700; color: ${THEME.dark};">${energyVal}</div>
        </div>
        <div style="padding: 14px; background: #f8fafc; border-radius: 10px; border: 1px solid ${THEME.border};">
          <div style="font-size: 11px; color: ${THEME.gray}; margin-bottom: 4px;">保温层厚度</div>
          <div style="font-size: 18px; font-weight: 700; color: ${THEME.dark};">
            ${heatLayer ? (heatLayer.thickness * 1000).toFixed(0) : 0}<span style="font-size: 11px; font-weight: 400; color: ${THEME.gray};">mm</span>
          </div>
        </div>
      </div>

    </div>
    ${pageFooterHTML(3)}
  `

  const canvas = await html2canvas(container, { scale: 2, backgroundColor: null, logging: false })
  pdf.addPage()   // 切到第 3 页
  pdf.addImage(canvas.toDataURL('image/png'), 'PNG', 0, 0, A4_WIDTH, A4_HEIGHT)
  document.body.removeChild(container)
}

/**
 * 第4页：三方案对比（只截图图表区域，不截图整个面板）
 */
async function addComparisonPage(pdf) {
  const container = createA4Page()

  // 从右侧面板提取图表 canvas
  const radarCanvas = document.querySelector('#radar-chart canvas')
  const barCanvas = document.querySelector('#bar-chart canvas')
  const waterfallCanvas = document.querySelector('#waterfall-chart canvas')

  const radarImg = radarCanvas ? radarCanvas.toDataURL('image/png') : null
  const barImg = barCanvas ? barCanvas.toDataURL('image/png') : null
  const waterfallImg = waterfallCanvas ? waterfallCanvas.toDataURL('image/png') : null

  container.innerHTML = `
    ${pageHeaderHTML('三方案对比分析')}
    <div style="padding: 0 ${MARGIN}px;">
      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px;">
        ${radarImg ? `
          <div style="background: #f8fcfc; border-radius: 10px; padding: 12px; border: 1px solid ${THEME.border};">
            <div style="font-size: 10px; color: ${THEME.gray}; font-weight: 600; margin-bottom: 8px; text-align: center;">综合性能雷达图</div>
            <img src="${radarImg}" style="width: 100%; height: auto; display: block;">
          </div>
        ` : ''}
        ${barImg ? `
          <div style="background: #f8fcfc; border-radius: 10px; padding: 12px; border: 1px solid ${THEME.border};">
            <div style="font-size: 10px; color: ${THEME.gray}; font-weight: 600; margin-bottom: 8px; text-align: center;">成本能耗对比</div>
            <img src="${barImg}" style="width: 100%; height: auto; display: block;">
          </div>
        ` : ''}
      </div>
      ${waterfallImg ? `
        <div style="background: #f8fcfc; border-radius: 10px; padding: 12px; border: 1px solid ${THEME.border};">
          <div style="font-size: 10px; color: ${THEME.gray}; font-weight: 600; margin-bottom: 8px; text-align: center;">碳排放瀑布图</div>
          <img src="${waterfallImg}" style="width: 100%; max-height: 200px; object-fit: contain; display: block; margin: 0 auto;">
        </div>
      ` : ''}
    </div>
    ${pageFooterHTML(4)}
  `

  const canvas = await html2canvas(container, { scale: 2, backgroundColor: null, logging: false })
  pdf.addPage()   // 切到第 4 页
  pdf.addImage(canvas.toDataURL('image/png'), 'PNG', 0, 0, A4_WIDTH, A4_HEIGHT)
  document.body.removeChild(container)
}

/**
 * 第5页：性能参数汇总
 */
async function addPerformanceSummaryPage(pdf) {
  const container = createA4Page()

  const k = document.getElementById('physics-k')?.textContent || '-'
  const thick = document.getElementById('physics-thick')?.textContent || '-'
  const cost = document.getElementById('physics-cost')?.textContent || '-'
  const energyM2 = document.getElementById('physics-energy-m2')?.textContent || '-'
  const energyTotal = document.getElementById('physics-energy-total')?.textContent || '-'
  const cool = document.getElementById('energy-cool')?.textContent || '-'
  const heat = document.getElementById('energy-heat')?.textContent || '-'
  const carbonTotal = document.getElementById('carbon-total')?.textContent || '-'
  const carbonSaving = document.getElementById('carbon-saving')?.textContent || '-'
  const ccerAnnual = document.getElementById('ccer-annual')?.textContent || '-'

  const params = [
    ['传热系数 K', k, 'W/(㎡·K)', THEME.primary],
    ['总厚度', thick, 'mm', THEME.dark],
    ['单方造价', cost, '', THEME.dark],
    ['单位能耗', energyM2, '', THEME.dark],
    ['年能耗', energyTotal, '', THEME.dark],
    ['制冷负荷', cool, '', THEME.dark],
    ['制热负荷', heat, '', THEME.dark],
    ['全周期碳排放', carbonTotal, 'tCO₂', THEME.dark],
    ['减碳率', carbonSaving, '%', '#16a34a'],
    ['CCER 年减排', ccerAnnual, 't', THEME.primary],
  ]

  const paramsHTML = params.map(([label, value, unit, color]) => `
    <div style="display: flex; align-items: baseline; padding: 14px 0; border-bottom: 1px dashed ${THEME.border};">
      <span style="font-size: 12px; color: ${THEME.gray}; min-width: 110px;">${label}</span>
      <span style="flex: 1; border-bottom: 1px dotted #cbd5e1; margin: 0 12px 3px; min-width: 20px;"></span>
      <span style="font-size: 15px; font-weight: 700; color: ${color}; white-space: nowrap;">
        ${value}<span style="font-size: 11px; font-weight: 400; color: ${THEME.gray}; margin-left: 4px;">${unit}</span>
      </span>
    </div>
  `).join('')

  const layersHTML = state.layers
    .filter(l => l.thickness > 0)
    .map(l => {
      const color = '#' + l.color.toString(16).padStart(6, '0')
      return `
        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 10px;">
          <div style="width: 14px; height: 14px; border-radius: 4px; background: ${color}; flex-shrink: 0;"></div>
          <span style="font-size: 12px; color: ${THEME.dark};">${l.name}</span>
          <span style="margin-left: auto; font-size: 12px; color: ${THEME.gray}; font-weight: 500;">${(l.thickness * 1000).toFixed(0)} mm</span>
        </div>
      `
    }).join('')

  container.innerHTML = `
    ${pageHeaderHTML('墙体性能参数汇总')}
    <div style="padding: 0 ${MARGIN}px;">
      <div style="display: flex; gap: 24px;">
        <!-- 左侧：参数列表 -->
        <div style="flex: 1.2;">
          <div style="font-size: 12px; color: ${THEME.gray}; font-weight: 600; margin-bottom: 12px; 
                      text-transform: uppercase; letter-spacing: 1px;">性能指标</div>
          ${paramsHTML}
        </div>
        <!-- 右侧：构造层 -->
        <div style="flex: 1; padding-left: 20px; border-left: 1px solid ${THEME.border};">
          <div style="font-size: 12px; color: ${THEME.gray}; font-weight: 600; margin-bottom: 12px; 
                      text-transform: uppercase; letter-spacing: 1px;">构造层配置</div>
          ${layersHTML}
          <div style="margin-top: 16px; padding: 12px; background: ${THEME.dark}; border-radius: 8px; text-align: center;">
            <div style="font-size: 10px; color: rgba(255,255,255,0.6);">总厚度</div>
            <div style="font-size: 20px; font-weight: 700; color: #fff; margin-top: 4px;">
              ${Math.round(state.layers.reduce((s, l) => s + l.thickness, 0) * 1000)}<span style="font-size: 12px; font-weight: 400;"> mm</span>
            </div>
          </div>
        </div>
      </div>
    </div>
    ${pageFooterHTML(5)}
  `

  const canvas = await html2canvas(container, { scale: 2, backgroundColor: null, logging: false })
  pdf.addPage()   // 切到第 5 页
  pdf.addImage(canvas.toDataURL('image/png'), 'PNG', 0, 0, A4_WIDTH, A4_HEIGHT)
  document.body.removeChild(container)
}

/**
 * 主导出函数
 */
export async function exportReportLegacy() {
  await waitForCharts()

  const pdf = new jsPDF('p', 'pt', 'a4')

  const city = document.getElementById('proj-city')?.textContent?.trim() || '未命名项目'
  const type = document.getElementById('proj-type')?.textContent?.trim() || '建筑节能分析'

  const projectInfo = {
    name: `${city} · ${type}`,
    type,
    area: document.getElementById('proj-area')?.textContent?.trim() || '-',
    scheme: ['方案A', '方案B', '方案C'][state.currentSchemeIndex] || '方案A',
  }

  // 1. 封面
  await addCoverPage(pdf, projectInfo)

  // 2. 3D 模型
  const modelImg = capture3DCanvas()
  await addModelPage(pdf, modelImg)

  // 3. 墙体构造与性能（文字总结，不截图面板）
  await addWallStructurePage(pdf)

  // 4. 三方案对比（只截图图表，不截图面板）
  await addComparisonPage(pdf)

  // 5. 性能参数汇总
  await addPerformanceSummaryPage(pdf)

  const fileName = `建筑墙体节能分析报告_${new Date().toISOString().slice(0, 10)}.pdf`
  pdf.save(fileName)
}

// ===================== 新版：基于 dashboard 数据的详情页导出 =====================

async function addReportCover(pdf, data, plan) {
  const building = getBuildingInfo(data)
  const container = createA4Page()
  container.style.background = THEME.bg

  const dateStr = new Date().toLocaleDateString('zh-CN')
  const reportNo = `RPT-${new Date().toISOString().slice(0, 10).replace(/-/g, '')}-${String(plan.plan_label || 'X').padStart(2, '0')}`

  container.innerHTML = `
    <div style="height: 8px; background: ${THEME.primary};"></div>
    <div style="padding: 0 ${MARGIN}px;">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 40px;">
        <div style="width: 62px; height: 62px; border-radius: 16px; background: ${THEME.primary}; display: flex; align-items: center; justify-content: center; color: #fff; font-size: 18px; font-weight: 800; letter-spacing: 1px;">稀土</div>
        <span style="font-size: 10px; color: ${THEME.lightGray}; letter-spacing: 2px;">ENVELOPE ENERGY REPORT</span>
      </div>
      <h1 style="font-size: 42px; color: ${THEME.dark}; margin-top: 110px; font-weight: 800; letter-spacing: 6px;">
        稀土智暖
      </h1>
      <p style="font-size: 14px; color: ${THEME.gray}; margin-top: 14px; letter-spacing: 2px;">
        建筑外墙保温方案测算专业报告
      </p>
      <div style="height: 2px; background: ${THEME.primary}; margin: 36px 0;"></div>
      <div style="font-size: 13px; color: ${THEME.dark}; line-height: 2.6;">
        <div style="display: flex; gap: 8px;">
          <span style="color: ${THEME.gray}; min-width: 80px;">建筑类型</span>
          <span style="font-weight: 600;">${building.name || building.building_id || '-'}</span>
        </div>
        <div style="display: flex; gap: 8px;">
          <span style="color: ${THEME.gray}; min-width: 80px;">所在城市</span>
          <span>${building.city || '-'}</span>
        </div>
        <div style="display: flex; gap: 8px;">
          <span style="color: ${THEME.gray}; min-width: 80px;">建筑面积</span>
          <span>${building.area_m2 || '-'} ㎡</span>
        </div>
        <div style="display: flex; gap: 8px;">
          <span style="color: ${THEME.gray}; min-width: 80px;">当前方案</span>
          <span style="color: ${THEME.primary}; font-weight: 600;">方案${plan.plan_label} · ${plan.scheme_name}</span>
        </div>
        <div style="display: flex; gap: 8px;">
          <span style="color: ${THEME.gray}; min-width: 80px;">生成日期</span>
          <span>${dateStr}</span>
        </div>
        <div style="display: flex; gap: 8px;">
          <span style="color: ${THEME.gray}; min-width: 80px;">报告编号</span>
          <span style="font-weight: 600; color: ${THEME.dark};">${reportNo}</span>
        </div>
      </div>
    </div>
    <div style="position: absolute; bottom: 0; left: 0; right: 0; height: 8px; background: ${THEME.primary};"></div>
  `

  const imgData = await html2canvas(container, { scale: 2, backgroundColor: null, logging: false })
  pdf.addImage(imgData.toDataURL('image/png'), 'PNG', 0, 0, A4_WIDTH, A4_HEIGHT)
  document.body.removeChild(container)
}

async function addReportModel(pdf, imgData) {
  const container = createA4Page()
  container.innerHTML = `
    ${pageHeaderHTML('建筑三维模型')}
    <div style="padding: 0 ${MARGIN}px;">
      <div style="display: flex; justify-content: center; align-items: center; height: ${A4_HEIGHT - 120}px;">
        <img src="${imgData}" style="max-width: 100%; max-height: ${A4_HEIGHT - 150}px; object-fit: contain; border-radius: 8px;">
      </div>
    </div>
    ${pageFooterHTML(2)}
  `
  const canvas = await html2canvas(container, { scale: 2, backgroundColor: null, logging: false })
  pdf.addPage()
  pdf.addImage(canvas.toDataURL('image/png'), 'PNG', 0, 0, A4_WIDTH, A4_HEIGHT)
  document.body.removeChild(container)
}

async function addReportStructure(pdf, plan) {
  const container = createA4Page()
  const rows = state.layers
    .filter(l => l.thickness > 0)
    .map(l => `
      <tr>
        <td style="padding: 8px; border-bottom: 1px solid ${THEME.border}; color: ${THEME.gray};">
          ${l.role || l.name}
        </td>
        <td style="padding: 8px; border-bottom: 1px solid ${THEME.border}; color: ${THEME.dark};">
          ${l.name}
        </td>
        <td style="padding: 8px; border-bottom: 1px solid ${THEME.border}; color: ${THEME.dark};">
          ${(l.thickness * 1000).toFixed(0)} mm
        </td>
        <td style="padding: 8px; border-bottom: 1px solid ${THEME.border}; color: ${THEME.dark};">
          ${l.lambda}
        </td>
      </tr>
    `).join('')

  container.innerHTML = `
    ${pageHeaderHTML('墙体构造与性能')}
    <div style="padding: 0 ${MARGIN}px;">
      <table style="width: 100%; border-collapse: collapse; font-size: 12px; margin-bottom: 24px;">
        <thead>
          <tr style="background: ${THEME.bg};">
            <th style="padding: 8px; text-align: left; color: ${THEME.gray};">层级</th>
            <th style="padding: 8px; text-align: left; color: ${THEME.gray};">材料</th>
            <th style="padding: 8px; text-align: left; color: ${THEME.gray};">厚度</th>
            <th style="padding: 8px; text-align: left; color: ${THEME.gray};">λ (W/m·K)</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
        <div style="padding: 14px; background: ${THEME.bg}; border-radius: 10px; border: 1px solid #c5f5e8;">
          <div style="font-size: 11px; color: ${THEME.gray};">外墙K值</div>
          <div style="font-size: 18px; font-weight: 700; color: ${THEME.primary};">${plan.u_value}</div>
        </div>
        <div style="padding: 14px; background: #f8fafc; border-radius: 10px; border: 1px solid ${THEME.border};">
          <div style="font-size: 11px; color: ${THEME.gray};">节能率</div>
          <div style="font-size: 18px; font-weight: 700; color: ${THEME.dark};">${plan.energy.saving_rate_pct}%</div>
        </div>
        <div style="padding: 14px; background: #f8fafc; border-radius: 10px; border: 1px solid ${THEME.border};">
          <div style="font-size: 11px; color: ${THEME.gray};">年碳排</div>
          <div style="font-size: 18px; font-weight: 700; color: ${THEME.dark};">${plan.carbon.annual_operation_tCO2} tCO₂</div>
        </div>
        <div style="padding: 14px; background: #f8fafc; border-radius: 10px; border: 1px solid ${THEME.border};">
          <div style="font-size: 11px; color: ${THEME.gray};">保温厚度</div>
          <div style="font-size: 18px; font-weight: 700; color: ${THEME.dark};">${plan.thickness_mm} mm</div>
        </div>
      </div>
    </div>
    ${pageFooterHTML(3)}
  `

  const canvas = await html2canvas(container, { scale: 2, backgroundColor: null, logging: false })
  pdf.addPage()
  pdf.addImage(canvas.toDataURL('image/png'), 'PNG', 0, 0, A4_WIDTH, A4_HEIGHT)
  document.body.removeChild(container)
}

async function addReportExtra(pdf, plan) {
  const container = createA4Page()
  const wfCanvas = document.querySelector('#detail-waterfall-chart canvas')
  const wfImg = wfCanvas ? wfCanvas.toDataURL('image/png') : null

  container.innerHTML = `
    ${pageHeaderHTML('碳资产与方案总结')}
    <div style="padding: 0 ${MARGIN}px;">
      <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 20px;">
        <div style="padding: 14px; background: ${THEME.bg}; border-radius: 10px; border: 1px solid #c5f5e8; text-align: center;">
          <div style="font-size: 11px; color: ${THEME.gray};">CCER 年减排量</div>
          <div style="font-size: 20px; font-weight: 700; color: ${THEME.primary};">${plan.ccer.annual_reduction_tCO2} t</div>
        </div>
        <div style="padding: 14px; background: #f8fafc; border-radius: 10px; border: 1px solid ${THEME.border}; text-align: center;">
          <div style="font-size: 11px; color: ${THEME.gray};">年价值</div>
          <div style="font-size: 20px; font-weight: 700; color: ${THEME.dark};">${plan.ccer.annual_value_yuan} 元</div>
        </div>
        <div style="padding: 14px; background: #f8fafc; border-radius: 10px; border: 1px solid ${THEME.border}; text-align: center;">
          <div style="font-size: 11px; color: ${THEME.gray};">10年总收益</div>
          <div style="font-size: 20px; font-weight: 700; color: ${THEME.dark};">${plan.ccer.total_10y_yuan} 元</div>
        </div>
      </div>
      ${wfImg ? `
        <div style="background: #f8fcfc; border-radius: 10px; padding: 12px; border: 1px solid ${THEME.border}; margin-bottom: 20px;">
          <div style="font-size: 11px; color: ${THEME.gray}; font-weight: 600; margin-bottom: 8px;">五阶段碳排瀑布图</div>
          <img src="${wfImg}" style="width: 100%; display: block;">
        </div>
      ` : ''}
      <div style="padding: 16px; background: linear-gradient(135deg, #f0fffd, #e6f7f5); border: 1px solid ${THEME.primary}; border-radius: 10px;">
        <div style="font-size: 12px; color: ${THEME.gray}; font-weight: 600; margin-bottom: 8px;">推荐理由</div>
        <div style="font-size: 12px; color: #475569; line-height: 1.8;">
          ${plan.recommend_tag || '综合推荐'}：${plan.scheme_name}，保温厚度 ${plan.thickness_mm}mm，
          节能率 ${plan.energy.saving_rate_pct}%，外墙K值 ${plan.u_value} W/(㎡·K)，
          CCER 年收益约 ${plan.ccer.annual_value_yuan} 元。
        </div>
      </div>
    </div>
    ${pageFooterHTML(4)}
  `

  const canvas = await html2canvas(container, { scale: 2, backgroundColor: null, logging: false })
  pdf.addPage()
  pdf.addImage(canvas.toDataURL('image/png'), 'PNG', 0, 0, A4_WIDTH, A4_HEIGHT)
  document.body.removeChild(container)
}

export async function exportReport() {
  if (state.dataMode === 'live') {
    if (!state.validatedComparison || !['succeeded','success'].includes(state.runMeta?.status)) {
      alert('没有经过本机核验的有效比较结果，不能导出正式计算报告。')
      return
    }
    window.open('/api/report?runs='+state.validatedComparison.ids.map(encodeURIComponent).join(','),'_blank','noopener')
    return
  }
  if (!confirm('当前为历史演示数据，仅用于界面演示，不得作为真实工程结果。是否仍导出演示文件？')) return
  const data = state.dashboardData
  if (!data) return
  const plan = resolvePlanLike(data, state.currentPlanKey)
  if (!plan) return

  await waitForCharts()

  const pdf = new jsPDF('p', 'pt', 'a4')
  await addReportCover(pdf, data, plan)
  await addReportOverview(pdf, data, plan)
  await addReportDetailData(pdf, plan)

  pdf.save(`建筑墙体节能分析报告_${new Date().toISOString().slice(0, 10)}.pdf`)
}

// 第2页：方案总览（3D + 剖面展开 + 三方案对比表）
async function addReportOverview(pdf, data, plan) {
  const container = createA4Page()
  const plans = getPlans(data)

  const modelImg = await sizedImg(capture3DCanvas(), CONTENT_W - 36, 220)

  // 等剖面展开动画播完再截图
  await new Promise(r => setTimeout(r, 900))
  let sectionImg = null
  const sectionView = document.querySelector('#section-view > div') || document.getElementById('section-view')
  if (sectionView) {
    try {
      const canvas = await html2canvas(sectionView, { scale: 2, backgroundColor: null, logging: false })
      sectionImg = await sizedImg(trimCanvas(canvas).toDataURL('image/png'), CONTENT_W - 36, 110)
    } catch (err) {
      sectionImg = null
    }
  }

  const rows = [
    ['材料类型', ...plans.map(p => p.scheme_name)],
    ['保温厚度', ...plans.map(p => `${p.thickness_mm} mm`)],
    ['节能率', ...plans.map(p => `${p.energy.saving_rate_pct}%`)],
    ['单方造价', ...plans.map(p => `${p.cost.unit_price_yuan_m2} 元/㎡`)],
    ['年碳排', ...plans.map(p => `${p.carbon.annual_operation_tCO2} tCO₂`)],
    ['CCER 年价值', ...plans.map(p => `${p.ccer.annual_value_yuan} 元`)]
  ]

  container.innerHTML = `
    ${pageHeaderHTML('方案总览')}
    <div style="padding: 0 ${MARGIN}px;">
      <div style="background: #f8fcfc; border: 1px solid ${THEME.border}; border-radius: 10px; padding: 10px; margin-bottom: 14px;">
        <div style="font-size: 10px; color: ${THEME.gray}; font-weight: 600; margin-bottom: 8px;">建筑三维模型</div>
        <div style="display: flex; justify-content: center;">
          <img src="${modelImg.src}" style="width: ${modelImg.width}px; height: ${modelImg.height}px; display: block;">
        </div>
      </div>
      ${sectionImg ? `
      <div style="background: #f8fcfc; border: 1px solid ${THEME.border}; border-radius: 10px; padding: 10px; margin-bottom: 14px; height: 160px; box-sizing: border-box;">
        <div style="font-size: 10px; color: ${THEME.gray}; font-weight: 600; margin-bottom: 8px;">墙体构造剖面（展开）</div>
        <div style="display: flex; justify-content: center; align-items: center; height: calc(100% - 22px);">
          <img src="${sectionImg.src}" style="width: ${sectionImg.width}px; height: ${sectionImg.height}px; display: block;">
        </div>
      </div>` : ''}
      <table style="width: 100%; border-collapse: collapse; font-size: 12px; margin-bottom: 40px;">
        <thead>
          <tr style="background: ${THEME.bg};">
            <th style="padding: 10px; text-align: left; color: ${THEME.gray}; border: 1px solid ${THEME.border};">指标</th>
            ${plans.map(p => `<th style="padding: 10px; text-align: center; color: ${THEME.dark}; border: 1px solid ${THEME.border};">方案${p.plan_label}</th>`).join('')}
          </tr>
        </thead>
        <tbody>
          ${rows.map(([label, ...vals]) => `
            <tr>
              <td style="padding: 10px; color: ${THEME.gray}; border: 1px solid ${THEME.border};">${label}</td>
              ${vals.map(v => `<td style="padding: 10px; text-align: center; color: ${THEME.dark}; border: 1px solid ${THEME.border};">${v}</td>`).join('')}
            </tr>
          `).join('')}
        </tbody>
      </table>
    </div>
    ${pageFooterHTML(2)}
  `

  const canvas = await html2canvas(container, { scale: 2, backgroundColor: null, logging: false })
  sectionImg = trimCanvas(canvas).toDataURL('image/png')
  pdf.addPage()
  pdf.addImage(canvas.toDataURL('image/png'), 'PNG', 0, 0, A4_WIDTH, A4_HEIGHT)
  document.body.removeChild(container)
}

// 第3页：详细数据（材料 / 能耗 / 碳排 / CCER）
async function addReportDetailData(pdf, plan) {
  const container = createA4Page()

  const layerRows = state.layers
    .filter(l => l.thickness > 0)
    .map(l => `
      <tr>
        <td style="padding: 6px 8px; border: 1px solid ${THEME.border}; color: ${THEME.gray};">${l.role || l.name}</td>
        <td style="padding: 6px 8px; border: 1px solid ${THEME.border}; color: ${THEME.dark};">${l.name}</td>
        <td style="padding: 6px 8px; border: 1px solid ${THEME.border}; color: ${THEME.dark};">${(l.thickness * 1000).toFixed(0)} mm</td>
        <td style="padding: 6px 8px; border: 1px solid ${THEME.border}; color: ${THEME.dark};">${l.lambda} W/(m·K)</td>
        <td style="padding: 6px 8px; border: 1px solid ${THEME.border}; color: ${THEME.dark};">${l.price} 元/㎡</td>
      </tr>
    `).join('')

  const stages = [
    ['建材生产', plan.carbon_stages_tCO2?.production],
    ['运输', plan.carbon_stages_tCO2?.transport],
    ['施工', plan.carbon_stages_tCO2?.construction],
    ['运行(50年)', plan.carbon_stages_tCO2?.operation],
    ['拆除', plan.carbon_stages_tCO2?.demolition],
    ['全周期合计', plan.carbon?.lca_total_tCO2]
  ]

  const table = (title, head, body) => `
    <div>
      <div style="font-size: 11px; color: ${THEME.primary}; font-weight: 700; margin-bottom: 6px;">${title}</div>
      <table style="width: 100%; border-collapse: collapse; font-size: 10px;">
        <thead>
          <tr style="background: ${THEME.bg};">
            ${head.map(h => `<th style="padding: 6px 8px; border: 1px solid ${THEME.border}; text-align: left; color: ${THEME.gray};">${h}</th>`).join('')}
          </tr>
        </thead>
        <tbody>${body}</tbody>
      </table>
    </div>
  `

  const materialTable = table('材料参数表', ['层级', '材料', '厚度', '导热系数 λ', '单价'], layerRows)

  const energyRows = [
    ['全年空调能耗', plan.energy.annual_cooling_kWh + ' kWh'],
    ['全年采暖能耗', plan.energy.annual_heating_kWh + ' kWh'],
    ['单位面积能耗', plan.energy.intensity_kWh_m2a + ' kWh/(㎡·a)'],
    ['节能率', plan.energy.saving_rate_pct + '%']
  ].map(([k, v]) => `
    <tr>
      <td style="padding: 6px 8px; border: 1px solid ${THEME.border}; color: ${THEME.gray};">${k}</td>
      <td style="padding: 6px 8px; border: 1px solid ${THEME.border}; color: ${THEME.dark}; text-align: right;">${v}</td>
    </tr>`).join('')
  const energyTable = table('能耗数据表', ['指标', '数值'], energyRows)

  const carbonRows = stages.map(([k, v]) => `
    <tr>
      <td style="padding: 6px 8px; border: 1px solid ${THEME.border}; color: ${THEME.gray};">${k}</td>
      <td style="padding: 6px 8px; border: 1px solid ${THEME.border}; color: ${THEME.dark}; text-align: right;">${v != null ? v + ' tCO₂' : '-'}</td>
    </tr>`).join('')
  const carbonTable = table('碳排数据表（五阶段）', ['阶段', '碳排量'], carbonRows)

  const ccerRows = [
    ['年减排量', plan.ccer.annual_reduction_tCO2 + ' t'],
    ['碳价', plan.ccer.price_yuan_t + ' 元/吨'],
    ['年价值', plan.ccer.annual_value_yuan + ' 元'],
    ['10年总收益', plan.ccer.total_10y_yuan + ' 元']
  ].map(([k, v]) => `
    <tr>
      <td style="padding: 6px 8px; border: 1px solid ${THEME.border}; color: ${THEME.gray};">${k}</td>
      <td style="padding: 6px 8px; border: 1px solid ${THEME.border}; color: ${THEME.dark}; text-align: right;">${v}</td>
    </tr>`).join('')
  const ccerTable = table('CCER 价值估算表', ['指标', '数值'], ccerRows)

  container.innerHTML = `
    ${pageHeaderHTML('详细数据')}
    <div style="padding: 0 ${MARGIN}px;">
      <div style="margin-bottom: 16px;">${materialTable}</div>
      <div style="display: flex; gap: 16px; margin-bottom: 16px;">
        <div style="flex: 1;">${energyTable}</div>
        <div style="flex: 1;">${ccerTable}</div>
      </div>
      <div style="margin-bottom: 18px;">${carbonTable}</div>
      <div style="margin-bottom: 26px; padding: 14px 16px; background: linear-gradient(135deg, #f0fffd, #e6f7f5); border: 1px solid ${THEME.primary}; border-radius: 10px; font-size: 12px; color: #475569; line-height: 1.8;">
        <b style="color: ${THEME.dark};">方案${plan.plan_label} · ${plan.scheme_name}</b>：
        保温厚度 ${plan.thickness_mm}mm，节能率 ${plan.energy.saving_rate_pct}%，
        外墙K值 ${plan.u_value} W/(㎡·K)，年碳排 ${plan.carbon.annual_operation_tCO2} tCO₂，
        CCER 年收益约 ${plan.ccer.annual_value_yuan} 元。
      </div>
    </div>
    ${pageFooterHTML(3)}
  `

  const canvas = await html2canvas(container, { scale: 2, backgroundColor: null, logging: false })
  pdf.addPage()
  pdf.addImage(canvas.toDataURL('image/png'), 'PNG', 0, 0, A4_WIDTH, A4_HEIGHT)
  document.body.removeChild(container)
}

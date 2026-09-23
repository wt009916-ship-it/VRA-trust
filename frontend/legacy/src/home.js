import { state } from './config.js'
import { getPlans, getBuildingInfo, getAllSchemes, buildLayers } from './data.js'
import { createSchemeThumbnail } from './thumbnail.js'
import { switchHomeWaterfall } from './charts.js'
import jsonData from '../../../fixtures/demo/frontend-data/data.json'

const thumbnails = []
let drawerTimer = null

const HOME_STYLE = `
  #view-home {
    position: fixed;
    inset: 0;
    z-index: 2;
    background: #e6f7f5;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    --topbar-h: 56px;
    font-family: system-ui, -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
  }
  #home-topbar {
    height: var(--topbar-h);
    display: flex;
    align-items: center;
    gap: 18px;
    padding: 0 22px;
    background: rgba(255,255,255,0.9);
    border-bottom: 1px solid #d3efe9;
    backdrop-filter: blur(10px);
    box-sizing: border-box;
    flex-shrink: 0;
  }
  #home-topbar .bar-brand {
    font-size: 16px;
    font-weight: 700;
    color: #0f2a26;
    letter-spacing: 1px;
  }
  #mock-badge {
    font-size: 11px;
    font-weight: 600;
    color: #b45309;
    background: #fef3c7;
    border: 1px solid #fcd34d;
    padding: 3px 10px;
    border-radius: 12px;
    white-space: nowrap;
  }
  #home-topbar .bar-item {
    font-size: 12px;
    color: #64748b;
    padding: 5px 12px;
    background: #f0fffd;
    border: 1px solid #c5f5e8;
    border-radius: 16px;
    white-space: nowrap;
  }
  #home-topbar .bar-item b { color: #21aba5; font-weight: 600; }
  #home-main {
    height: calc(100vh - var(--topbar-h));
    min-height: 0;
    display: grid;
    grid-template-rows: minmax(0, 3fr) minmax(0, 2fr);
    gap: 14px;
    padding: 14px 22px 18px;
    box-sizing: border-box;
  }
  #home-cards {
    flex: 3;
    min-height: 0;
    overflow: hidden;
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 14px;
  }
  .plan-card {
    background: rgba(255,255,255,0.96);
    border-radius: 12px;
    border: 1px solid #d3efe9;
    box-shadow: 0 4px 18px rgba(15,42,38,0.06);
    padding: 14px;
    display: flex;
    flex-direction: column;
    transition: border-color 0.2s, box-shadow 0.2s;
    overflow: hidden;
  }
  .plan-card.active {
    border-color: #21aba5;
    box-shadow: 0 6px 24px rgba(33,171,165,0.18);
  }
    .plan-card.featured {
      border-color: #21aba5;
      border-width: 2px;
      background: linear-gradient(180deg, #ffffff 0%, #f0fffd 100%);
      box-shadow: 0 10px 30px rgba(33,171,165,0.22);
    }
    .plan-card.featured .plan-label {
      color: #1f7974;
    }
  .plan-card-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 4px;
  }
  .plan-label {
    font-size: 13px;
    font-weight: 700;
    color: #21aba5;
  }
  .plan-tag {
    font-size: 10px;
    color: #1f7974;
    background: rgba(33,171,165,0.1);
    padding: 3px 8px;
    border-radius: 10px;
  }
  .plan-card-name {
    font-size: 15px;
    font-weight: 600;
    color: #1e293b;
    margin-bottom: 10px;
  }
  .plan-thumb {
    flex: 1;
    min-height: 0;
    border-radius: 10px;
    background: linear-gradient(180deg, #eafaf7, #d5f1ec);
    overflow: hidden;
    margin-bottom: 12px;
    cursor: default;
  }
  .plan-metrics {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 8px;
    margin-bottom: 12px;
  }
  .plan-metrics div {
    background: #f8fcfc;
    border: 1px solid #e2f0ee;
    border-radius: 8px;
    padding: 7px 8px;
  }
  .plan-metrics span {
    display: block;
    font-size: 10px;
    color: #94a3b8;
    margin-bottom: 2px;
  }
  .plan-metrics b {
    font-size: 13px;
    color: #1e293b;
    font-weight: 700;
  }
  .plan-detail-btn {
    margin-top: auto;
    padding: 9px 0;
    border: none;
    border-radius: 8px;
    background: #21aba5;
    color: #fff;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    transition: background 0.2s;
  }
  .plan-detail-btn:hover { background: #1f7974; }
  #home-charts {
    flex: 2;
    min-height: 0;
    overflow: hidden;
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 14px;
  }
  .chart-box {
    position: relative;
    background: rgba(255,255,255,0.96);
    border: 1px solid #d3efe9;
    border-radius: 12px;
    padding: 12px;
    display: flex;
    flex-direction: column;
    min-width: 0;
  }
  .chart-box h5 {
    margin: 0 0 6px;
    font-size: 12px;
    color: #1f7974;
    font-weight: 600;
  }
  .chart-box > div:not(#drawer-wrap) {
    flex: 1;
    min-height: 0;
  }
  #drawer-outer {
    position: fixed;
    right: 0;
    top: var(--drawer-top, 65%);
    transform: translateY(-50%);
    z-index: 60;
  }
  #scheme-drawer {
    display: flex;
    align-items: stretch;
    transform: translateX(calc(100% - 34px));
    transition: transform 0.35s ease;
  }
  #drawer-outer.open #scheme-drawer {
    transform: translateX(0);
  }
  #drawer-tab {
    border: none;
    background: #21aba5;
    color: #fff;
    font-size: 12px;
    font-weight: 600;
    width: 34px;
    padding: 12px 0;
    border-radius: 10px 0 0 10px;
    cursor: grab;
    box-shadow: 0 4px 16px rgba(33,171,165,0.3);
    writing-mode: vertical-rl;
    letter-spacing: 2px;
    transition: background 0.2s;
    touch-action: none;
    user-select: none;
  }
  #drawer-tab:hover { background: #1f7974; }
  #drawer-panel {
    width: 260px;
    min-height: 52px;
    background: rgba(255,255,255,0.98);
    border: 1px solid #c5f5e8;
    border-radius: 12px 0 0 12px;
    box-shadow: 0 10px 30px rgba(15,42,38,0.15);
    padding: 10px;
    box-sizing: border-box;
    display: flex;
    flex-direction: column;
    justify-content: center;
  }
  #drawer-toggle {
    width: 100%;
    padding: 9px 0;
    border: 1px solid #c5f5e8;
    background: #f0fffd;
    color: #1f7974;
    font-size: 12px;
    font-weight: 600;
    border-radius: 8px;
    cursor: pointer;
    transition: background 0.2s, color 0.2s;
    flex-shrink: 0;
  }
  #drawer-toggle:hover { background: #e2f7f2; }
  #drawer-toggle.active { background: #21aba5; color: #fff; }
  #drawer-schemes {
    max-height: 0;
    overflow: hidden;
    opacity: 0;
    margin-top: 0;
    transition: max-height 0.3s ease, opacity 0.25s ease, margin-top 0.3s ease;
  }
  #scheme-drawer.expanded #drawer-schemes {
    max-height: 220px;
    opacity: 1;
    margin-top: 8px;
    overflow-y: auto;
  }
  @media (max-height: 850px) {
  #home-main {
    padding: 10px 16px 14px;
    gap: 10px;
  }
  .plan-card {
    padding: 10px;
  }
  .plan-metrics div {
    padding: 4px 6px;
  }
  .plan-thumb {
    min-height: 0;
  }
}

  @media (max-height: 650px) {
    #view-home {
      --topbar-h: 46px;
    }
    #home-topbar {
      padding: 0 16px;
    }
    .plan-card-name {
      font-size: 13px;
      margin-bottom: 6px;
    }
    .plan-card-head {
      margin-bottom: 2px;
    }
    .plan-metrics {
      gap: 5px;
      margin-bottom: 8px;
    }
    .plan-metrics b {
      font-size: 11px;
    }
    .plan-metrics span {
      font-size: 9px;
    }
    .plan-detail-btn {
      padding: 6px 0;
      font-size: 12px;
    }
    .chart-box {
      padding: 8px;
    }
    .chart-box h5 {
      font-size: 11px;
      margin-bottom: 4px;
    }
  }
  .drawer-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 10px;
    border-radius: 8px;
    cursor: pointer;
    transition: background 0.15s;
  }
  .drawer-item:hover { background: #f0fffd; }
  .drawer-item.active { background: #e2f7f2; }
  .drawer-id {
    font-size: 11px;
    font-weight: 700;
    color: #21aba5;
    min-width: 24px;
  }
  .drawer-name {
    flex: 1;
    font-size: 12px;
    color: #1e293b;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .drawer-thick {
    font-size: 11px;
    color: #64748b;
  }
`

export function initHome(data) {
  const style = document.createElement('style')
  style.textContent = HOME_STYLE
  document.head.appendChild(style)

  const root = document.getElementById('view-home')
  if (!root) return

    root.innerHTML = `
    <div id="home-topbar">
      <span style="display:flex; align-items:center; gap:10px;">
        <span class="bar-brand">稀土智暖 · 三方案对比</span>
        <span id="mock-badge">演示数据</span>
      </span>
      <div id="topbar-items" style="display:flex; gap:10px; flex-wrap:nowrap;"></div>
    </div>
    <div id="home-main">
      <div id="home-cards"></div>
      <div id="home-charts">
        <div class="chart-box">
          <h5>综合性能雷达图</h5>
          <div id="radar-chart"></div>
        </div>
        <div class="chart-box">
          <h5>节能率与年碳排对比</h5>
          <div id="bar-chart"></div>
        </div>
        <div class="chart-box">
          <h5>五阶段碳排瀑布图</h5>
          <div id="waterfall-chart"></div>
        </div>
      </div>
    </div>
    <div id="drawer-outer">
      <div id="scheme-drawer">
        <button id="drawer-tab">其他方案</button>
        <div id="drawer-panel">
          <button id="drawer-toggle">查看 6 种备选方案</button>
          <div id="drawer-schemes"></div>
        </div>
      </div>
    </div>
  `

  renderTopbar(data)
  buildCards(data)
  buildDrawer(data)
}

export function renderHome(data, activePlan) {
  renderTopbar(data)
  document.querySelectorAll('.plan-card').forEach(card => {
    card.classList.toggle('active', card.dataset.plan === activePlan)
  })
  setDrawerActive(activePlan)
  thumbnails.forEach(t => t.reset())
}

export function updateThumbnails() {
  thumbnails.forEach(t => t.update())
}

export function resizeThumbnails() {
  thumbnails.forEach(t => t.resize && t.resize())
}

function renderTopbar(data) {
  const building = getBuildingInfo(data)
  const proj = state.dataMode === 'live' ? {} : (jsonData.project_info || {})
  const items = [
    ['地点', building.city || proj.city || '-'],
    ['建筑类型', building.name || building.building_id || proj.building_type || '-'],
    ['面积', `${building.area_m2 || proj.area_m2 || '-'}㎡`],
    ['预算', proj.budget_yuan != null ? `${(proj.budget_yuan / 10000).toFixed(0)}万` : '-'],
    ['节能目标', proj.energy_target_pct != null ? `${proj.energy_target_pct}%` : '-']
  ]
  const wrap = document.getElementById('topbar-items')
  if (!wrap) return
  wrap.innerHTML = items.map(([label, value]) =>
    `<span class="bar-item">${label} <b>${value}</b></span>`
  ).join('')
}

function buildCards(data) {
  const wrap = document.getElementById('home-cards')
  if (!wrap) return
  wrap.innerHTML = ''
  thumbnails.forEach(t => t.dispose())
  thumbnails.length = 0

  getPlans(data).forEach(plan => {
    const card = document.createElement('div')
    card.className = 'plan-card'
    if (plan.plan_label === 'B') card.classList.add('featured')
    card.dataset.plan = plan.plan_label
    card.innerHTML = `
      <div class="plan-card-head">
        <span class="plan-label">方案 ${plan.plan_label}</span>
        <span class="plan-tag">${plan.recommend_tag || ''}</span>
      </div>
      <div class="plan-card-name">${plan.scheme_name}</div>
      <div class="plan-thumb"></div>
      <div class="plan-metrics">
        <div><span>材料厚度</span><b>${plan.thickness_mm ?? '—'}mm</b></div>
        <div><span>综合单价</span><b>${plan.cost?.unit_price_yuan_m2 ?? '—'}元/㎡</b></div>
        <div><span>节能率</span><b>${typeof plan.energy?.saving_rate_pct === 'number' ? plan.energy.saving_rate_pct.toFixed(2) : '—'}%</b></div>
        <div><span>初投资</span><b>${plan.cost?.initial_investment_wanyuan ?? '—'}万</b></div>
        <div><span>年碳排</span><b>${typeof plan.carbon?.annual_operation_tCO2 === 'number' ? plan.carbon.annual_operation_tCO2.toFixed(2) : '—'}t</b></div>
        <div><span>碳收益情景</span><b>${plan.ccer?.annual_value_yuan == null ? '未评估' : plan.ccer.annual_value_yuan+'元/年'}</b></div>
      </div>
      <button class="plan-detail-btn" data-plan="${plan.plan_label}">查看方案详情</button>
    `
    wrap.appendChild(card)

    const thumbBox = card.querySelector('.plan-thumb')
    const layers = buildLayers(plan, state.constructionLib)
    thumbnails.push(createSchemeThumbnail(thumbBox, layers, state.currentGeo))

    card.querySelector('.plan-detail-btn').addEventListener('click', e => {
      e.stopPropagation()
      window.navigateToDetail && window.navigateToDetail(plan.plan_label)
    })
  })
}

function buildDrawer(data) {
  const holder = document.getElementById('scheme-drawer')
  if (holder) holder.style.display = getAllSchemes(data).length ? '' : 'none'
  const outer = document.getElementById('drawer-outer')
  const drawer = document.getElementById('scheme-drawer')
  const schemesBox = document.getElementById('drawer-schemes')
  const tab = document.getElementById('drawer-tab')
  if (!outer || !drawer || !schemesBox || !tab) return

  const schemes = getAllSchemes(data)
  schemesBox.innerHTML = schemes.map(s => `
    <div class="drawer-item" data-id="${s.scheme_id}">
      <span class="drawer-id">${s.scheme_id}</span>
      <span class="drawer-name">${s.scheme_name}</span>
      <span class="drawer-thick">${s.thickness_mm}mm</span>
    </div>
  `).join('')

  let hoverTimer = null
  outer.addEventListener('mouseenter', () => {
    clearTimeout(hoverTimer)
    outer.classList.add('open')
  })
  outer.addEventListener('mouseleave', () => {
    hoverTimer = setTimeout(() => {
      outer.classList.remove('open')
      outer.classList.remove('expanded')
    }, 300)
  })

  const toggleBtn = document.getElementById('drawer-toggle')
  toggleBtn.addEventListener('click', () => {
    drawer.classList.toggle('expanded')
    toggleBtn.classList.toggle('active', drawer.classList.contains('expanded'))
  })

  // 按住竖条可沿右边缘拖动
  let dragging = false
  tab.addEventListener('pointerdown', e => {
    dragging = true
    tab.setPointerCapture(e.pointerId)
  })
  tab.addEventListener('pointermove', e => {
    if (!dragging) return
    const halfH = outer.offsetHeight / 2
    const minY = halfH + 8
    const maxY = window.innerHeight - halfH - 8
    const y = Math.max(minY, Math.min(maxY, e.clientY))
    outer.style.setProperty('--drawer-top', y + 'px')
  })
  tab.addEventListener('pointerup', () => {
    dragging = false
  })

  schemesBox.querySelectorAll('.drawer-item').forEach(item => {
    item.addEventListener('click', () => {
      const id = item.dataset.id
      setDrawerActive(id)
      window.selectScheme && window.selectScheme(id)
      window.navigateToDetail && window.navigateToDetail(id)
    })
  })
}

function setDrawerActive(id) {
  document.querySelectorAll('.drawer-item').forEach(item => {
    item.classList.toggle('active', item.dataset.id === id)
  })
}

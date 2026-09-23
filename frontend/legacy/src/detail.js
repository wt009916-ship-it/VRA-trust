import { state } from './config.js'
import { resolvePlanLike, getBuildingInfo } from './data.js'
import { createSection } from './section.js'
import { showDetailWaterfallStages } from './charts.js'
import jsonData from '../../../fixtures/demo/frontend-data/data.json'
import {fmt} from './safety.js'

const DETAIL_STYLE = `
  #view-detail {
    position: fixed;
    inset: 0;
    z-index: 3;
    background: #e6f7f5;
    font-family: system-ui, -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
    overflow: hidden;
  }
  #detail-nav {
    height: 56px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 20px;
    background: rgba(255,255,255,0.92);
    border-bottom: 1px solid #d3efe9;
    backdrop-filter: blur(10px);
  }
  #detail-nav button {
    border: 1px solid #c5f5e8;
    background: #f0fffd;
    color: #1f7974;
    font-size: 13px;
    font-weight: 600;
    padding: 8px 16px;
    border-radius: 20px;
    cursor: pointer;
    transition: background 0.2s;
  }
  #detail-nav button:hover { background: #d9f3ed; }
  #detail-nav #export-pdf-btn {
    background: #21aba5;
    border-color: #21aba5;
    color: #fff;
  }
  #detail-nav #export-pdf-btn:hover { background: #1f7974; }
  #detail-title {
    margin: 0;
    font-size: 16px;
    font-weight: 700;
    color: #1e293b;
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
  #detail-body {
    display: flex;
    height: calc(100vh - 56px);
    padding: 14px;
    gap: 14px;
    box-sizing: border-box;
    overflow: hidden;
  }
  #detail-left {
    flex: 1.1;
    display: flex;
    flex-direction: column;
    gap: 14px;
    min-width: 0;
    overflow: hidden;
  }
  #detail-3d {
    flex: 1;
    min-height: 0;
    border-radius: 12px;
    background: #dff3ee;
    overflow: hidden;
    position: relative;
  }
  #detail-section-wrap {
    height: 210px;
    background: rgba(255,255,255,0.96);
    border: 1px solid #d3efe9;
    border-radius: 12px;
    padding: 14px;
    box-sizing: border-box;
    flex-shrink: 0;
  }
  #detail-section-wrap .section-title {
    font-size: 12px;
    font-weight: 600;
    color: #1f7974;
    margin-bottom: 10px;
  }
  #section-view {
    height: 130px;
  }
  #detail-right {
    width: 420px;
    min-width: 360px;
    min-height: 0;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  #detail-right > .detail-module:nth-child(1) {
    flex: 1.4;
    min-height: 0;
    display: flex;
    flex-direction: column;
  }
  #detail-right > .detail-module:nth-child(2) {
    flex: 0 0 auto;
  }
  #detail-right > .detail-module:nth-child(3) {
    flex: 1.4;
    min-height: 0;
    display: flex;
    flex-direction: column;
  }
  #detail-right > .detail-module:nth-child(4) {
    flex: 0 0 auto;
  }
  #detail-right > .detail-module:nth-child(5) {
    flex: 0.7;
    min-height: 0;
    overflow: hidden;
  }
  .detail-module {
    background: rgba(255,255,255,0.96);
    border: 1px solid #d3efe9;
    border-radius: 12px;
    padding: 14px;
    flex-shrink: 0;
  }
  .detail-module h5 {
    margin: 0 0 10px;
    font-size: 13px;
    color: #1f7974;
    font-weight: 600;
  }
  #material-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
  }
  #material-table th, #material-table td {
    text-align: left;
    padding: 7px 8px;
    border-bottom: 1px solid #e2f0ee;
  }
  #material-table th {
    color: #64748b;
    font-weight: 600;
    background: #f8fcfc;
  }

  /* ===== 指标卡片：主题绿色系，无悬浮效果 ===== */
  #metric-cards {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 10px;
  }
  #metric-cards .metric {
    background: #f8fcfc;
    border: 1px solid #d3efe9;
    border-radius: 10px;
    padding: 14px 6px;
    text-align: center;
  }
  #metric-cards .metric .m-label {
    font-size: 11px;
    color: #64748b;
    font-weight: 500;
    margin-bottom: 6px;
  }
  #metric-cards .metric .m-value {
    font-size: 20px;
    font-weight: 700;
    color: #1f7974;
    line-height: 1.2;
    font-variant-numeric: tabular-nums;
  }
  #metric-cards .metric .m-unit {
    font-size: 10px;
    color: #94a3b8;
    margin-top: 4px;
  }

  #detail-waterfall-chart {
    height: 100%;
    min-height: 180px;
  }
  #ccer-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 10px;
  }
  #ccer-grid .ccer-item {
    text-align: center;
    background: #f0fffd;
    border-radius: 10px;
    padding: 12px 6px;
    border: 1px solid #c5f5e8;
  }
  #ccer-grid .ccer-item span {
    display: block;
    font-size: 10px;
    color: #94a3b8;
    margin-bottom: 4px;
  }
  #ccer-grid .ccer-item b {
    font-size: 15px;
    color: #1e293b;
  }
  #recommend-text {
    font-size: 12px;
    color: #475569;
    line-height: 1.7;
  }
`

/* 数字滚动动画 */
function animateMetricValues() {
  document.querySelectorAll('#metric-cards .m-value').forEach(el => {
    const rawTarget = el.dataset.target
    const suffix = el.dataset.suffix || ''
    const target = parseFloat(rawTarget)
    if (state.dataMode === 'live') { el.textContent = (Number.isFinite(target) ? fmt(target) : '未提供') + suffix; return }

    if (isNaN(target)) {
      el.textContent = (rawTarget || '0') + suffix
      return
    }

    const duration = 1400
    const startTime = performance.now()

    function easeOutQuart(t) {
      return 1 - Math.pow(1 - t, 4)
    }

    function step(now) {
      const progress = Math.min((now - startTime) / duration, 1)
      const eased = easeOutQuart(progress)
      const current = target * eased

      let formatted
      if (Number.isInteger(target)) {
        formatted = Math.round(current).toLocaleString()
      } else {
        const decimals = target < 10 ? 2 : 1
        formatted = current.toFixed(decimals)
      }

      el.textContent = formatted + suffix

      if (progress < 1) {
        requestAnimationFrame(step)
      } else {
        const final = Number.isInteger(target)
          ? target.toLocaleString()
          : target.toFixed(target < 10 ? 2 : 1)
        el.textContent = final + suffix
      }
    }

    requestAnimationFrame(step)
  })
}

export function initDetail(data) {
  const style = document.createElement('style')
  style.textContent = DETAIL_STYLE
  document.head.appendChild(style)

  const root = document.getElementById('view-detail')
  if (!root) return

  root.innerHTML = `
    <div id="detail-nav">
      <button id="back-home-btn">← 返回三方案对比</button>
      <span style="display:flex; align-items:center; gap:10px; min-width:0;">
        <h2 id="detail-title" style="white-space:nowrap;">方案详情</h2>
        <span id="mock-badge">演示数据</span>
      </span>
      <button id="export-pdf-btn">导出 PDF</button>
    </div>
    <div id="run-status-tip" style="display:none; margin:10px 20px 0; padding:8px 12px; border-radius:8px; background:#f8fafc; border:1px solid #e2e8f0; font-size:12px; line-height:1.5;"></div>
    <div id="detail-body">
      <div id="detail-left">
        <div id="detail-3d"></div>
        <div id="detail-section-wrap">
          <div class="section-title">墙体构造剖面展开</div>
          <div id="section-view"></div>
        </div>
      </div>
      <div id="detail-right">
        <div class="detail-module">
          <h5>材料构造清单</h5>
          <table id="material-table">
            <thead>
              <tr><th>层级</th><th>材料</th><th>厚度</th><th>导热系数 λ</th></tr>
            </thead>
            <tbody></tbody>
          </table>
        </div>
        <div class="detail-module">
          <h5>能耗与碳排指标</h5>
          <div id="metric-cards"></div>
        </div>
        <div class="detail-module">
          <h5>五阶段碳排瀑布图</h5>
          <div id="detail-waterfall-chart"></div>
        </div>
        <div class="detail-module">
          <h5>CCER 碳资产</h5>
          <div id="ccer-grid"></div>
        </div>
        <div class="detail-module">
          <h5>推荐理由</h5>
          <div id="recommend-text"></div>
        </div>
      </div>
    </div>
  `

  document.getElementById('back-home-btn').addEventListener('click', () => {
    window.navigateTo && window.navigateTo('home')
  })
  document.getElementById('export-pdf-btn').addEventListener('click', async () => {
    const btn = document.getElementById('export-pdf-btn')
    if (btn.disabled) return
    btn.disabled = true
    btn.textContent = '生成中...'
    try {
      await window.exportDetailPDF()
      btn.textContent = '导出 PDF'
    } catch (err) {
      console.error(err)
      btn.textContent = '导出失败，重试'
    } finally {
      btn.disabled = false
    }
  })
}

export function renderDetail(data, planKey) {
  if (!data) return
  const plan = resolvePlanLike(data, planKey)
  if (!plan) return

  document.getElementById('detail-title').textContent =
    `方案${plan.plan_label} · ${plan.scheme_name}`

  // 剖面动画
  const sectionView = document.getElementById('section-view')
  if (sectionView) createSection(sectionView, state.layers)

  // 材料清单
  const tbody = document.querySelector('#material-table tbody')
  if (tbody) {
    tbody.innerHTML = state.layers
      .filter(l => l.thickness > 0)
      .map(l => `
        <tr>
          <td>${l.role || l.name}</td>
          <td>${l.name}</td>
          <td>${(l.thickness * 1000).toFixed(0)} mm</td>
          <td>${l.lambda} W/(m·K)</td>
        </tr>
      `).join('')
  }

  // 四项指标 —— 主题绿色系 + 数字滚动
  const metrics = [
    { label: '能耗', value: plan.energy?.intensity_kWh_m2a ?? '—', unit: 'kWh/(㎡·a)', suffix: '' },
    { label: '节能率', value: plan.energy?.saving_rate_pct ?? '—', unit: '', suffix: '%' },
    { label: '年碳排', value: plan.carbon?.annual_operation_tCO2 ?? '—', unit: 'tCO₂', suffix: '' },
    { label: '外墙K值', value: plan.u_value ?? '—', unit: 'W/(㎡·K)', suffix: '' }
  ]
  const metricBox = document.getElementById('metric-cards')
  if (metricBox) {
    metricBox.innerHTML = metrics.map(m => `
      <div class="metric">
        <div class="m-label">${m.label}</div>
        <div class="m-value" data-target="${m.value}" data-suffix="${m.suffix}">0${m.suffix}</div>
        <div class="m-unit">${m.unit}</div>
      </div>
    `).join('')

    requestAnimationFrame(() => animateMetricValues())
  }

  // 瀑布图 —— 只调整顶部边距防止标签截断，不修改其他配置
  const stageKeys = ['production', 'transport', 'construction', 'operation', 'demolition']
  const stages = state.dashboardData?.charts?.waterfall?.stages || ['建材生产', '运输', '施工', '运行(50年)', '拆除']
  const values = stageKeys.map(k => plan.carbon_stages_tCO2?.[k] ?? null)
  showDetailWaterfallStages(stages, values)

  // CCER
  const ccerBox = document.getElementById('ccer-grid')
  if (ccerBox && plan.ccer) {
    ccerBox.innerHTML = [
      ['年减排量', `${plan.ccer?.annual_reduction_tCO2 ?? '—'} t`],
      ['年价值', `${plan.ccer?.annual_value_yuan ?? '—'} 元`],
      ['10年总收益', `${plan.ccer?.total_10y_yuan ?? '—'} 元`]
    ].map(([label, value]) => `
      <div class="ccer-item">
        <span>${label}</span>
        <b>${value}</b>
      </div>
    `).join('')
  }

  // 推荐理由
  const rec = document.getElementById('recommend-text')
  if (rec) {
    const proj = jsonData.project_info || {}
    const area = getBuildingInfo(data).area_m2 || proj.area_m2 || '-'
    rec.textContent = `${plan.recommend_tag ? `${plan.recommend_tag}：` : ''}` +
      `${plan.scheme_name}，${state.dataMode === 'live' ? '新增' : ''}保温厚度${fmt(plan.thickness_mm)}mm，` +
      `节能率约${fmt(plan.energy?.saving_rate_pct)}%，年碳排约${fmt(plan.carbon?.annual_operation_tCO2)}tCO₂，` +
      `外墙K值${fmt(plan.u_value,3)} W/(㎡·K)。碳资产开发未核验，不承诺CCER收益。` +
      (state.dataMode === 'live' ? ' 建筑外观为历史示意；构造参数取自参考IDF，K值为假设表面热阻下估算，运行碳口径见工作台。' : ' 当前为历史演示数据。')
  }
}

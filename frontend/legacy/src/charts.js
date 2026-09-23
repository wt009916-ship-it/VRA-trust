import * as echarts from 'echarts'

let radarChart = null
let barChart = null
let waterfallChart = null
let detailWaterfallChart = null
let currentData = null

const PLAN_COLORS = ['#21aba5', '#f59e0b', '#3b82f6']

export function initCharts() {
  const r = document.getElementById('radar-chart')
  const b = document.getElementById('bar-chart')
  const w = document.getElementById('waterfall-chart')
  const dw = document.getElementById('detail-waterfall-chart')
  if (!r || !b || !w) return

  radarChart = echarts.init(r)
  barChart = echarts.init(b)
  waterfallChart = echarts.init(w)
  if (dw) detailWaterfallChart = echarts.init(dw)

  function resizeAllCharts() {
    ;[radarChart, barChart, waterfallChart, detailWaterfallChart].forEach(ch => {
      if (!ch) return
      const dom = ch.getDom()
      const w = dom.clientWidth
      const h = dom.clientHeight
      if (w && h) ch.resize({ width: w, height: h })
    })
  }

  if (typeof ResizeObserver !== 'undefined') {
    const ro = new ResizeObserver(() => resizeAllCharts())
    ;[r, b, w, dw].forEach(el => el && ro.observe(el))
  }

  let raf = null
  window.addEventListener('resize', () => {
    if (raf) cancelAnimationFrame(raf)
    raf = requestAnimationFrame(() => {
      resizeAllCharts()
      setTimeout(resizeAllCharts, 80)
    })
  })
}

export function ensureChartsFit() {
  const charts = [radarChart, barChart, waterfallChart, detailWaterfallChart]
  const pr = window.devicePixelRatio || 1
  charts.forEach(ch => {
    if (!ch) return
    const dom = ch.getDom()
    const cw = dom.clientWidth
    const chh = dom.clientHeight
    if (!cw || !chh) return
    const canvas = dom.querySelector('canvas')
    if (!canvas) return
    if (
      Math.abs(canvas.width - cw * pr) > 2 ||
      Math.abs(canvas.height - chh * pr) > 2
    ) {
      ch.resize({ width: cw, height: chh })
    }
  })
}

// 新任务开始/失败时清空上一次成功数值
export function clearCharts() {
  ;[radarChart, barChart, waterfallChart, detailWaterfallChart].forEach(ch => {
    if (ch) ch.clear()
  })
}

export function updateCharts(json) {
  if (!json?.comparison?.radar_dimensions) return
  if (!radarChart || !barChart || !waterfallChart) return

  const comp = json.comparison.radar_dimensions
  const schemes = json.schemes
  // 🔧 从 JSON 里自动提取每个方案的代表色（取保温层颜色）
  const colors = schemes.map(s => {
    const insLayer = s.construction.layers.find(l => l.is_insulation)
    // 有保温层且颜色有效 → 用保温层颜色；否则默认灰色
    return (insLayer && insLayer.color_hex) ? insLayer.color_hex : '#94a3b8'
  })

  const names = schemes.map(s => s.scheme_name)

  // ---------- 雷达图 ----------
  const indicators = [
    { name: '节能率', max: Math.max(...comp.energy_saving_pct, 100) },
    { name: '成本', max: Math.max(...comp.initial_cost_yuan_m2, 500) },
    { name: '碳排', max: Math.max(...comp.annual_carbon_kg_m2, 10) },
    { name: 'CCER', max: Math.max(...comp.ccer_value_yuan_m2, 1000) },
    { name: '施工难度', max: Math.max(...comp.construction_difficulty, 100) }
  ]

  const radarSeries = names.map((name, i) => ({
    name,
    value: [
      comp.energy_saving_pct[i],
      comp.initial_cost_yuan_m2[i],
      comp.annual_carbon_kg_m2[i],
      comp.ccer_value_yuan_m2[i],
      comp.construction_difficulty[i]
    ],
    lineStyle: { color: colors[i], width: 2 },
    itemStyle: { color: colors[i] },
    areaStyle: { color: colors[i], opacity: 0.08 }
  }))

  radarChart.setOption({
    tooltip: { trigger: 'item' },
    legend: { data: names, bottom: 0, textStyle: { fontSize: 10 }, itemGap: 12 },
    radar: {
      indicator: indicators,
      shape: 'polygon',
      splitNumber: 4,
      axisName: { color: '#64748b', fontSize: 10 },
      center: ['50%', '45%'],
      radius: '55%'
    },
    series: [{ type: 'radar', data: radarSeries }]
  }, true)

  // ---------- 柱状图 ----------
  const dims = ['节能率(%)', '成本(元/㎡)', '碳排(kg/㎡)', 'CCER价值', '施工难度']
  const barSeries = names.map((name, i) => ({
    name,
    type: 'bar',
    data: [
      comp.energy_saving_pct[i],
      comp.initial_cost_yuan_m2[i],
      comp.annual_carbon_kg_m2[i],
      comp.ccer_value_yuan_m2[i],
      comp.construction_difficulty[i]
    ],
    itemStyle: { color: colors[i] }
  }))

  barChart.setOption({
    tooltip: { trigger: 'axis' , confine: true },
    legend: { data: names, bottom: 0, textStyle: { fontSize: 10 }, itemGap: 12 },
    grid: { left: '3%', right: '4%', bottom: '25%', top: '5%', containLabel: true },
    xAxis: { type: 'category', data: dims, axisLabel: { fontSize: 9, rotate: 20 } },
    yAxis: { type: 'value', axisLabel: { fontSize: 9 } },
    series: barSeries
  }, true)

  // ---------- 瀑布图 ----------
  const costs = comp.initial_cost_yuan_m2
  const base = Math.min(...costs)
  const aHeight = Math.max(0, costs[0] - base)
  const bHeight = Math.max(0, costs[1] - costs[0])
  const cHeight = Math.max(0, costs[2] - costs[1])

  waterfallChart.setOption({
    tooltip: {
      trigger: 'axis',
            formatter: (params) => {
        const tar = params.find(p => p.seriesName === '成本')
        if (!tar) return ''
        const label = tar.name === '基础' ? '成本' : '增量'
        return `${tar.name}<br/>${label}: ${tar.value} 元/㎡`
      }
    },
    grid: { left: '3%', right: '4%', bottom: '12%', top: '8%', containLabel: true },
    xAxis: {
      type: 'category',
      data: ['基础', '方案A', '方案B', '方案C'],
      axisLabel: { fontSize: 9 }
    },
    yAxis: { type: 'value', axisLabel: { fontSize: 9 } },
    series: [
      {
        name: '辅助',
        type: 'bar',
        stack: '总量',
        itemStyle: { color: 'transparent' },
        data: [0, base, costs[0], costs[1]],
        silent: true
      },
      {
        name: '成本',
        type: 'bar',
        stack: '总量',
        itemStyle: { color: '#21aba5' },
        data: [base, aHeight, bHeight, cHeight]
      }
    ]
  }, true)
}

// ===================== 新版 dashboard 图表 =====================

// 首页：雷达 + 柱状 + 瀑布
export function updateHomeCharts(data, activePlan = 'A') {
  currentData = data
  clearCharts()
  const charts = data?.charts
  if (!charts) return

  if (radarChart && charts.radar) updateRadar(charts.radar)
  if (barChart) updateBar(data)
  if (waterfallChart && charts.waterfall) updateWaterfallCompare(charts.waterfall, waterfallChart)
}

// 详情页：五阶段碳排瀑布
export function updateDetailWaterfall(planKey = 'A') {
  if (!currentData?.charts?.waterfall || !detailWaterfallChart) return
  detailWaterfallChart.resize()
  updateWaterfall(currentData.charts.waterfall, planKey, detailWaterfallChart)
}

// 侧边抽屉选择方案时切换首页瀑布
export function switchHomeWaterfall(planKey) {
  if (!currentData?.charts?.waterfall) return
  updateWaterfall(currentData.charts.waterfall, planKey, waterfallChart)
}

// 雷达图：初投资/年碳排反转归一化
function updateRadar(radar) {
  const series = radar.series || []
  const dims = radar.dimensions || []
  const reversedIdx = [1, 2] // 初投资、年碳排：越小越好
  const maxes = dims.map((_, di) =>
    Math.max(...series.map(s => s.values[di] ?? 0))
  )

  const data = series.map((s, i) => ({
    name: `方案${s.plan}`,
    value: s.values.map((v, di) => {
      const raw = reversedIdx.includes(di) ? maxes[di] - v : v
      return maxes[di] > 0 ? +((raw / maxes[di]) * 100).toFixed(1) : 0
    }),
    lineStyle: { color: PLAN_COLORS[i], width: 2 },
    itemStyle: { color: PLAN_COLORS[i] },
    areaStyle: { color: PLAN_COLORS[i], opacity: 0.08 }
  }))

  radarChart.setOption({
    tooltip: { trigger: 'item' },
    legend: { data: data.map(d => d.name), bottom: 0, textStyle: { fontSize: 10 }, itemGap: 12 },
    radar: {
      indicator: dims.map(name => ({ name, max: 100 })),
      shape: 'polygon',
      splitNumber: 4,
      axisName: { color: '#64748b', fontSize: 10 },
      center: ['50%', '46%'],
      radius: '56%'
    },
    series: [{ type: 'radar', data }]
  }, true)
}

// 柱状图：节能率 + 年碳排，双 Y 轴
function updateBar(data) {
  const plans = data.plans || []
  const cats = plans.map(p => `方案${p.plan_label}`)
  const savings = plans.map(p => p.energy?.saving_rate_pct ?? null)
  const carbons = plans.map(p => p.carbon?.annual_operation_tCO2 ?? null)

  barChart.setOption({
    tooltip: { trigger: 'axis', confine: true },
    legend: { data: ['节能率', '年碳排'], bottom: 0, textStyle: { fontSize: 10 }, itemGap: 12 },
    grid: { left: '3%', right: '4%', bottom: '22%', top: '14%', containLabel: true },
    xAxis: { type: 'category', data: cats, axisLabel: { fontSize: 10 } },
    yAxis: [
      {
        type: 'value',
        name: '节能率%',
        nameTextStyle: { fontSize: 9, color: '#64748b' },
        axisLabel: { fontSize: 9, formatter: '{value}%' }
      },
      {
        type: 'value',
        name: '年碳排 tCO₂',
        nameTextStyle: { fontSize: 9, color: '#64748b' },
        axisLabel: { fontSize: 9 }
      }
    ],
    series: [
      {
        name: '节能率',
        type: 'bar',
        yAxisIndex: 0,
        data: savings,
        itemStyle: { color: '#21aba5', borderRadius: [3, 3, 0, 0] },
        barWidth: 22
      },
      {
        name: '年碳排',
        type: 'bar',
        yAxisIndex: 1,
        data: carbons,
        itemStyle: { color: '#f59e0b', borderRadius: [3, 3, 0, 0] },
        barWidth: 22
      }
    ]
  }, true)
}

// 瀑布图：五阶段碳排
function updateWaterfall(wf, planKey, chart) {
  if (!chart) return
  const ser = wf.series.find(s => s.plan === planKey) || wf.series[0]
  const values = ser?.values || []
  const stages = wf.stages || []
  setWaterfallOption(chart, stages, values)
}

// 侧边 S0-S5 全量方案没有 charts.waterfall series，用方案自身 carbon_stages 动态画
export function showHomeWaterfallStages(stages, values) {
  if (waterfallChart) setWaterfallOption(waterfallChart, stages, values)
}

export function showDetailWaterfallStages(stages, values) {
  if (detailWaterfallChart) {
    detailWaterfallChart.clear()
    detailWaterfallChart.resize()
    setWaterfallOption(detailWaterfallChart, stages, values)
  }
}

function setWaterfallOption(chart, stages, values) {
  if (!chart) return
  if (!values?.length || values.some(v => typeof v !== 'number' || !Number.isFinite(v))) {
    chart.setOption({graphic:{type:'text',left:'center',top:'middle',style:{text:'生命周期资料不完整\n未提供的阶段不按零计算',fill:'#64748b',fontSize:12,textAlign:'center'}}},true)
    return
  }
  const helper = values.map((_, i) =>
    values.slice(0, i).reduce((a, b) => a + b, 0)
  )

  chart.setOption({
    tooltip: {
      trigger: 'axis',
      formatter: params => {
        const tar = params.find(p => p.seriesName === '碳排')
        return tar ? `${tar.name}<br/>碳排: ${tar.value} tCO₂` : ''
      }
    },
    grid: { left: '3%', right: '4%', bottom: '14%', top: 25, containLabel: true },
    xAxis: { type: 'category', data: stages, axisLabel: { fontSize: 9 } },
    yAxis: {
      type: 'value',
      name: 'tCO₂',
      nameTextStyle: { fontSize: 9, color: '#64748b' },
      axisLabel: { fontSize: 9 }
    },
    series: [
      {
        name: '辅助',
        type: 'bar',
        stack: '碳',
        itemStyle: { color: 'transparent' },
        data: helper,
        silent: true
      },
      {
        name: '碳排',
        type: 'bar',
        stack: '碳',
        itemStyle: { color: '#21aba5', borderRadius: [3, 3, 0, 0] },
        data: values
      }
    ]
  }, true)
}

function updateWaterfallCompare(wf, chart) {
  if (!chart) return
  const stages = wf.stages || []
  // 图例颜色显式指定，避免透明辅助柱抢走图例方块颜色
  const legendData = (wf.series || []).map((s, i) => ({
    name: `方案${s.plan}`,
    itemStyle: { color: PLAN_COLORS[i] || '#21aba5' }
  }))

  // 每个方案两根同名 series：透明辅助柱在底部，彩色增量柱在上
  const series = []
  ;(wf.series || []).forEach((s, i) => {
    const plan = s.plan
    const name = `方案${plan}`
    const values = s.values || []
    const helper = values.map((_, idx) =>
      values.slice(0, idx).reduce((a, b) => a + b, 0)
    )
    const color = PLAN_COLORS[i] || '#21aba5'

    series.push({
      name,
      type: 'bar',
      stack: `瀑布${plan}`,
      itemStyle: { color: 'transparent' },
      data: helper,
      silent: true,
      tooltip: { show: false },
      barGap: '20%'
    })
    series.push({
      name,
      type: 'bar',
      stack: `瀑布${plan}`,
      data: values,
      itemStyle: { color, borderRadius: [3, 3, 0, 0] }
    })
  })

  chart.setOption({
      tooltip: {
        trigger: 'axis',
        formatter: params => {
          const list = params.filter(p => p.seriesName.startsWith('方案'))
          if (!list.length) return ''
          return `${params[0].name}<br/>` +
            list.map(p => `${p.seriesName}: ${p.value} tCO₂`).join('<br/>')
        }
      },
      legend: {
        data: legendData,
        bottom: 0,
        textStyle: { fontSize: 10 },
        itemGap: 12
      },
      grid: { left: '3%', right: '4%', bottom: '22%', top: 42, containLabel: true },
      xAxis: { type: 'category', data: stages, axisLabel: { fontSize: 9 } },
      yAxis: {
        type: 'value',
        name: 'tCO₂',
        nameTextStyle: { fontSize: 9, color: '#64748b' },
        axisLabel: { fontSize: 9 }
      },
      series
  }, true)
}

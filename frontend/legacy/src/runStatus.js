import { state } from './config.js'
import { clearCharts } from './charts.js'

const STATUS_TEXT = {
  queued: '排队中',
  running: '计算中',
  failed: '计算失败',
  success: '计算完成',
  succeeded: '计算完成',
  stale: '结果已失效'
}

const STATUS_COLOR = {
  queued: '#94a3b8',
  running: '#3b82f6',
  failed: '#ef4444',
  success: '#16a34a',
  succeeded: '#16a34a',
  stale: '#b45309'
}

// 更新页面上的数据来源/任务状态标识（首页与详情页共用 #mock-badge）
export function updateRunStatusUI(meta) {
  const isLive = state.dataMode === 'live'
  const status = meta?.status || 'queued'
  document.querySelectorAll('button[onclick*="exportDetailPDF"]').forEach(el => {
    el.disabled = isLive && (!state.validatedComparison || !['succeeded','success'].includes(status))
  })
  const label = !isLive
    ? '演示数据'
    : `${STATUS_TEXT[status] || status}${meta?.run_id ? ' · ' + meta.run_id : ''}`

  document.querySelectorAll('#mock-badge').forEach(el => {
    el.textContent = label
    if (isLive) {
      const color = STATUS_COLOR[status] || '#94a3b8'
      el.style.color = color
      el.style.borderColor = color
      el.style.background = '#ffffff'
    } else {
      el.style.color = '#b45309'
      el.style.borderColor = '#fcd34d'
      el.style.background = '#fef3c7'
    }
  })

  const tip = document.getElementById('run-status-tip')
  if (!tip) return
  if (!isLive) {
    tip.style.display = 'none'
    tip.textContent = ''
    return
  }
  tip.style.display = 'block'
  if (status === 'failed' || status === 'stale') {
    tip.style.color = '#b91c1c'
    tip.textContent = `计算失败：${meta?.error?.message || meta?.error?.code || '未知错误'}（run_id: ${meta?.run_id || '-'}）`
  } else if (status === 'queued') {
    tip.style.color = '#64748b'
    tip.textContent = `任务已排队，等待计算…（run_id: ${meta?.run_id || '-'}）`
  } else if (status === 'running') {
    tip.style.color = '#1d4ed8'
    tip.textContent = `任务计算中，结果稍后刷新…（run_id: ${meta?.run_id || '-'}）`
  } else {
    tip.style.color = '#166534'
    tip.textContent = `结果来源：${meta?.source || '外部仿真'} · run_id: ${meta?.run_id || '-'}`
  }
}

// 新任务开始或失败时：清空上一次成功数值与旧推荐语
export function clearRunOutputs(meta) {
  clearCharts()

  document.querySelectorAll('.plan-metrics b').forEach(el => {
    el.textContent = '—'
  })

  const metric = document.getElementById('metric-cards')
  if (metric) metric.innerHTML = ''

  const ccer = document.getElementById('ccer-grid')
  if (ccer) ccer.innerHTML = ''

  const material = document.querySelector('#material-table tbody')
  if (material) material.innerHTML = ''

  const rec = document.getElementById('recommend-text')
  if (rec) {
    rec.textContent = meta?.status === 'failed'
      ? '本次计算失败，未产生结果。'
      : '本次任务尚未产生结果，等待计算完成。'
  }

  updateRunStatusUI(meta)
  document.querySelectorAll('button[onclick*="exportDetailPDF"]').forEach(el => { el.disabled = true })
}

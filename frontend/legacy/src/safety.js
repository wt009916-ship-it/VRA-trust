export function escapeHTML(v) {
  return String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]))
}
export function finiteOrNull(v) { return typeof v === 'number' && Number.isFinite(v) ? v : null }
export function fmt(v, digits = 2) { return finiteOrNull(v) == null ? '未提供' : v.toLocaleString('zh-CN', { maximumFractionDigits: digits }) }
export function safeObject(value) {
  if (typeof value === 'string') return escapeHTML(value)
  if (Array.isArray(value)) return value.map(safeObject)
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).filter(([k]) => !['__proto__','constructor','prototype'].includes(k)).map(([k,v]) => [k,safeObject(v)]))
  return value
}

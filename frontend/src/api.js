let csrfToken = '';
let maxUploadBytes = 64 * 1024 * 1024;
export function uploadLimitMB() { return maxUploadBytes / 1024 / 1024; }
export function checkUpload(file) {
  if (!file || typeof file.size !== 'number' || file.size === 0) throw new Error('请选择非空文件');
  if (file.size > maxUploadBytes) throw new Error(`文件 ${(file.size / 1024 / 1024).toFixed(1)} MB，超过服务端 ${uploadLimitMB()} MB 上限；请按楼层或图页拆分。`);
}
export function setCsrfToken(value) { csrfToken = value || ''; }
export async function request(path, options = {}) {
  if (path.endsWith('/files') && options.body instanceof FormData) checkUpload(options.body.get('file'));
  const headers = options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' };
  const response = await fetch('/api' + path, { ...options, credentials: 'same-origin', headers: { ...headers, ...(csrfToken ? {'X-CSRF-Token': csrfToken} : {}), ...options.headers }, cache: 'no-store' });
  let invalidJson = false;
  const data = await response.json().catch(() => { invalidJson = true; return null; });
  if (!response.ok) {
    const detail = data?.detail;
    const error = new Error(Array.isArray(detail) ? detail.map(x => x.loc.join('.') + ': ' + x.msg).join('; ') : detail || '请求失败 (' + response.status + ')');
    error.status = response.status;
    if (response.status === 401 && !path.startsWith('/auth/')) document.dispatchEvent(new Event('session-expired'));
    throw error;
  }
  if (invalidJson) throw new Error('服务返回了无法读取的数据，请稍后重试');
  if (path === '/health' && Number.isSafeInteger(data?.upload_policy?.max_file_bytes) && data.upload_policy.max_file_bytes > 0) maxUploadBytes = data.upload_policy.max_file_bytes;
  return data;
}
export const post = (path, body) => request(path, { method: 'POST', body: JSON.stringify(body) });
export function number(value, digits = 2) {
  return typeof value === 'number' && Number.isFinite(value) ? value.toLocaleString('zh-CN', { maximumFractionDigits: digits }) : '—';
}
export function escape(value) {
  return String(value ?? '').replace(/[&<>"']/g, x => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[x]);
}
export function latestSchemes(runs) {
  const found = new Map();
  for (const run of runs) if (!found.has(run.scheme_id)) found.set(run.scheme_id, run);
  return [...found.values()];
}
export function resultValue(run, key) {
  return run?.status === 'succeeded' ? run.metrics?.[key] ?? null : null;
}
export function comparisonIsCurrent(runs, comparedIds) {
  const latest = latestSchemes(runs);
  return comparedIds.length >= 2 && latest.length === comparedIds.length &&
    latest.every(run => run.status === 'succeeded' && comparedIds.includes(run.run_id));
}

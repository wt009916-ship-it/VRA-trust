let csrfToken = '';
let maxUploadBytes = 64 * 1024 * 1024;
export function uploadLimitMB() { return maxUploadBytes / 1024 / 1024; }
export function checkUpload(file) {
  if (!file || typeof file.size !== 'number' || file.size === 0) throw new Error('请选择非空文件');
  if (file.size > maxUploadBytes) throw new Error(`文件 ${(file.size / 1024 / 1024).toFixed(1)} MB，超过服务端 ${uploadLimitMB()} MB 上限；请按楼层或图页拆分。`);
}
export function setCsrfToken(value) { csrfToken = value || ''; }
const writes = new Map();
export function request(path, options = {}) {
  const method=(options.method||'GET').toUpperCase();
  if(['GET','HEAD'].includes(method)||typeof options.body!=='string')return performRequest(path,options);
  const key=method+' '+path+' '+options.body;
  if(writes.has(key))return writes.get(key);
  if(writes.size>=32)return Promise.reject(new Error('提交任务过多，请等待当前请求结束'));
  const pending=performRequest(path,options).finally(()=>writes.delete(key));
  writes.set(key,pending);return pending;
}
async function performRequest(path, options = {}) {
  const slow=path.endsWith('/imports')||path.endsWith('/components')||path.includes('/model/validate')||path.includes('/runtime-backup');
  const {timeoutMs=slow?180000:path.endsWith('/provider/test')?185000:60000,signal,...fetchOptions}=options;
  const controller=new AbortController(),abort=()=>controller.abort();
  if(signal?.aborted)abort();else signal?.addEventListener('abort',abort,{once:true});
  const timer=setTimeout(abort,timeoutMs);
  try { return await fetchRequest(path,fetchOptions,controller.signal); }
  catch(error){
    if(controller.signal.aborted&&!signal?.aborted){
      const failure=new Error('请求超时。若正在保存或提交任务，结果尚未确认，请先检查最新记录，避免重复提交。');
      failure.status=0;failure.ambiguous=!['GET','HEAD'].includes(options.method||'GET');throw failure;
    }
    throw error;
  } finally { clearTimeout(timer);signal?.removeEventListener('abort',abort); }
}
async function fetchRequest(path, options, signal) {
  if (path.endsWith('/files') && options.body instanceof FormData) checkUpload(options.body.get('file'));
  const startedCsrf=csrfToken;
  const headers = options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' };
  const response = await fetch('/api' + path, { ...options, signal, credentials: 'same-origin', headers: { ...headers, ...(csrfToken ? {'X-CSRF-Token': csrfToken} : {}), ...options.headers }, cache: 'no-store' });
  let invalidJson = false;
  const data = await response.json().catch(() => { invalidJson = true; return null; });
  if (!response.ok) {
    const detail = data?.detail;
    const error = new Error(Array.isArray(detail) ? detail.map(x => x.loc.join('.') + ': ' + x.msg).join('; ') : detail || '请求失败 (' + response.status + ')');
    error.status = response.status;
    error.retryAfter = Number(response.headers.get('Retry-After')) || null;
    if(response.status===403&&detail==='会话校验失败，请刷新后重试'){
      document.dispatchEvent(new Event('session-refresh-required'));
      error.message='登录状态已更新，正在重新校验。请稍后重试本次操作。';
    }
    if (response.status === 401 && startedCsrf===csrfToken && (!path.startsWith('/auth/')||path==='/auth/security'||path==='/auth/sessions')) document.dispatchEvent(new Event('session-expired'));
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

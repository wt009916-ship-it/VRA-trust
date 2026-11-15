import {escape as esc} from './api.js';
const nature={model_scenario:'原生模型情景，非实测',synthetic:'合成参考账单',published_reference:'公开参考账单',measured:'声明实测账单，真实性仍需核验'};
const basis={hourly_meter_integral:'逐时计量积分',native_table_rounded:'原生表舍入值',bill_interval_statistics:'声明账期比较',native_clock_count:'原生时钟计数'};
export function energyContextMarkup(c){
 if(!c)return '';
 return `<p class="subtle">原生年 ${esc(c.native_year??'未知')} · ${esc(c.carrier)} · ${esc(c.boundary)} · ${esc(basis[c.basis]||c.basis)}。${esc(nature[c.data_nature]||c.data_nature)}。</p><p>原生期间 ${esc(c.native_start??'未知')} → ${esc(c.native_end??'未知')}${c.bill_start?`；原账单期间 ${esc(c.bill_start)} → ${esc(c.bill_end)}`:''}。${c.alignment==='calendar_pattern'?'参考日历映射，不是同期校准。':'开始含、结束不含。'}${c.uses_daylight_saving?'原生时钟含夏令时；不是本地标准时账单配对。':''}</p>`;
}
export function energyArtifactMarkup(a){
 const head=`<h3>${esc(a.name)}</h3><p>${esc(a.scope)}</p>`;
 if(!a.verified||!a.result||a.status==='stale')return `<section class="agent-artifact">${head}<p role="status">当前来源无法核验，旧能耗、账单指标和报告入口已撤下。</p></section>`;
 const c=a.energy_context||{},route=a.kind==='enduse_review'?'end-use-ledgers':'utility-comparisons';
 return `<section class="agent-artifact">${head}<p>数据口径：${esc(nature[c.data_nature||c.bill_nature]||'原生模型情景')}；原生年 ${esc(c.native_year??'未知')}。所问数值及具体载体/期间见上方逐项核验记录；没有交付的指标不算完成。</p><p>未取得实楼校准或任何认证。<a href="/api/projects/${encodeURIComponent(a.project_id)}/${route}/${encodeURIComponent(a.record_id)}/report.html" target="_blank" rel="noopener">查看完整同源报告</a></p></section>`;
}

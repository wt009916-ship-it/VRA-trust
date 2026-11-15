import {post,escape as esc,number as fmt} from './api.js';

const labels={keep_unknown:'含义未知',reject_hypothesis:'拒绝补线假设',retain_hypothesis:'保留几何假设，尚未经工程确认'};
function lineMarkup(row,color,dash=''){
  const [a,b]=row.points_source_px;
  return `<line data-gap-id="${esc(row.candidate_id)}" x1="${esc(a[0])}" y1="${esc(a[1])}" x2="${esc(b[0])}" y2="${esc(b[1])}" stroke="${color}" stroke-width="2" ${dash?'stroke-dasharray="3 2"':''}><title>${esc(row.candidate_id)}</title></line>`;
}

export function lineworkMarkup(record,base){
  const work=record.result?.linework;
  if(record.status==='stale'||!work)return '';
  const url=`/api${base}/drawings/${record.drawing_id}`;
  const reviews=record.line_reviews||{},[width,height]=work.source_size;
  return `<section id="drawing-linework"><h2>线段与疑似断点</h2><p>${work.lines.length} 个线段候选 · ${work.gaps.length} 个短间隔假设。${work.truncated?'已达到分析数量限制，结果不完整。':''}未自动补线，也未识别为墙、门窗或结构构件。</p><details><summary>对照原方向图页并复核断点</summary><p>蓝线是暗像素线段候选，黄虚线是含义未知的间隔，红线是人工保留的几何假设。底图为原方向分析缩略图。</p><div class="drawing-canvas" style="aspect-ratio:${width}/${height}"><img src="${url}/derivatives/linework-preview.png" alt="原方向分析缩略图；未填补断点"><svg viewBox="0 0 ${width} ${height}" role="img" aria-label="观测线段与未证实的补线假设">${work.lines.map(row=>lineMarkup(row,'#3587a4')).join('')}${work.gaps.filter(row=>reviews[row.candidate_id]?.decision!=='reject_hypothesis').map(row=>lineMarkup(row,reviews[row.candidate_id]?.decision==='retain_hypothesis'?'#c13535':'#b87910',reviews[row.candidate_id]?.decision!=='retain_hypothesis')).join('')}</svg></div>${work.gaps.length?`<form id="drawing-line-review"><label>疑似断点<select name="candidate_id">${work.gaps.map(g=>`<option value="${esc(g.candidate_id)}">${esc(g.candidate_id)} · 分析图间隔 ${fmt(g.gap_analysis_px,2)} px</option>`).join('')}</select></label><div id="drawing-line-current"></div><label>复核决定<select name="decision"><option value="keep_unknown">保持未知</option><option value="reject_hypothesis">拒绝补线假设</option><option value="retain_hypothesis">保留几何假设，尚未经工程确认</option></select></label><label>原图依据与未解决的问题<textarea name="basis" minlength="10" maxlength="2000" required></textarea></label><button>保存断点复核</button></form>`:'<p>未生成断点候选，不表示图纸没有缺损。</p>'}<p><a href="${url}/line-overlay.svg" download>导出带原图缩略图的核查层 SVG</a> · 原件仍可单独下载。导出保留来源摘要和复核依据，不替代工程图纸。</p><ul>${work.limitations.map(text=>`<li>${esc(text)}</li>`).join('')}</ul></details></section>`;
}

export function attachLinework(host,record,base,action,reload){
  const form=host.querySelector('#drawing-line-review');if(!form)return;
  function select(){
    const saved=record.line_reviews?.[form.elements.candidate_id.value];
    host.querySelector('#drawing-line-current').innerHTML=`<p>当前状态：${esc(labels[saved?.decision]||'尚未复核')}。${saved?`依据：${esc(saved.basis)}`:''}</p>`;
    form.elements.decision.value='keep_unknown';form.elements.basis.value='';
  }
  form.elements.candidate_id.onchange=select;select();
  for(const line of host.querySelectorAll('[data-gap-id^="gap_"]'))line.onclick=()=>{form.elements.candidate_id.value=line.dataset.gapId;select();};
  form.onsubmit=event=>{
    event.preventDefault();
    const fields=new FormData(form);
    const input={expected_revision:record.revision,candidate_id:fields.get('candidate_id'),decision:fields.get('decision'),basis:fields.get('basis')};
    action(async()=>{await post(`${base}/drawings/${record.drawing_id}/line-review`,input);await reload();},event.submitter);
  };
}

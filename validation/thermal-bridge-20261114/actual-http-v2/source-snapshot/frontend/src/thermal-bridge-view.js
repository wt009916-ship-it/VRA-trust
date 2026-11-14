import {escape as esc, number as num} from './api.js';

export const statusText={calculated:'数值计算完成',needs_refinement:'需要细化网格 · 仅供诊断',incomplete:'输入待补全',stale:'来源或版本已变更'};
export const sideText={left:'左边',right:'右边',bottom:'下边',top:'上边'};
export function nullableNumber(value){
  if(value===null || value===undefined || String(value).trim()==='')return null;
  if(typeof value==='boolean')throw new Error('布尔值不是工程数值');
  const result=Number(value);
  if(!Number.isFinite(result))throw new Error('数值必须有限；未知值请留空');
  return result;
}
export function heatColor(value,low,high){
  const fraction=high===low ? .5 : Math.max(0,Math.min(1,(value-low)/(high-low)));
  return `hsl(${240-240*fraction} 65% 46%)`;
}
export function fieldBounds(result){
  if(!Array.isArray(result?.temperature_c))return null;
  let low=Infinity,high=-Infinity;
  for(const row of result.temperature_c)for(const value of row){low=Math.min(low,value);high=Math.max(high,value);}
  return Number.isFinite(low)&&Number.isFinite(high)?{low,high}:null;
}
export function geometryMarkup(input){
  const w=nullableNumber(input.width),h=nullableNumber(input.height);
  if(!(w>0&&h>0))return '<p>填写截面尺寸后显示分区草图。</p>';
  const scale=Math.min(720/w,360/h),width=w*scale,height=h*scale;
  const rects=(input.regions||[]).slice(0,32).map((r,i)=>{
    const [x0,x1,y0,y1]=['x0','x1','y0','y1'].map(k=>nullableNumber(r[k]));
    if([x0,x1,y0,y1].some(x=>x===null)||!(0<=x0&&x0<x1&&x1<=w&&0<=y0&&y0<y1&&y1<=h))return '';
    return `<rect x="${x0*scale}" y="${(h-y1)*scale}" width="${(x1-x0)*scale}" height="${(y1-y0)*scale}" fill="hsl(${i*67%360} 35% 72%)" stroke="currentColor" stroke-width=".7"><title>${esc(r.name)} · ${esc(r.conductivity??'未知')} ${esc(r.conductivity_unit)}</title></rect>`;
  }).join('');
  return `<svg viewBox="0 0 ${width} ${height}" width="${width}" height="${height}" role="img" aria-label="材料分区草图，原点在左下角">${rects}</svg><p>原点为左下角，x 向右、y 向上。范围 ${num(w)} × ${num(h)} ${esc(input.length_unit)}。草图不代替重叠及缺口检查。</p>`;
}
export function resultMarkup(record,base){
  const r=record.status==='stale'?null:record.result,path='/api'+base+'/'+encodeURIComponent(record.thermalbridge_id);
  let detail='<p>当前结果不可用。请复核来源与输入后新建计算。</p>';
  if(r?.status==='incomplete')detail='<p>尚缺：'+r.missing.map(esc).join('、')+'。未计算温度或热流。</p>';
  else if(r?.temperature_c){
    const bounds=fieldBounds(r),mesh=r.mesh_check;
    detail=`<p class="tb-notice">${r.status==='needs_refinement'?'网格检查未通过，以下数值与图仅用于检查模型。':'两级网格检查通过；仍不是连续体误差保证或标准认证。'}</p>
      <figure><canvas data-temperature-field role="img" aria-label="二维截面单元温度场，原点左下角；精确数值见温度 CSV"></canvas><figcaption>单元中心温度：${num(bounds.low,3)} ～ ${num(bounds.high,3)} °C。蓝色较冷，红色较暖；颜色范围仅对应本次记录。<br>保持截面长宽比例；界面温度取值见指定位置表。</figcaption></figure>
      <table><caption>边界热流 · W/m 延伸长度（正值进入截面）</caption><thead><tr><th>边界</th><th>热流</th></tr></thead><tbody>${Object.entries(r.boundary_heat_into_domain_w_per_m).map(([s,q])=>`<tr><td>${sideText[s]}</td><td>${num(q,6)}</td></tr>`).join('')}</tbody></table>
      <p>热平衡残差 ${num(r.energy_balance_w_per_m,10)} W/m。不是全楼功率或全年能耗。</p>
      <p>网格：${mesh.coarse_cells} → ${mesh.fine_cells} 单元；温度最大差 ${num(mesh.max_temperature_difference_k,6)} K（限 0.1 K）；边界热流相对差 ${num(mesh.max_edge_heat_difference_relative*100,4)}%（限 1%）。</p>
      ${mesh.fixed_temperature_corner_discontinuities.length?'<p>相邻固定温度边在角点不连续：'+mesh.fixed_temperature_corner_discontinuities.map(esc).join('、')+'；总热流可能奇异，不能宣称网格收敛。</p>':''}
      ${r.probes.length?'<table><caption>指定位置温度 · 网格重构近似</caption><thead><tr><th>位置</th><th>x / m</th><th>y / m</th><th>温度 / °C</th></tr></thead><tbody>'+r.probes.map(p=>`<tr><td>${esc(p.name)}</td><td>${num(p.x,6)}</td><td>${num(p.y,6)}</td><td>${num(p.temperature_c,4)}</td></tr>`).join('')+'</tbody></table>':''}
      <ul>${r.limitations.map(x=>'<li>'+esc(x)+'</li>').join('')}</ul><a href="${path}/temperatures.csv">下载单元温度 CSV</a>`;
  }
  return `<h3>${esc(record.input.name)} · ${esc(statusText[record.status]||record.status)}</h3><p>${esc(record.source_notice)}</p>${detail}<p><a href="${path}" target="_blank" rel="noopener">完整 JSON</a> · <a href="${path}/report.html" target="_blank" rel="noopener">打印报告</a></p><details><summary>本次输入与来源</summary><pre>${esc(JSON.stringify({input:record.input,evidence:record.evidence_snapshot,calculator_version:record.calculator_version,stale_details:record.stale_details},null,2))}</pre></details>`;
}
export function drawTemperature(canvas,result){
  const bounds=fieldBounds(result);if(!canvas||!bounds)return;
  const xe=result.x_edges_m,ye=result.y_edges_m,w=xe.at(-1),h=ye.at(-1),scale=Math.min(800/w,400/h);
  canvas.width=Math.max(1,Math.round(w*scale));canvas.height=Math.max(1,Math.round(h*scale));
  const ctx=canvas.getContext('2d');if(!ctx)return;
  result.temperature_c.forEach((row,j)=>row.forEach((t,i)=>{
    ctx.fillStyle=heatColor(t,bounds.low,bounds.high);
    const left=xe[i]/w*canvas.width,right=xe[i+1]/w*canvas.width,top=(h-ye[j+1])/h*canvas.height,bottom=(h-ye[j])/h*canvas.height;
    ctx.fillRect(left,top,right-left+.2,bottom-top+.2);
  }));
}

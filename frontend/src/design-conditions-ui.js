import {request, post, escape as esc} from './api.js';

const statuses={matching_declared_fields:'声明字段一致',differences_found:'存在参数差异',
  incomplete_model_coverage:'尚未覆盖全部模型设计日',unverified_dependencies:'日程或其他定容工况待核验',
  different_fields:'字段不同',unverified_schedule_dependencies:'日程依赖待核验'};
const fieldNames={month:'月份',day:'日期',day_type:'日类型',maximum_dry_bulb:'最高干球温度',
  daily_dry_bulb_range:'干球日温差',dry_bulb_modifier_type:'干球变化模式',dry_bulb_day_schedule:'干球日程',
  humidity_type:'湿度定义',wetbulb_or_dewpoint:'对应湿球/露点',humidity_day_schedule:'湿度日程',
  humidity_ratio:'含湿量',enthalpy:'焓',daily_wet_bulb_range:'湿球日温差',barometric_pressure:'气压',
  wind_speed:'风速',wind_direction:'风向',rain:'降雨',snow:'积雪',daylight_saving:'夏令时',
  solar_model:'太阳模型',beam_day_schedule:'直射日程',diffuse_day_schedule:'散射日程',
  beam_optical_depth:'直射光学厚度',diffuse_optical_depth:'散射光学厚度',sky_clearness:'天空晴朗度'};
const reviewNames={pending:'待复核',confirmed:'人工已复核',rejected:'已撤回'};
const textInput=(name,label,type='text',extra='')=>'<label>'+label+'<input name="'+name+'" type="'+type+'" required '+extra+'></label>';

export function designCheckMarkup(record,base) {
  if(!record || record.status!=='current' || !record.result) return '<p role="status">当前核对结果不可用，请重新检查来源和模型版本。</p>';
  const result=record.result;
  return '<article><h3>'+esc(statuses[result.status]||result.status)+'</h3><p>仅核对声明字段，不是来源权威或工程适用性认证。</p>'+
    '<p>来源版本：'+esc(record.source_snapshot.input.edition)+' · 模型证据修订 '+esc(record.model_snapshot.evidence.revision)+'</p>'+
    (result.unmapped_model_days.length?'<p>未映射：'+esc(result.unmapped_model_days.join('、'))+'</p>':'')+
    (result.unverified_sizing_period_types.length?'<p>其他定容工况待核验：'+esc(result.unverified_sizing_period_types.join('、'))+'</p>':'')+
    '<p>坐标字段：'+(result.site_fields.every(f=>f.equal)?'一致，仍不代表适用性通过':'存在差异，请查看完整报告')+'</p>'+
    result.rows.map(row=>'<details><summary>'+esc(row.model_day)+' → '+esc(row.source_day)+' · '+esc(statuses[row.status]||row.status)+'</summary>'+
      '<p>模型第 '+esc(row.model_locator.line)+' 行；来源第 '+esc(row.source_locator.line)+' 行。</p>'+
      (row.unverified_dependencies.length?'<p>日程引用尚未验证：'+esc(row.unverified_dependencies.join('、'))+'</p>':'')+
      '<div class="hourly-table"><table><thead><tr><th>字段</th><th>单位</th><th>模型</th><th>来源</th><th>核对</th></tr></thead><tbody>'+
      row.fields.map(f=>'<tr><td>'+esc(fieldNames[f.field]||f.field)+'</td><td>'+esc(f.unit||'—')+'</td><td>'+esc(f.model||'未填写')+'</td><td>'+esc(f.source||'未填写')+'</td><td>'+(f.equal?'一致':'不同')+'</td></tr>').join('')+'</tbody></table></div></details>').join('')+
    '<p><a target="_blank" rel="noopener" href="/api'+esc(base)+'/design-checks/'+esc(record.designcheck_id)+'">完整 JSON</a> · '+
    '<a target="_blank" rel="noopener" href="/api'+esc(base)+'/design-checks/'+esc(record.designcheck_id)+'/report.html">来源核对报告 / 打印</a></p></article>';
}

export async function designConditionsWorkspace(state,host,action) {
  const base='/projects/'+state.project.project_id;
  let sources=[],model=null,source=null,current=null,sequence=0,cachedUpload=null,rendered=null;
  host.innerHTML='<p>将模型设计日与保留的 DDY 文件逐字段核对。登记的发布方和版本属于来源声明，人工复核也不等于专业认证。</p>'+
    '<details><summary>登记设计气象来源</summary><form data-source-form class="field-grid">'+
      '<label>DDY 原件<input name="ddy" type="file" accept=".ddy" required></label>'+
      '<label>原件编码<select name="encoding"><option value="utf-8-sig">UTF-8</option><option value="cp1252">Windows-1252（旧版官方天气包）</option></select></label>'+
      '<p>当前核对契约为 IDF 9.0 字段布局，不自动转换文件。</p>'+
      textInput('title','资料名称','text','maxlength="200"')+textInput('publisher','声明发布方','text','maxlength="200"')+
      textInput('edition','资料版本 / 年代','text','maxlength="100"')+textInput('source_url','来源网址','url')+
      textInput('acquired_on','取得日期','date')+textInput('permission','授权使用说明','text','minlength="5" maxlength="1000"')+
      textInput('scope','适用范围与限制','text','minlength="5" maxlength="2000"')+
      '<button class="primary">保留原件并登记</button><p data-upload-status role="status"></p></form></details>'+
    '<div class="field-grid"><label>设计气象来源<select data-source-choice></select></label><label>已确认模型<select data-model-choice></select></label></div>'+
    '<p data-source-note></p><details><summary>人工复核 / 撤回来源</summary><label>复核依据<textarea data-review-basis minlength="10" maxlength="2000"></textarea></label>'+
    '<button data-review="confirmed">确认已检查原件及声明</button><button data-review="pending">撤回确认</button></details>'+
    '<p><button data-prepare>选择设计日对应关系</button><button data-refresh>刷新当前版本</button></p>'+
    '<form data-mapping-form><div data-mapping></div><button class="primary" data-check disabled>核对并保存记录</button></form>'+
    '<div data-result aria-live="polite"></div><details><summary>历史核对记录</summary><div data-history></div></details>';
  const q=s=>host.querySelector(s);
  function clear() {sequence++;model=null;source=null;current=null;rendered=null;q('[data-mapping]').innerHTML='';q('[data-check]').disabled=true;q('[data-result]').innerHTML='';}
  async function show(id) {
    const token=++sequence;current=id;
    q('[data-result]').innerHTML='<p role="status">正在重新核验来源…</p>';
    try {
      const record=await request(base+'/design-checks/'+id);
      if(!host.isConnected || token!==sequence) return;
      rendered=JSON.stringify(record);q('[data-result]').innerHTML=designCheckMarkup(record,base);
    } catch(error) {
      if(host.isConnected && token===sequence) {current=null;q('[data-result]').textContent='当前核对结果不可用：'+error.message;}
      throw error;
    }
  }
  async function refresh() {
    clear();const token=sequence;
    const [s,e,h]=await Promise.all([request(base+'/design-sources'),request(base+'/evidence'),request(base+'/design-checks')]);
    if(!host.isConnected||token!==sequence)return;
    sources=s;
    q('[data-source-choice]').innerHTML='<option value="">请选择来源版本</option>'+s.map(r=>'<option value="'+r.designsource_id+'">'+esc(r.input.title+' · '+r.input.edition+' · '+reviewNames[r.review.state]+(r.source_status==='stale'?' · 来源失效':''))+'</option>').join('');
    q('[data-model-choice]').innerHTML='<option value="">请选择模型证据</option>'+e.filter(v=>v.type==='idf'&&v.review_state==='confirmed').map(v=>'<option value="'+v.evidence_id+'">'+esc(v.name+' · '+v.scheme_id+' · 修订 '+v.revision)+'</option>').join('');
    q('[data-source-note]').textContent='请选择来源并核对资料版本。';
    q('[data-history]').innerHTML=h.map(r=>'<p><button data-open-check="'+r.designcheck_id+'">'+esc(r.created_at)+' · '+(r.status==='stale'?'已失效':'查看当前核对')+'</button></p>').join('')||'<p>还没有核对记录。</p>';
    q('[data-history]').querySelectorAll('[data-open-check]').forEach(b=>b.onclick=()=>action(()=>show(b.dataset.openCheck),b));
  }
  q('[data-source-choice]').onchange=()=>{clear();const selected=sources.find(s=>s.designsource_id===q('[data-source-choice]').value);q('[data-source-note]').textContent=selected?selected.input.publisher+' / '+selected.input.edition+' · '+reviewNames[selected.review.state]+' · 原件 '+selected.file_snapshot.hash:'请选择来源版本';};
  q('[data-model-choice]').onchange=clear;
  q('[data-mapping]').onchange=()=>{sequence++;current=null;rendered=null;q('[data-result]').innerHTML='';};
  q('[data-source-form]').onsubmit=e=>{e.preventDefault();action(async()=>{
    const form=e.currentTarget;const file=form.elements.ddy.files[0];
    if(!file || file.size>2*1024*1024)throw Error('请选择不超过 2 MiB 的 DDY 原件');
    const fields=Object.fromEntries(new FormData(form));delete fields.ddy;
    if(cachedUpload?.file!==file) {
      const data=new FormData();data.append('file',file);
      const f=await request(base+'/files',{method:'POST',body:data});
      if(form.elements.ddy.files[0]!==file)throw Error('文件选择已改变；刚才的原件已保留，请重新提交当前选择');
      cachedUpload={file,id:f.file_id};
    }
    fields.file_id=cachedUpload.id;
    const saved=await post(base+'/design-sources',fields);
    if(!host.isConnected)return;
    q('[data-upload-status]').textContent='已保留原件并解析 '+saved.catalog.days.length+' 个设计日，需人工复核后使用。';
    await refresh();
  },e.submitter);};
  q('[data-refresh]').onclick=e=>action(refresh,e.currentTarget);
  host.querySelectorAll('[data-review]').forEach(button=>button.onclick=()=>action(async()=>{
    const selected=sources.find(s=>s.designsource_id===q('[data-source-choice]').value);
    const basis=q('[data-review-basis]').value.trim();
    if(!selected || basis.length<10)throw Error('请选择来源并填写至少 10 字的复核依据');
    clear();
    await post(base+'/design-sources/'+selected.designsource_id+'/review',{expected_revision:selected.revision,state:button.dataset.review,basis});
    await refresh();
  },button));
  q('[data-prepare]').onclick=e=>action(async()=>{
    clear();const token=sequence;
    const sid=q('[data-source-choice]').value,eid=q('[data-model-choice]').value;
    if(!sid||!eid)throw Error('请选择已复核来源及模型');
    const [s,m]=await Promise.all([request(base+'/design-sources/'+sid),request(base+'/design-models/'+eid)]);
    if(!host.isConnected||token!==sequence)return;
    if(s.source_status!=='intact'||s.review.state!=='confirmed')throw Error('请先复核有效的来源资料');
    source=s;model=m;
    q('[data-mapping]').innerHTML=m.catalog.days.map((d,i)=>'<label>'+esc(d.name)+'<select data-map="'+i+'" required><option value="">明确选择来源设计日</option>'+s.catalog.days.map((v,j)=>'<option value="'+j+'">'+esc(v.name)+'</option>').join('')+'</select></label>').join('');
    q('[data-check]').disabled=false;
  },e.currentTarget);
  q('[data-mapping-form]').onsubmit=e=>{e.preventDefault();action(async()=>{
    if(!source||!model)throw Error('请重新准备来源与模型映射');
    const pairs=[...q('[data-mapping]').querySelectorAll('[data-map]')].map(select=>{
      if(!/^\d+$/.test(select.value))throw Error('请逐项选择来源设计日');
      return {model_day:model.catalog.days[Number(select.dataset.map)].name,source_day:source.catalog.days[Number(select.value)].name};
    });
    const body={source_id:source.designsource_id,source_revision:source.revision,model_evidence_id:model.evidence.evidence_id,model_revision:model.evidence.revision,pairs};
    const token=++sequence;current=null;q('[data-result]').innerHTML='';
    const saved=await post(base+'/design-checks',body);
    if(!host.isConnected||token!==sequence)return;
    await show(saved.designcheck_id);
  },e.submitter);};
  await refresh();
  const timer=setInterval(()=>{
    if(!host.isConnected){clearInterval(timer);return;}
    if(!current||host.closest('.work-view')?.hidden)return;
    const id=current,token=sequence;
    request(base+'/design-checks/'+id).then(record=>{
      if(host.isConnected&&token===sequence&&id===current&&JSON.stringify(record)!==rendered){rendered=JSON.stringify(record);q('[data-result]').innerHTML=designCheckMarkup(record,base);}
    }).catch(error=>{if(host.isConnected&&token===sequence){current=null;q('[data-result]').textContent='当前结果无法重新核验：'+error.message;}});
  },8000);
}

import {request,post,escape as esc,number as num} from './api.js';

export function profileMarkup(record){
  const result=record?.status==='extracted'?record.result:null;
  if(!result?.section_properties)return `<p role="status">${esc(record?.status==='unsupported'?'该构件不能作为本工具的等截面梁输入':'来源已失效或尚未核验')}。${esc(record?.result?.issues?.join('；')||'')} 截面值不展示。</p>`;
  const s=result.section_properties;
  return `<p>实体 #${esc(result.product_id)} · ${esc(result.name)} · ${esc(result.source.profile_type)}；模型几何，非实测或安全认可。</p><dl><dt>截面积</dt><dd>${num(s.area_m2,10)} m²</dd><dt>局部轴 Ix / Iy</dt><dd>${num(s.ix_m4,12)} / ${num(s.iy_m4,12)} m⁴</dd><dt>实体挤出长度（不是跨度）</dt><dd>${num(result.extrusion_length_m,6)} m</dd></dl><details><summary>截面尺寸、坐标轴与原件来源</summary><pre>${esc(JSON.stringify({dimensions:s.dimensions_m,axes_world:result.axes_world,source:result.source,file_hash:record.file_snapshot.hash},null,2))}</pre></details>`;
}

export function reviewedProfile(record,axis,confirmed,basis){
  if(record?.status!=='extracted'||!record.result?.section_profile)throw new Error('IFC截面尚未通过当前来源核验，请重新读取。');
  if(!['x','y'].includes(axis)||confirmed!==true||basis.trim().length<20)throw new Error('请选择弯曲轴，并明确确认几何适用性及至少20字的复核依据。');
  return {profile_id:record.beamprofile_id,expected_profile_hash:record.hash,bending_axis:axis,geometry_reviewed:true,review_basis:basis};
}

export function bindIfcBeamProfile(host,base,action,onChange){
  host.innerHTML=`<details><summary>从IFC构件提取截面并复核</summary><p>先在CAD/BIM页上传并读取模型。此处提取明确等截面轮廓，跨度、支承、材料模量和荷载需另行提供。</p><button type="button" data-ifc-load>加载IFC读取记录</button><label>原件读取记录<select data-ifc-cad><option value="">请选择</option></select></label><label>选定梁构件<select data-ifc-product><option value="">先选择读取记录</option></select></label><button type="button" data-ifc-extract disabled>提取新截面记录</button><button type="button" data-ifc-clear>切回手工截面</button><div data-ifc-status aria-live="polite"></div><div data-ifc-values></div><label>弯曲轴（截面局部主轴）<select data-ifc-axis><option value="">请明确选择</option><option value="x">绕X轴，沿Y方向弯曲</option><option value="y">绕Y轴，沿X方向弯曲</option></select></label><label>几何和受力模型复核依据<textarea data-ifc-basis minlength="20"></textarea></label><label><input type="checkbox" data-ifc-confirm>已核对截面、局部轴、等截面适用性；跨度及力学参数另有依据</label></details>`;
  const cad=host.querySelector('[data-ifc-cad]'),product=host.querySelector('[data-ifc-product]'),extract=host.querySelector('[data-ifc-extract]');
  const status=host.querySelector('[data-ifc-status]'),values=host.querySelector('[data-ifc-values]'),axis=host.querySelector('[data-ifc-axis]'),basis=host.querySelector('[data-ifc-basis]'),confirm=host.querySelector('[data-ifc-confirm]');
  let chosen=null,current=null,serial=0,cadSerial=0,timer=null;
  async function read(path){const abort=new AbortController(),timeout=setTimeout(()=>abort.abort(),12000);try{return await request(path,{signal:abort.signal});}finally{clearTimeout(timeout);}}
  function show(record){current=record;values.innerHTML=profileMarkup(record);onChange(record,true);}
  function clear(){serial++;chosen=null;current=null;confirm.checked=false;axis.value='';basis.value='';values.innerHTML='';status.textContent='使用手工截面；请重新输入几何来源。';clearTimeout(timer);onChange(null,false);}
  async function refresh(){
    if(!chosen||!host.isConnected)return;
    const token=++serial,id=chosen.beamprofile_id;
    try{const r=await read(base+'/ifc-beam-profiles/'+id);if(token!==serial||!host.isConnected)return;
      if(chosen.hash&&r.hash!==chosen.hash)throw new Error('截面记录已变化，须重新选择复核。');
      show(r);status.textContent=r.status==='extracted'?'当前来源已核验；请完成弯曲轴和人工复核。':'当前来源不可用于计算。';
    }catch(error){if(token!==serial||!host.isConnected)return;show(null);confirm.checked=false;status.textContent='截面来源核验失败：'+error.message;}
  }
  function schedule(){clearTimeout(timer);timer=setTimeout(async()=>{if(!host.isConnected||!chosen)return;if(!document.hidden)await refresh();schedule();},5000);timer.unref?.();}
  async function restore(snapshot){serial++;chosen={beamprofile_id:snapshot.beamprofile_id,hash:snapshot.hash};current=null;confirm.checked=false;axis.value=snapshot.bending_axis||'';basis.value=snapshot.review_basis||'';values.innerHTML='<p>正在重新核验来源…</p>';onChange(null,true);await refresh();schedule();}
  host.querySelector('[data-ifc-clear]').onclick=clear;
  host.querySelector('[data-ifc-load]').onclick=()=>action(async()=>{const response=await read(base+'/ifc-beam-profile-inputs');if(!host.isConnected)return;cad.innerHTML='<option value="">请选择</option>'+response.items.map(r=>`<option value="${esc(r.cad_id)}">${esc(r.name)} · ${esc(r.created_at)}</option>`).join('');status.textContent=response.truncated?'仅列最近100条读取记录。':'选择后会核验该记录当前状态。';});
  cad.onchange=()=>action(async()=>{const token=++cadSerial;product.innerHTML='<option value="">正在核验…</option>';extract.disabled=true;if(!cad.value)return;const r=await read(base+'/cad-inspections/'+cad.value);if(token!==cadSerial||!host.isConnected)return;if(r.status!=='parsed'||r.result?.format!=='IFC')throw new Error('IFC读取记录已失效，请重新读取。');const beams=r.result.objects.filter(x=>['IfcBeam','IfcBeamStandardCase'].includes(x.type));product.innerHTML='<option value="">请选择构件</option>'+beams.slice(0,500).map(x=>`<option value="${x.id}">#${x.id} ${esc(x.name)} · ${esc(x.type)}</option>`).join('');status.textContent=beams.length>500?'选择器仅显示前500个梁构件。':`已读取${beams.length}个梁构件；尚未证明截面可用于分析。`;});
  product.onchange=()=>{extract.disabled=!product.value;};
  extract.onclick=()=>action(async()=>{const cid=cad.value,id=Number(product.value);const r=await post(base+'/ifc-beam-profiles',{cad_id:cid,product_id:id});if(!host.isConnected||cid!==cad.value||id!==Number(product.value))return;await restore({beamprofile_id:r.beamprofile_id,hash:r.hash});},extract);
  return {clear,restore,capture:()=>chosen?{...chosen,bending_axis:axis.value,review_basis:basis.value}:null,
    review:async()=>{if(!chosen)return null;const selection=chosen;await refresh();if(chosen!==selection)throw new Error('提交期间截面选择已变化，请重新复核。');return reviewedProfile(current,axis.value,confirm.checked,basis.value);}};
}

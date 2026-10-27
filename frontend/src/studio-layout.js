import { storeyKey } from './solid-preview.js';
import { escape as esc, number as num } from './api.js';

// The existing model controls are moved, not cloned: revisions, required inputs,
// source review and API handlers keep the same state and identity.
export function mountModelStudio(host, { projectId, selectRoom, fit, area, filterStorey=()=>{}, batchUse=()=>{} }) {
  const workbench=host.querySelector('.model-workbench');
  const inputs=workbench.querySelector('.model-inputs'), main=workbench.querySelector('.model-main');
  const importPanel=inputs.querySelector('details'), roomPanel=inputs.querySelector('section');
  const preview=main.querySelector('.model-preview');
  const review=main.querySelector('section:not(.model-preview)');
  const parameters=[...main.children].filter(el=>el!==preview&&el!==review);
  host.classList.add('spatial-studio');
  const heading=host.querySelector('.view-heading');heading.classList.add('studio-heading');
  heading.querySelector('h1').textContent='建筑模型';
  heading.querySelector('p').textContent='查看空间、核对参数，再发布计算输入。';
  const api=host.querySelector('#model-api');
  heading.insertAdjacentHTML('beforeend','<div class="studio-heading-actions"><button data-studio-import>导入资料</button><button class="primary" data-studio-review>复核与发布</button></div>');
  const modal=document.createElement('dialog');modal.className='studio-import-dialog';
  modal.innerHTML='<header><div><small>项目资料</small><h2>导入图纸与模型</h2></div><button type="button" data-close aria-label="关闭导入窗口">×</button></header>';
  importPanel.open=true;modal.append(importPanel);host.append(modal);
  const fileInput=importPanel.querySelector('input[type=file]');
  const drop=fileInput.closest('label');drop.classList.add('studio-file-drop');
  drop.addEventListener('dragover',e=>{e.preventDefault();drop.classList.add('drag-over');});
  drop.addEventListener('dragleave',()=>drop.classList.remove('drag-over'));
  drop.addEventListener('drop',e=>{e.preventDefault();drop.classList.remove('drag-over');if(e.dataTransfer.files.length!==1){importPanel.querySelector('#import-progress').textContent='单次模型识别请选择一份文件；多文件项目可从项目中心批量导入。';return;}fileInput.files=e.dataTransfer.files;fileInput.dispatchEvent(new Event('change',{bubbles:true}));});
  drop.insertAdjacentHTML('afterbegin','<strong>拖入项目文件，或选择本地资料</strong><span>IFC · DXF · PDF · PNG / JPG</span>');
  modal.querySelector('[data-close]').onclick=()=>modal.close();
  const openImport=()=>{if(!modal.open)modal.showModal();};
  host.querySelector('[data-studio-import]').onclick=openImport;
  const resources=document.createElement('aside');resources.className='studio-resources';resources.setAttribute('aria-label','模型资源与空间');
  resources.innerHTML='<header class="studio-panel-title"><strong>模型资源</strong><div class="studio-resource-actions"><button data-import-small aria-label="导入模型资料">＋</button><button data-resources-close aria-label="关闭模型资源">×</button></div></header><div class="studio-source-list"></div><div class="studio-space-heading"><strong>空间</strong><span data-room-count>0</span></div><label class="studio-room-search"><span class="sr-only">搜索空间</span><input type="search" placeholder="搜索空间名称" aria-label="搜索空间"></label><label class="studio-room-search">显示楼层<select data-storey-filter aria-label="显示楼层"><option value="">全楼</option></select><small>仅筛选显示，不改变计算范围</small></label><div class="studio-room-list" aria-label="空间列表"></div><footer></footer>';
  resources.querySelector('[data-import-small]').onclick=openImport;
  resources.querySelector('[data-resources-close]').onclick=()=>workbench.classList.remove('show-resources');
  resources.querySelector('footer').append(api);
  const records=host.querySelector('#model-imports');
  const recordDialog=document.createElement('dialog');recordDialog.className='studio-record-dialog';
  recordDialog.innerHTML='<header><h2>识别与复核记录</h2><button type="button" aria-label="关闭识别记录">×</button></header>';
  recordDialog.append(records);recordDialog.querySelector('button').onclick=()=>recordDialog.close();host.append(recordDialog);
  if(!records.children.length)records.innerHTML='<p class="studio-empty">尚无识别任务。导入项目资料后，可在这里核对候选与原始文件。</p>';
  const recordButton=document.createElement('button');recordButton.textContent='识别与复核记录';recordButton.onclick=()=>recordDialog.showModal();resources.querySelector('footer').prepend(recordButton);
  const inspector=document.createElement('aside');inspector.className='studio-properties';inspector.setAttribute('aria-label','模型属性');
  inspector.innerHTML='<header class="studio-panel-title"><strong>属性与发布</strong><button data-inspector-close aria-label="关闭模型属性">×</button></header><nav class="studio-property-tabs" aria-label="模型属性分类"><button data-property="space" class="selected" aria-pressed="true">空间</button><button data-property="thermal" aria-pressed="false">热工</button><button data-property="review" aria-pressed="false">复核</button></nav><div class="studio-property-content"><div data-property-page="space"></div><div data-property-page="thermal" hidden></div><div data-property-page="review" hidden></div></div>';
  roomPanel.querySelector('h2').textContent='空间属性';
  inspector.querySelector('[data-property-page="space"]').append(roomPanel);
  parameters.forEach(panel=>inspector.querySelector('[data-property-page="thermal"]').append(panel));
  review.querySelector('h2').textContent='复核与发布';
  inspector.querySelector('[data-property-page="review"]').append(review);
  const gate=review.querySelector('#model-gate'),runs=review.querySelector('#model-runs'),status=review.querySelector('#model-status');
  const history=review.querySelector('#model-history').parentElement;
  const center=document.createElement('div');center.className='studio-center';
  const originalToolbar=preview.querySelector('.model-preview-top');
  const summary=originalToolbar.querySelector('#model-summary'),xray=originalToolbar.querySelector('label');
  originalToolbar.innerHTML='<div class="studio-view-buttons"><button data-preview="3d" aria-pressed="true">3D 模型</button><button data-preview="2d" aria-pressed="false">2D 平面</button></div><div class="studio-view-tools"><button data-resources-toggle>资源</button><button data-fit title="重置三维相机，查看完整模型">重置视角</button><button data-properties-toggle>属性</button></div>';
  originalToolbar.querySelector('.studio-view-tools').append(xray);
  const caption=preview.querySelector('p');caption.className='studio-canvas-caption';caption.prepend(summary);
  center.append(preview);
  center.insertAdjacentHTML('beforeend','<section class="studio-results"><nav aria-label="模型检查与运行"><button data-result="audit" class="selected" aria-pressed="true">校验与依据</button><button data-result="runs" aria-pressed="false">计算记录</button><button data-result="history" aria-pressed="false">版本与来源</button><button data-results-toggle aria-expanded="true" title="展开或收起底部检查面板">收起</button></nav><div class="studio-result-content"><div data-result-page="audit"></div><div data-result-page="runs" hidden></div><div data-result-page="history" hidden></div></div></section><footer class="studio-status"></footer>');
  center.querySelector('[data-result-page="audit"]').append(gate);
  center.querySelector('[data-result-page="runs"]').append(runs);
  center.querySelector('[data-result-page="history"]').append(history);history.open=true;
  center.querySelector('.studio-status').append(status);
  workbench.replaceChildren(resources,center,inspector);
  workbench.dataset.preview='3d';
  function property(page){
    inspector.querySelectorAll('[data-property]').forEach(b=>{b.classList.toggle('selected',b.dataset.property===page);b.setAttribute('aria-pressed',String(b.dataset.property===page));});
    inspector.querySelectorAll('[data-property-page]').forEach(p=>{p.hidden=p.dataset.propertyPage!==page;});
    workbench.classList.add('show-properties');
  }
  inspector.querySelectorAll('[data-property]').forEach(b=>b.onclick=()=>property(b.dataset.property));
  host.querySelector('[data-studio-review]').onclick=()=>property('review');
  inspector.querySelector('[data-inspector-close]').onclick=()=>workbench.classList.remove('show-properties');
  originalToolbar.querySelector('[data-resources-toggle]').onclick=()=>workbench.classList.toggle('show-resources');
  originalToolbar.querySelector('[data-properties-toggle]').onclick=()=>workbench.classList.toggle('show-properties');
  originalToolbar.querySelector('[data-fit]').onclick=fit;
  originalToolbar.querySelectorAll('[data-preview]').forEach(b=>b.onclick=()=>{
    workbench.dataset.preview=b.dataset.preview;
    originalToolbar.querySelectorAll('[data-preview]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));
  });
  const resultsToggle=center.querySelector('[data-results-toggle]');
  function resultsVisible(show){center.classList.toggle('results-collapsed',!show);resultsToggle.textContent=show?'收起':'展开';resultsToggle.setAttribute('aria-expanded',String(show));}
  resultsToggle.onclick=()=>resultsVisible(center.classList.contains('results-collapsed'));
  center.querySelectorAll('[data-result]').forEach(b=>b.onclick=()=>{
    resultsVisible(true);
    center.querySelectorAll('[data-result]').forEach(x=>{x.classList.toggle('selected',x===b);x.setAttribute('aria-pressed',String(x===b));});
    center.querySelectorAll('[data-result-page]').forEach(p=>{p.hidden=p.dataset.resultPage!==b.dataset.result;});
  });
  let snapshot={rooms:[],selected:0,sources:[],model:null};
  function tree(){
    const q=resources.querySelector('input').value.trim().toLocaleLowerCase(),floor=resources.querySelector('[data-storey-filter]').value;
    const list=resources.querySelector('.studio-room-list'),top=list.scrollTop;
    list.innerHTML=snapshot.rooms.map((r,index)=>({r,index})).filter(({r})=>(!floor||storeyKey(r)===floor)&&[r.name,r.building_name,r.storey_name].filter(Boolean).join(' ').toLocaleLowerCase().includes(q)).map(({r,index})=>`<button class="studio-room ${index===snapshot.selected?'selected':''}" data-room-index="${index}" aria-pressed="${index===snapshot.selected}"><span class="studio-space-icon">▧</span><span><strong>${esc(r.name)}</strong><small>${num(area(r))} m² · ${r.conditioned===null?'用途待确认':r.conditioned===false?'非空调空间':'空调空间'}</small></span></button>`).join('')||'<p class="studio-empty">没有匹配的空间。导入资料，或添加房间。</p>';
    list.scrollTop=top;
    list.querySelectorAll('[data-room-index]').forEach(b=>b.onclick=()=>{snapshot.selected=Number(b.dataset.roomIndex);selectRoom(snapshot.selected);tree();property('space');});
  }
  const batch=document.createElement('details');batch.className='model-card';batch.innerHTML='<summary>批量确认显示范围</summary><p class="subtle">使用当前楼层筛选；全楼时修改全部空间。不会根据楼层名称猜测用途。修改仅进入草稿，须填写依据并保存。</p>'+[['conditioned','是否设置空调和人员/设备负荷'],['include_floor_area','是否计入项目面积']].map(([key,label])=>`<label>${label}<select data-batch-use="${key}"><option value="keep">不修改</option><option value="true">是</option><option value="false">否</option><option value="unset">恢复待复核</option></select></label>`).join('')+'<label>确认依据 · 必填<textarea data-batch-note minlength="10" maxlength="1000" placeholder="说明适用楼层、实际用途或本次显式假设"></textarea></label><button type="button" data-apply-batch>应用到显示楼层 / 全楼</button>';
  resources.querySelector('.studio-room-list').before(batch);
  batch.querySelector('[data-apply-batch]').onclick=()=>{const value=key=>{const v=batch.querySelector('[data-batch-use="'+key+'"]').value;return v==='keep'?undefined:v==='unset'?null:v==='true';};batchUse({storey:resources.querySelector('[data-storey-filter]').value,conditioned:value('conditioned'),include_floor_area:value('include_floor_area'),note:batch.querySelector('[data-batch-note]').value});};
  resources.querySelector('input').oninput=tree;resources.querySelector('[data-storey-filter]').onchange=e=>{
    const floor=e.target.value;filterStorey(floor);
    if(floor&&snapshot.rooms[snapshot.selected]&&storeyKey(snapshot.rooms[snapshot.selected])!==floor){
      const index=snapshot.rooms.findIndex(room=>storeyKey(room)===floor);
      if(index>=0){snapshot.selected=index;selectRoom(index);}
    }
    tree();
  };
  return {
    update(value){
      const changed=value.selected!==snapshot.selected;
      const search=resources.querySelector('input');
      if(changed&&search.value&&!value.rooms[value.selected]?.name.toLocaleLowerCase().includes(search.value.toLocaleLowerCase()))search.value='';
      snapshot=value;const floorSelect=resources.querySelector('[data-storey-filter]'),previous=floorSelect.value;const levels=[...new Map(value.rooms.map(r=>[storeyKey(r),(r.building_name?r.building_name+' / ':'')+(r.storey_name||'标高 '+num(r.elevation_m)+' m')])).entries()];floorSelect.innerHTML='<option value="">全楼</option>'+levels.map(([id,label])=>`<option value="${esc(id)}">${esc(label)}</option>`).join('');if(levels.some(([id])=>id===previous))floorSelect.value=previous;filterStorey(floorSelect.value);resources.querySelector('[data-room-count]').textContent=value.rooms.length;tree();if(changed)resources.querySelector('.studio-room.selected')?.scrollIntoView({block:'nearest'});
      resources.querySelector('.studio-source-list').innerHTML=value.sources.length?value.sources.map(s=>`<a href="/api/projects/${projectId}/files/${esc(s.file_id)}" download><span>${esc(s.name.split('.').at(-1).toUpperCase())} · 来源文件</span><strong title="${esc(s.name)}">${esc(s.name)}</strong><small>来源文件 · SHA256 ${esc(s.hash.slice(0,10))}…</small></a>`).join(''):'<div class="studio-empty"><strong>尚无来源文件</strong><p>导入 IFC、DXF、PDF 或图像，保留原件并识别空间。</p><button data-empty-import>导入项目资料</button></div>';
      resources.querySelector('[data-empty-import]')?.addEventListener('click',openImport);
      originalToolbar.querySelector('[data-fit]').disabled=!value.canFit;
      heading.querySelector('.eyebrow').textContent=value.model?'模型 v'+value.model.revision+' · '+(value.model.status==='REVIEWED'?'空间已复核':'草稿'):'模型工作区 · 未保存';
    },
    imported(){modal.close();const latest=records.querySelector('details');if(latest)latest.open=true;if(!recordDialog.open)recordDialog.showModal();},
    adopted(){recordDialog.close();property('space');},
    showOverlay(){recordDialog.close();openImport();},
  };
}

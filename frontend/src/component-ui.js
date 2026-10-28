import {request,post,escape as esc,number as num} from './api.js';

const labels={structure:'墙板、柱梁与屋面',doors_windows:'门、窗与洞口',stairs:'楼梯、坡道与栏杆',services:'空调、管线与机电',furniture:'家具与室内陈设'};
export const componentLabels=labels;

export function componentSummary(record){
  return `<div class="component-metrics">${Object.entries(labels).map(([key,label])=>`<div><span>${label}</span><strong>${record.category_counts[key]||0}</strong></div>`).join('')}</div><details class="component-basis"><summary>来源覆盖：范围内 ${record.in_scope_count} · 缺表示 ${record.status_counts.NO_REPRESENTATION||0} · 几何失败 ${record.status_counts.GEOMETRY_FAILED||0}</summary><p>可见几何 ${record.status_counts.SOURCE_MESH||0}，三角面 ${num(record.triangles,0)}。</p><p class="subtle">此视图读取实际IFC实体，门洞保留原生扣减。家具只显示原件中已有对象；缺失的机电/家具不会自动添加。构件几何、厂家性能及热模型映射分别核对。</p></details>`;
}

export async function componentWorkspace(state,host,action,notice){
  const pid=state.project.project_id,base='/projects/'+pid;
  const instance={};host.componentInstance=instance;
  let generation=0,dispose=()=>{},current=null;
  const [initialRecords,sources]=await Promise.all([request(base+'/components'),request(base+'/components/sources')]);
  let records=initialRecords;
  if(!host.isConnected||state.project?.project_id!==pid||host.componentInstance!==instance)return;
  host.innerHTML=`<div class="view-heading"><div><span class="eyebrow">BUILDING COMPONENTS</span><h1>工程构件与室内</h1><p>从原件查看墙、门窗、楼梯、空调及家具，保留源标识与未覆盖项。</p></div></div><details class="model-card"><summary>提取授权IFC原件中的构件</summary><label>已上传IFC<select data-component-source>${sources.map(f=>`<option value="${esc(f.file_id)}">${esc(f.name)}</option>`).join('')}</select></label><label>或上传IFC<input data-component-file type="file" accept=".ifc"></label><p>不改变源坐标方向；下列XYZ仅作平移，应与建模工作区使用相同原点。</p><div class="form-grid">${['X','Y','Z'].map((axis,index)=>`<label>${axis}源原点 m<input data-component-origin="${index}" type="number" step="any" value="0"></label>`).join('')}</div><button data-component-storeys>读取源楼层与建议原点</button><div data-component-storey-select></div><button class="primary" data-component-build>提取真实构件几何</button><p data-component-progress role="status"></p></details><div class="component-workspace"><section class="component-main"><div class="component-toolbar"><label>已提取版本<select data-component-record></select></label><label>楼层<select data-component-floor><option value="">显示全楼</option></select></label><label>类别<select data-component-category><option value="">全部构件</option>${Object.entries(labels).map(([key,label])=>`<option value="${key}">${label}</option>`).join('')}</select></label><label>源名称 / GlobalId<input data-component-search type="search"></label><button data-component-load>加载此范围</button></div><div data-component-summary></div><p data-component-count role="status"></p><div class="component-canvas" data-component-canvas aria-label="实际IFC工程与室内构件三维"></div></section><aside class="model-card component-inspector" data-component-inspector><h2>选择一个构件</h2><p>点击实际实体查看IFC标识、楼层和原件属性。</p></aside></div>`;
  const active=()=>host.isConnected&&state.project?.project_id===pid&&host.componentInstance===instance;
  function paintRecords(){host.querySelector('[data-component-record]').innerHTML=records.map(r=>`<option value="${esc(r.component_id)}">${esc(r.name)} · ${esc(new Date(r.created_at).toLocaleString('zh-CN'))}</option>`).join('');}
  const setRecord=()=>{
    current=records.find(r=>r.component_id===host.querySelector('[data-component-record]').value);
    if(!current){host.querySelector('[data-component-canvas]').innerHTML='<p class="empty">选择已上传IFC，提取原件构件。没有来源时不生成示例家具。</p>';return;}
    host.querySelector('[data-component-summary]').innerHTML=componentSummary(current);
    host.querySelector('[data-component-floor]').innerHTML='<option value="">显示全楼</option>'+current.inventory.storeys.filter(s=>!current.selected_storey_ids.length||current.selected_storey_ids.includes(s.id)).map(s=>`<option value="${esc(s.id)}">${esc(s.name)} · ${num(s.elevation_m)} m</option>`).join('');
  };
  async function load(){
    if(!current)return;
    const token=++generation,asset=current.component_id,items=[];
    const params=new URLSearchParams({storey_id:host.querySelector('[data-component-floor]').value,category:host.querySelector('[data-component-category]').value,limit:'300'});
    host.querySelector('[data-component-count]').textContent='正在核对来源并读取实际几何…';
    for(let offset=0;;){
      params.set('offset',String(offset));const page=await request(base+'/components/'+asset+'/geometry?'+params);
      if(token!==generation||!active())return;
      items.push(...page.components);offset+=page.components.length;
      if(!page.remaining)break;
      if(!page.components.length)throw Error('构件分页未前进，停止加载');
    }
    const query=host.querySelector('[data-component-search]').value.trim().toLocaleLowerCase();
    const filtered=items.filter(r=>!query||[r.name,r.source_id,r.ifc_type].join(' ').toLocaleLowerCase().includes(query));
    dispose();host.querySelector('[data-component-count]').textContent=`当前范围 ${filtered.length} / ${items.length} 个构件 · 可见实体 ${filtered.filter(r=>r.status==='SOURCE_MESH').length}。范围筛选不删除原始构件。`;
    dispose=await sourceScene(host,filtered,r=>{
      host.querySelector('[data-component-inspector]').innerHTML=`<h2>${esc(r.name)}</h2><dl class="metadata"><dt>IFC类型</dt><dd>${esc(r.ifc_type)}</dd><dt>GlobalId</dt><dd><code>${esc(r.source_id)}</code></dd><dt>楼层</dt><dd>${esc(r.storey_name||'未分配')}</dd><dt>几何</dt><dd>${esc(r.status)}</dd><dt>热模型映射</dt><dd>尚未绑定，不从外观推断设备性能</dd></dl><details open><summary>原件属性 · 原名称/值与单位须核对</summary><pre>${esc(JSON.stringify(r.source_properties||{},null,2))}</pre></details>`;
    },()=>token===generation&&active());
  }
  paintRecords();setRecord();
  host.querySelector('[data-component-record]').onchange=()=>{setRecord();action(load);};
  host.querySelector('[data-component-load]').onclick=e=>action(load,e.currentTarget);
  host.querySelector('[data-component-storeys]').onclick=e=>action(async()=>{
    const fid=host.querySelector('[data-component-source]').value;if(!fid)throw Error('先选择或上传IFC');
    const data=await request(base+'/files/'+fid+'/ifc-storeys');
    host.querySelector('[data-component-storey-select]').innerHTML=`<p>建议源原点 ${esc(JSON.stringify(data.suggested_origin_m))}；请按建模工作区依据填写。未勾选楼层表示整楼。</p>`+data.storeys.map(s=>`<label class="check-option"><input data-component-build-floor type="checkbox" value="${esc(s.id)}">${esc(s.name)}</label>`).join('');
  },e.currentTarget);
  host.querySelector('[data-component-build]').onclick=e=>action(async()=>{
    let fid=host.querySelector('[data-component-source]').value;const file=host.querySelector('[data-component-file]').files[0];
    if(file){const data=new FormData();data.set('file',file);const saved=await request(base+'/files',{method:'POST',body:data});fid=saved.file_id;}
    if(!fid)throw Error('请先选择授权IFC原件');
    host.querySelector('[data-component-progress]').textContent='正在读取源实体与门洞，保留家具和机电缺项…';
    const origin=[...host.querySelectorAll('[data-component-origin]')].map(el=>{if(el.value==='')throw Error('原点三个坐标须明确填写');return Number(el.value);});
    const record=await post(base+'/components',{file_id:fid,origin_m:origin,storey_ids:[...host.querySelectorAll('[data-component-build-floor]:checked')].map(el=>el.value)});
    if(!active())return;records=[record,...records];paintRecords();setRecord();await load();notice('源构件已保留为独立版本；不改变热模型或原件。');host.querySelector('[data-component-progress]').textContent='已完成，缺表示与失败项仍计入清单。';
  },e.currentTarget);
  if(current)await load();
}

async function sourceScene(host,items,onPick,isCurrent){
  const target=host.querySelector('[data-component-canvas]');target.innerHTML='';
  const available=items.filter(r=>r.status==='SOURCE_MESH');
  if(!available.length){target.innerHTML='<p class="empty">当前范围没有可显示的源实体；不会用方块替代缺失的门窗、空调或家具。</p>';return ()=>{};}
  try{
    const THREE=await import('three'),{OrbitControls}=await import('three/addons/controls/OrbitControls.js');
    if(!isCurrent()||!target.isConnected)return ()=>{};
    const scene=new THREE.Scene();scene.background=new THREE.Color('#eaf0f5');
    scene.add(new THREE.HemisphereLight(0xffffff,0x657889,2.5));const light=new THREE.DirectionalLight(0xffffff,2);light.position.set(30,60,20);scene.add(light);
    const renderer=new THREE.WebGLRenderer({antialias:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));target.append(renderer.domElement);
    const camera=new THREE.PerspectiveCamera(45,1,.05,100000),controls=new OrbitControls(camera,renderer.domElement),colors={structure:0xb4bfcb,doors_windows:0x408cb5,stairs:0x819e90,services:0xd69b61,furniture:0xa38db4};
    const meshes=available.map(row=>{
      const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(row.vertices.flatMap(([x,y,z])=>[x,z,-y]),3));geometry.setIndex(row.triangles.flat());geometry.computeVertexNormals();
      const mesh=new THREE.Mesh(geometry,new THREE.MeshStandardMaterial({color:colors[row.category],roughness:.8,side:THREE.DoubleSide}));mesh.userData.record=row;scene.add(mesh);return mesh;
    });
    const bounds=new THREE.Box3();meshes.forEach(mesh=>bounds.expandByObject(mesh));const center=bounds.getCenter(new THREE.Vector3()),size=bounds.getSize(new THREE.Vector3());
    const resize=()=>{renderer.setSize(Math.max(200,target.clientWidth),Math.max(300,target.clientHeight));camera.aspect=Math.max(200,target.clientWidth)/Math.max(300,target.clientHeight);camera.updateProjectionMatrix();camera.position.copy(center).add(new THREE.Vector3(1,.7,1).normalize().multiplyScalar(Math.max(size.length(),3)*1.6/Math.min(1,camera.aspect)));controls.target.copy(center);controls.update();};
    const observer=new ResizeObserver(resize);observer.observe(target);resize();
    let down,selected,alive=true;
    renderer.domElement.onpointerdown=e=>{down=[e.clientX,e.clientY];};
    renderer.domElement.onpointerup=e=>{if(!down||Math.hypot(e.clientX-down[0],e.clientY-down[1])>5)return;const rect=renderer.domElement.getBoundingClientRect(),ray=new THREE.Raycaster();ray.setFromCamera(new THREE.Vector2((e.clientX-rect.left)/rect.width*2-1,1-(e.clientY-rect.top)/rect.height*2),camera);const hit=ray.intersectObjects(meshes,false)[0];if(hit){if(selected)selected.material.emissive.setHex(0);selected=hit.object;selected.material.emissive.setHex(0x243f56);onPick(selected.userData.record);}};
    const dispose=()=>{if(!alive)return;alive=false;observer.disconnect();controls.dispose();meshes.forEach(m=>{m.geometry.dispose();m.material.dispose();});renderer.dispose();};
    function frame(){if(!alive)return;if(!host.isConnected||!target.isConnected){dispose();return;}if(!host.hidden&&!document.hidden)renderer.render(scene,camera);requestAnimationFrame(frame);}frame();return dispose;
  }catch(error){target.textContent='实际构件三维渲染失败：'+error.message;return ()=>{};}
}

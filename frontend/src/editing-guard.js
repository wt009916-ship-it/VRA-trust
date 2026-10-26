export function markUnsaved(host, dirty=true) { host.dataset.unsaved=String(dirty); }
export function hasUnsaved() { return !!document.querySelector('[data-unsaved="true"]'); }
let pending;
export function confirmNavigation() {
  if(!hasUnsaved()&&!document.querySelector('#spatial[aria-busy=true]'))return Promise.resolve(true);
  if(pending)return pending;
  const dialog=document.createElement('dialog');dialog.className='unsaved-dialog';
  const saving=!!document.querySelector('#spatial[aria-busy=true]');
  dialog.innerHTML=saving?'<h2>正在保存模型</h2><p>正在等待服务器确认，请保存完成后再切换项目。</p><div class="actions"><button class="primary" data-stay>继续等待</button></div>':'<h2>模型有未保存的修改</h2><p>离开此项目会丢失这些编辑。可返回建模工作区保存草稿，再切换项目。</p><div class="actions"><button class="primary" data-stay>继续编辑</button><button data-discard>放弃修改并离开</button></div>';
  document.body.append(dialog);dialog.showModal();
  pending=new Promise(resolve=>{
    const finish=leave=>{dialog.close();dialog.remove();pending=null;resolve(leave);};
    dialog.querySelector('[data-stay]').onclick=()=>finish(false);
    dialog.querySelector('[data-discard]')?.addEventListener('click',()=>finish(true));
    dialog.oncancel=e=>{e.preventDefault();finish(false);};
  });
  return pending;
}
if(typeof window!=='undefined')window.addEventListener('beforeunload',e=>{if(hasUnsaved()){e.preventDefault();e.returnValue='';}});

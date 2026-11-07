// Collapse only the submitted draft, never edits made while the request was pending.
const draft=form=>JSON.stringify([...form.querySelectorAll('input,select,textarea')].map(el=>
  [el.id,el.name,el.type,el.value,el.checked]));

export function captureTaskEditor(target) {
  const editor=target.closest?.('.task-view')?.querySelector('.task-editor');
  const form=editor?.querySelector('form');
  if(!form)return ()=>false;
  const submitted=draft(form);
  return ()=>{
    if(!target.isConnected||!editor.isConnected||draft(form)!==submitted)return false;
    const doc=target.ownerDocument;
    const moveFocus=form.contains(doc.activeElement)||doc.activeElement===doc.body;
    editor.open=false;
    if(moveFocus){target.focus({preventScroll:true});target.scrollIntoView({block:'start'});}
    return true;
  };
}

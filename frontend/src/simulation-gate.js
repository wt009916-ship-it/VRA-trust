// Scheme-specific readiness; pending/errors stay disabled and stale replies lose.
export function bindSimulationGate({button, scheme, status, initialGate, loadGate}) {
  let gate=initialGate, generation=0, busy=false;
  function render(message) {
    if (!button.isConnected) return;
    button.disabled=busy || gate?.can_simulate!==true;
    scheme.disabled=busy;
    status.textContent=message || (gate?.can_simulate===true
      ? '当前方案通过输入准入；天气条件和模型适用性仍需复核。'
      : (gate?.blockers || []).map(item=>item.message).join('；') || '当前资料尚未通过准入。');
  }
  async function refresh() {
    const token=++generation, selected=scheme.value;
    gate=null;render('正在核验所选方案，暂不能提交计算…');
    try {
      const next=await loadGate(selected);
      if (token!==generation || !button.isConnected || scheme.value!==selected) return;
      gate=next;render();
    } catch(error) {
      if (token===generation && button.isConnected) render('准入状态未确认：'+error.message);
    }
  }
  scheme.addEventListener('change',refresh);
  render();
  return {
    get ready(){return !busy && gate?.can_simulate===true;},
    begin(){busy=true;render('正在提交计算…');},
    async end(){busy=false;await refresh();},
    refresh,
  };
}

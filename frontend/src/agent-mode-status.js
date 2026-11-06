import {request} from './api.js';

// Session-only UI preference. Never retain compute permission or submitted inputs.
export function createAgentModePreference() {
  let owner=null, project=null, selected='local';
  return {
    bind(mode, userId, projectId) {
      if(!mode)return;
      if(owner!==userId||project!==projectId){selected='local';owner=userId;project=projectId;}
      mode.value=selected;
      mode.onchange=()=>{
        if(owner===userId&&project===projectId&&mode.isConnected)
          selected=['local','provider','local_model'].includes(mode.value)?mode.value:'local';
      };
    },
    clear(){owner=null;project=null;selected='local';}
  };
}

let latestRequest=0;
export async function refreshAgentMode(mode=document.querySelector('#agent-mode'),read=()=>request('/agent/status')) {
  if(!mode)return;
  const ticket=++latestRequest;
  try {
    const info=await read();
    if(!mode.isConnected||ticket!==latestRequest)return;
    mode.options[1].textContent=info.provider_ready?'AI · '+info.model:'AI · 请先配置 Key';
    mode.options[2].textContent=info.local_model_ready?'本机 AI · '+info.local_model:'本机 AI · 请先配置';
  } catch {
    if(!mode.isConnected||ticket!==latestRequest)return;
    mode.options[1].textContent='AI · 配置状态待核实';
    mode.options[2].textContent='本机 AI · 配置状态待核实';
  }
}

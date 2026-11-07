// Current-state polling is bounded; a late response cannot resurrect invalidated data.
export function createCadMonitor({ids,fetchStates,fetchRecord,onRecord,onUnknown,onChecked,timeoutMs=4000}){
 if(!Array.isArray(ids)||ids.length>50||new Set(ids).size!==ids.length)throw Error('Invalid CAD monitor scope');
 let generation=0,stopped=false,active=null;
 const current=new Map();
 function unknown(reason){
  current.clear();for(const id of ids)onUnknown(id,reason);
 }
 function invalidate(reason='verification_unavailable'){
  if(stopped)return;
  generation++;active?.abort();active=null;unknown(reason);
 }
 async function refresh(){
  if(stopped||!ids.length)return;
  const ticket=++generation;active?.abort();
  const controller=new AbortController();active=controller;
  const live=()=>!stopped&&ticket===generation;
  let timer;
  const deadline=new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('verification_timeout')),timeoutMs);});
  const work=(async()=>{
   const reply=await fetchStates(ids,controller.signal);if(!live())return;
   if(!reply||!Array.isArray(reply.states)||reply.states.length!==ids.length||
      new Set(reply.states.map(r=>r.cad_id)).size!==ids.length||
      reply.states.some(r=>!ids.includes(r.cad_id)||!['parsed','stale','unverified'].includes(r.status))||
      !Number.isFinite(Date.parse(reply.checked_at)))throw Error('invalid_state_reply');
   for(const state of reply.states){
    if(!live())return;
    if(state.status!=='parsed'){
     current.delete(state.cad_id);onUnknown(state.cad_id,state.reasons?.[0]||'verification_unavailable');
    }else{
     if(!state.inspection_hash)throw Error('invalid_state_reply');
     if(current.get(state.cad_id)!==state.inspection_hash){
      const record=await fetchRecord(state.cad_id,controller.signal);if(!live())return;
      if(record.cad_id!==state.cad_id||record.status!=='parsed'||!record.result||record.hash!==state.inspection_hash){
       current.delete(state.cad_id);onUnknown(state.cad_id,record.stale_reasons?.[0]||'source_changed_during_refresh');continue;
      }
      current.set(state.cad_id,record.hash);onRecord(record);
     }
    }
    onChecked?.(state.cad_id,reply.checked_at);
   }
  })();
  try{await Promise.race([work,deadline]);}
  catch(error){if(live()){generation++;controller.abort();unknown(error.message==='verification_timeout'?'verification_timeout':'verification_unavailable');}}
  finally{clearTimeout(timer);if(active===controller)active=null;}
 }
 return {refresh,invalidate,stop(){stopped=true;generation++;active?.abort();active=null;current.clear();}};
}

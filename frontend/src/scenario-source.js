// A successful observation grants only current UI permission, never server authority.
export function scenarioSourceMatches(record,initial){
 const collection=Boolean(initial?.materialset_id),id=collection?'materialset_id':'takeoff_id',rows=collection?'materials':'layers';
 return Boolean(initial?.hash&&record?.[id]===initial[id]&&record.hash===initial.hash&&
  record.status==='measured'&&record.result?.status==='measured'&&Array.isArray(record.result[rows])&&record.result[rows].length);
}

export function createScenarioSourceGuard({read,validate,onState,timeoutMs=4000}){
 let generation=0,closed=false,active=null,state='unchecked';
 const emit=value=>{state=value;onState(value);};
 function invalidate(reason='unavailable'){
  if(closed)return;
  generation++;active?.abort();active=null;emit(reason);
 }
 async function refresh(){
  if(closed)return null;
  const ticket=++generation;active?.abort();
  const controller=new AbortController();active=controller;emit('checking');
  const live=()=>!closed&&ticket===generation;
  let timer;
  const deadline=new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('timeout')),timeoutMs);});
  try{
   const record=await Promise.race([Promise.resolve().then(()=>read(controller.signal)),deadline]);
   if(!live())return null;
   if(!validate(record)){emit('stale');return null;}
   emit('current');return record;
  }catch(error){
   if(live()){generation++;controller.abort();emit(error.message==='timeout'?'timeout':'unavailable');}
   return null;
  }finally{clearTimeout(timer);if(active===controller)active=null;}
 }
 return {refresh,invalidate,current:()=>!closed&&state==='current',
  stop(){closed=true;generation++;active?.abort();active=null;state='closed';}};
}

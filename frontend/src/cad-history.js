// Server pages retain membership, but details are revalidated on every visit.
export function createCadHistory({fetchPage,onLoading,onPage,onError,timeoutMs=15000}){
 let epoch=0,stopped=false,active=null,current=0,snapshot=null,next=null,cursors=[null];
 async function load(target=0,reset=false){
  if(stopped)return;
  if(!reset&&(!Number.isInteger(target)||target<0||target>=cursors.length))return;
  const ticket=++epoch;active?.abort();const controller=new AbortController();active=controller;
  if(reset){snapshot=null;next=null;cursors=[null];target=0;}
  const before=cursors[target],frozen=snapshot;
  onLoading();let timer;
  const deadline=new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('读取超时，请重新加载记录。')),timeoutMs);});
  try{
   const reply=await Promise.race([fetchPage({before,snapshot:frozen,limit:20},controller.signal),deadline]);
   if(stopped||ticket!==epoch)return;
   if(!reply||!Array.isArray(reply.records)||reply.records.length>20||reply.limit!==20||
      !Number.isSafeInteger(reply.snapshot)||reply.snapshot<0||(frozen!==null&&reply.snapshot!==frozen)||
      new Set(reply.records.map(r=>r?.cad_id)).size!==reply.records.length||
      reply.records.some(r=>!/^cad_[a-f0-9]{32}$/.test(r?.cad_id||'')||!r.source)||
      (reply.next_before!==null&&(!Number.isSafeInteger(reply.next_before)||reply.next_before<=0||
       reply.next_before>reply.snapshot||(before!==null&&reply.next_before>=before)||reply.records.length!==20)))throw Error('历史分页响应不完整，请重新加载记录。');
   current=target;snapshot=reply.snapshot;next=reply.next_before;
   cursors=cursors.slice(0,current+1);if(next!==null)cursors.push(next);
   onPage(reply.records,{page:current,hasPrevious:current>0,hasNext:next!==null});
  }catch(error){if(!stopped&&ticket===epoch){controller.abort();onError(error);}}
  finally{clearTimeout(timer);if(active===controller)active=null;}
 }
 return {reset:()=>load(0,true),previous:()=>load(current-1),next:()=>load(current+1),
  stop(){stopped=true;epoch++;active?.abort();active=null;}};
}

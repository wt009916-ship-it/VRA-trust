import polygonClipping from 'polygon-clipping';

export function polygonArea(points){
  return Math.abs(points.reduce((sum,p,i)=>{const q=points[(i+1)%points.length];return sum+p[0]*q[1]-q[0]*p[1];},0))/2;
}
const multiArea=polygons=>polygons.reduce((sum,p)=>sum+polygonArea(p[0])-p.slice(1).reduce((n,r)=>n+polygonArea(r),0),0);

// Geometric exposed floor projections, not a statutory or surveyed floor area.
export function geometricFloorArea(room){
  if(room.shell?.length){
    return room.shell.reduce((area,face)=>{
      const p=face.points,n=[0,0,0];
      for(let i=1;i<p.length-1;i++){const a=p[i].map((v,k)=>v-p[0][k]),b=p[i+1].map((v,k)=>v-p[0][k]);n[0]+=a[1]*b[2]-a[2]*b[1];n[1]+=a[2]*b[0]-a[0]*b[2];n[2]+=a[0]*b[1]-a[1]*b[0];}
      return area+(n[2]/Math.hypot(...n)<-.5?polygonArea(p.map(v=>v.slice(0,2))):0);
    },0);
  }
  const sections=room.segments?.length?room.segments:[room],levels=[];
  for(const z of sections.map(s=>s.elevation_m).sort((a,b)=>a-b))if(!levels.length||z-levels.at(-1)>1e-7)levels.push(z);
  const shape=s=>[s.polygon,...(s.holes||[])];let total=0;
  for(const low of levels){
    const at=sections.filter(s=>Math.abs(s.elevation_m-low)<=1e-7).map(shape);
    const under=sections.filter(s=>s.elevation_m<low-1e-7&&s.elevation_m+s.height_m>=low-1e-7).map(shape);
    const above=polygonClipping.union(...at);
    total+=multiArea(under.length?polygonClipping.difference(above,...under):above);
  }
  return total;
}

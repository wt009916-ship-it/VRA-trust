// Triangulate each actual 3D face in its own plane; never extrude a sloping shell.
export function shellGeometry(faces, THREE) {
  const positions=[];
  for(const face of faces){
    const p=face.points.map(v=>new THREE.Vector3(...v)),origin=p[0],u=p[1].clone().sub(origin).normalize();
    const normal=new THREE.Vector3();
    for(let i=1;i<p.length-1;i++)normal.add(p[i].clone().sub(origin).cross(p[i+1].clone().sub(origin)));
    normal.normalize();const v=normal.clone().cross(u);
    const contour=p.map(a=>{const d=a.clone().sub(origin);return new THREE.Vector2(d.dot(u),d.dot(v));});
    for(const triangle of THREE.ShapeUtils.triangulateShape(contour,[])){
      for(const index of [...triangle].reverse()){const a=p[index];positions.push(a.x,a.z,a.y);}
    }
  }
  const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));geometry.computeVertexNormals();return geometry;
}

export function storeyKey(room){return room.storey_id||(room.building_id?'b:'+room.building_id+'|':'')+'z:'+room.elevation_m;}

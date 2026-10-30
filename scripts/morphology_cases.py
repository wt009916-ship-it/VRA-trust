"""Authored analytic/faceted geometries, NOT independent real-building samples."""
from math import cos, sin, pi
from backend.solid_geometry import from_mesh, footprint


def rectangle(x,y,w,d):
    return [(float(x),float(y)),(float(x+w),float(y)),(float(x+w),float(y+d)),(float(x),float(y+d))]


def room(identifier, polygon, z=0., height=3., **extra):
    return dict(id=identifier,name=identifier,polygon=polygon,elevation_m=float(z),height_m=float(height),
                conditioned=True,include_floor_area=True,source_locator='CONTROLLED authored morphology; not a surveyed building',**extra)


def solid(identifier, vertices, polygons):
    triangles=[(face[0],face[i],face[i+1]) for face in polygons for i in range(1,len(face)-1)]
    shell=from_mesh(vertices,triangles)
    for face in shell:face.update(classification='NOTDEFINED',source_id='controlled_'+identifier)
    floor=footprint(shell);zs=[p[2] for face in shell for p in face['points']]
    return room(identifier,list(floor.exterior.coords)[:-1],min(zs),max(zs)-min(zs),shell=shell)


def cases():
    square=rectangle(0,0,8,8)
    lower=dict(polygon=square,elevation_m=0.,height_m=3.)
    setback=[lower,dict(polygon=rectangle(1,1,6,6),elevation_m=3.,height_m=3.)]
    overhang=[dict(polygon=rectangle(0,0,4,4),elevation_m=0.,height_m=3.),dict(polygon=rectangle(2,0,4,4),elevation_m=3.,height_m=3.)]
    quads=[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
    base=[(0.,0.,0.),(4.,0.,0.),(4.,4.,0.),(0.,4.,0.)]
    slope=solid('Slope',base+[(0.,0.,3.),(4.,0.,5.),(4.,4.,5.),(0.,4.,3.)],quads)
    hip=solid('Hip',base+[(0.,0.,3.),(4.,0.,3.),(4.,4.,3.),(0.,4.,3.),(2.,2.,5.)],
              [(0,3,2,1),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7),(4,5,8),(5,6,8),(6,7,8),(7,4,8)])
    lean=solid('Lean',base+[(x+1.,y,3.) for x,y,_ in base],quads)
    angle=pi/12
    top=[(2+(x-2)*cos(angle)-(y-2)*sin(angle),2+(x-2)*sin(angle)+(y-2)*cos(angle),6.) for x,y,_ in base]
    twist=solid('Twist',base+top,quads)
    circle=[(5.+4*cos(2*pi*i/32),5.+4*sin(2*pi*i/32)) for i in range(32)]
    ellipse=[(6.+5*cos(2*pi*i/32),4.+3*sin(2*pi*i/32)) for i in range(32)]
    return {
      'rectangle':[room('Box',square)],
      'l_plan':[room('L',[(0.,0.),(8.,0.),(8.,3.),(3.,3.),(3.,8.),(0.,8.)])],
      'u_plan':[room('U',[(0.,0.),(9.,0.),(9.,9.),(6.,9.),(6.,3.),(3.,3.),(3.,9.),(0.,9.)])],
      'courtyard':[room('Court',rectangle(0,0,10,10),holes=[rectangle(3,3,4,4)])],
      'multiple_voids':[room('Voids',rectangle(0,0,12,12),holes=[rectangle(2,2,2,2),rectangle(8,8,2,2)])],
      'setback':[room('Setback',square,height=6.,segments=setback)],
      'cantilever':[room('Cantilever',rectangle(0,0,4,4),height=6.,segments=overhang)],
      'podium_two_towers':[room('Podium',rectangle(0,0,12,8),height=4.),room('TowerA',rectangle(0,0,4,4),4.,9.),room('TowerB',rectangle(8,0,4,4),4.,9.)],
      'skybridge':[room('Left',rectangle(0,0,4,4),height=9.),room('Right',rectangle(8,0,4,4),height=9.),room('Bridge',rectangle(4,1,4,2),6.,3.)],
      'split_level':[room('Low',rectangle(0,0,4,4)),room('High',rectangle(4,0,4,4),1.5,3.)],
      'sloped_roof':[slope], 'hip_roof':[hip], 'leaning_solid':[lean], 'twisted_faceted_solid':[twist],
      'circular_facets':[room('Circle',circle)], 'elliptical_facets':[room('Ellipse',ellipse)],
    }

from pathlib import Path
from hashlib import sha256
import json,sys,math,random
from PIL import Image,ImageDraw,ImageChops,ImageFilter
sys.path.insert(0,str(Path(__file__).parent/'drawing-components'))
from wkb_reference import polygons,extent

ROOT=Path('C:/Users/18483/AppData/Local/Temp/vra-floorplan-feasibility-20261108')
OUT=ROOT/'frozen-reference'
OUT.mkdir(exist_ok=False)
SIDE=768
data=json.loads((ROOT/'selected-geometries.json').read_text())
cases=[]

def sha(path):return sha256(path.read_bytes()).hexdigest()
def save_case(key,image,mask,boxes,group,provenance):
    image_path=OUT/(key+'.png');mask_path=OUT/(key+'-wall.png')
    image.save(image_path);mask.save(mask_path)
    record={'image_id':key,'source_sha256':sha(image_path),'width':SIDE,'height':SIDE,
            'boxes':boxes,'wall_mask_file':mask_path.name,'wall_mask_sha256':sha(mask_path),'group':group,'provenance':provenance}
    cases.append(record)

for index,plan in enumerate(data['plans']):
    geometries={k:polygons(plan[k]['_wkb_hex']) for k in ('wall','door','front_door','window')}
    all_points=[p for values in geometries.values() for poly in values for ring in poly for p in ring]
    xmin,ymin=min(p[0] for p in all_points),min(p[1] for p in all_points)
    xmax,ymax=max(p[0] for p in all_points),max(p[1] for p in all_points)
    scale=512/max(xmax-xmin,ymax-ymin)
    dx=(SIDE-scale*(xmax-xmin))/2;dy=(SIDE-scale*(ymax-ymin))/2
    def xy(p):return (dx+(p[0]-xmin)*scale,dy+(ymax-p[1])*scale)
    def poly_mask(poly):
        mask=Image.new('L',(SIDE,SIDE));draw=ImageDraw.Draw(mask)
        draw.polygon([xy(p) for p in poly[0]],fill=255)
        for hole in poly[1:]:draw.polygon([xy(p) for p in hole],fill=0)
        return mask
    wall=Image.new('L',(SIDE,SIDE))
    for poly in geometries['wall']:wall=ImageChops.lighter(wall,poly_mask(poly))
    cutouts=Image.new('L',(SIDE,SIDE))
    for label in ('door','front_door','window'):
        for poly in geometries[label]:cutouts=ImageChops.lighter(cutouts,poly_mask(poly))
    overlap=ImageChops.darker(wall,cutouts).histogram()[255]
    wall=ImageChops.subtract(wall,cutouts)
    image=Image.new('RGB',(SIDE,SIDE),'white');image.paste('black',(0,0,SIDE,SIDE),wall)
    draw=ImageDraw.Draw(image);boxes=[];seen=set()
    for label in ('door','front_door','window'):
        for poly in geometries[label]:
            b=extent(poly);a=xy((b[0],b[3]));z=xy((b[2],b[1]))
            left,top,right,bottom=*a,*z
            category='window' if label=='window' else 'door'
            identity=(category,*[round(v,7) for v in (left,top,right,bottom)])
            if identity in seen:continue
            seen.add(identity)
            if category=='window':
                draw.rectangle((left,top,right,bottom),outline='black',width=1)
                if right-left>=bottom-top:
                    draw.line((left,(top+bottom)/2,right,(top+bottom)/2),fill='black',width=1)
                else:
                    draw.line(((left+right)/2,top,(left+right)/2,bottom),fill='black',width=1)
                box=[left-1,top-1,right+1,bottom+1]
            elif right-left>=bottom-top:
                radius=right-left;cx=left;cy=(top+bottom)/2
                draw.arc((cx-radius,cy-radius,cx+radius,cy+radius),270,360,fill='black',width=1)
                draw.line((cx,cy,cx,cy-radius),fill='black',width=2)
                box=[cx-1,cy-radius-1,cx+radius+1,cy+1]
            else:
                radius=bottom-top;cx=(left+right)/2;cy=bottom
                draw.arc((cx-radius,cy-radius,cx+radius,cy+radius),180,270,fill='black',width=1)
                draw.line((cx,cy,cx-radius,cy),fill='black',width=2)
                box=[cx-radius-1,cy-radius-1,cx+1,cy+1]
            assert 0<=box[0]<box[2]<=SIDE and 0<=box[1]<box[3]<=SIDE
            boxes.append({'category':category,'box':box})
    provenance={'dataset_id':plan['id'],'dataset_commit':data['selection']['source_commit'],
                'coordinate_transform':[scale,0,dx-xmin*scale,0,-scale,dy+ymax*scale],
                'native_coordinates':'dataset coordinates; no engineering unit inferred',
                'opening_priority_overlap_pixels':overlap,
                'door_glyph':'synthetic quarter-circle/leaf; opening polygon supplies span, hinge/swing direction is arbitrary, not source building fact',
                'label_origin':'source geometry for walls/openings; derived symbol bounding boxes from independent renderer',
                'source_images_available':False}
    key=f'resplan-{plan["id"]}'
    save_case(key,image,wall,boxes,'rendered_clean',provenance)
    if index<4:
        modified=boxes;new_mask=wall
        if index==0:
            variant=image.resize((256,256),Image.Resampling.BILINEAR).resize((SIDE,SIDE),Image.Resampling.BILINEAR);kind='low_resolution_256'
        elif index==1:
            variant=image.filter(ImageFilter.GaussianBlur(1.4));kind='gaussian_blur_1_4'
        elif index==2:
            variant=image.rotate(6,resample=Image.Resampling.BICUBIC,fillcolor='white')
            new_mask=wall.rotate(6,resample=Image.Resampling.NEAREST,fillcolor=0);kind='rotation_ccw_6'
            radians=math.radians(6);c,s=math.cos(radians),math.sin(radians)
            def turn(x,y):return [c*(x-SIDE/2)+s*(y-SIDE/2)+SIDE/2,-s*(x-SIDE/2)+c*(y-SIDE/2)+SIDE/2]
            modified=[]
            for item in boxes:
                l,t,r,b=item['box'];corners=[turn(x,y) for x,y in ((l,t),(r,t),(r,b),(l,b))]
                modified.append({'category':item['category'],'box':[min(p[0] for p in corners),min(p[1] for p in corners),max(p[0] for p in corners),max(p[1] for p in corners)]})
        else:
            variant=image.copy();pixels=variant.load();rng=random.Random(20261108)
            for x,y in rng.sample([(x,y) for y in range(SIDE) for x in range(SIDE)],SIDE*SIDE//100):
                color=0 if rng.random()<0.5 else 255;pixels[x,y]=(color,color,color)
            kind='salt_pepper_1_percent_seed_20261108'
        save_case(key+'-degraded',variant,new_mask,modified,'rendered_degraded',{**provenance,'degradation':kind,'parent':key,'not_independent_building':True})

blank=Image.new('RGB',(SIDE,SIDE),'white');zero=Image.new('L',(SIDE,SIDE))
save_case('negative-blank',blank,zero,[],'negative',{'nature':'generated blank page; no architecture'})
grid=blank.copy();draw=ImageDraw.Draw(grid)
for position in range(100,700,50):
    draw.line((100,position,650,position),fill='black',width=1);draw.line((position,100,position,650),fill='black',width=1)
draw.text((100,70),'NUMERIC GRID - NOT A FLOOR PLAN',fill='black')
save_case('negative-grid',grid,zero,[],'negative',{'nature':'generated numeric grid; no building components'})
manifest={'cases':cases,'no_inference_yet':True,'selection':data['selection'],
          'model_id':'florence-community/Florence-2-base-ft','model_revision':json.loads((ROOT/'acquisition-metadata.json').read_text())['model_revision'],
          'tasks':{'door':'<OPEN_VOCABULARY_DETECTION>doors in the floor plan','window':'<OPEN_VOCABULARY_DETECTION>windows in the floor plan',
                   'wall':'<REFERRING_EXPRESSION_SEGMENTATION>walls in the floor plan'},
          'generation':{'max_new_tokens':512,'num_beams':3,'do_sample':False},
          'screen_gate':{'clean_door_precision_min':0.85,'clean_door_recall_min':0.85,'clean_window_precision_min':0.85,'clean_window_recall_min':0.85,
                         'clean_wall_micro_iou_min':0.8,'clean_wall_macro_iou_min':0.75,'degraded_each_class_f1_min':0.7,'degraded_wall_micro_iou_min':0.65,
                         'negative_opening_predictions_max':0,'negative_wall_pixels_fraction_max':0.01,'inference_failures_max':0},
          'iou_threshold':0.5,'gate_meaning':'Candidate screening only; passing does not close D08 or warrant any score without independent real drawing evaluation and app integration',
          'training':False,'label_review':'publisher-derived geometry plus renderer-derived symbol extents; not third-party expert labels',
          'hashes':{'selected_geometries':sha(ROOT/'selected-geometries.json'),'renderer':sha(Path(__file__)),'wkb_decoder':sha(Path(__file__).parent/'drawing-components/wkb_reference.py'),
                    'evaluator':sha(Path(__file__).parent/'drawing-components/evaluate.py')}}
(OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'case_count':len(cases),'clean_buildings':8,'correlated_degradations':4,'negatives':2,'manifest_sha256':sha(OUT/'manifest.json'),
                  'counts':{c:sum(x['category']==c for r in cases if r['group']=='rendered_clean' for x in r['boxes']) for c in ('door','window')}}),flush=True)

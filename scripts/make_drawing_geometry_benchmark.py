"""Freeze independently authored image geometry before running any application algorithm."""
import hashlib,json,random,sys
from pathlib import Path
from PIL import Image,ImageDraw,ImageFilter,ImageFont


def main():
    font_path,output=map(Path,sys.argv[1:3]);output.mkdir(parents=True,exist_ok=False)
    font=ImageFont.truetype(str(font_path),28)
    clean=Image.new('RGB',(1000,700),'white');d=ImageDraw.Draw(clean)
    d.rectangle((70,80,930,620),outline='black',width=4)
    for x in (350,680):d.line((x,80,x,620),fill='black',width=3)
    for y in (260,440):d.line((70,y,930,y),fill='black',width=3)
    labels=[('7200 mm',(430,25)),('WEST',(150,160)),('CENTER',(450,320)),('EAST',(760,510))]
    for text,xy in labels:d.text(xy,text,font=font,fill='black')
    # Images are degraded by Pillow.rotate, independently of the application affine implementation.
    cases=[('sharp',clean,0.,False),('turn_3_25',clean.rotate(3.25,resample=Image.Resampling.BICUBIC,expand=True,fillcolor='white'),3.25,False),
           ('turn_minus_9_5',clean.rotate(-9.5,resample=Image.Resampling.BICUBIC,expand=True,fillcolor='white'),-9.5,False)]
    noisy=clean.copy();d=ImageDraw.Draw(noisy);rng=random.Random(1107)
    for _ in range(800):d.point((rng.randrange(1000),rng.randrange(700)),fill='black')
    cases.append(('noise_6',noisy.rotate(6,resample=Image.Resampling.BICUBIC,expand=True,fillcolor='white'),6.,False))
    cases.append(('blur_minus_4',clean.filter(ImageFilter.GaussianBlur(1.2)).rotate(-4,resample=Image.Resampling.BICUBIC,expand=True,fillcolor='white'),-4.,False))
    missing=clean.copy();ImageDraw.Draw(missing).rectangle((425,20,580,65),fill='white')
    cases.append(('missing_dimension',missing,0.,False))
    missing_wall=clean.copy();ImageDraw.Draw(missing_wall).rectangle((345,290,355,330),fill='white')
    cases.append(('missing_wall',missing_wall,0.,False))
    half=clean.resize((500,350));a=half.rotate(8,expand=True,fillcolor='white');b=half.rotate(-8,expand=True,fillcolor='white')
    mixed=Image.new('RGB',(a.width+b.width,max(a.height,b.height)),'white');mixed.paste(a,(0,0));mixed.paste(b,(a.width,0))
    cases.append(('ambiguous',mixed,None,False));cases.append(('blank',Image.new('RGB',(600,400),'white'),None,False))
    weak=Image.new('RGB',(100,100),'white');ImageDraw.Draw(weak).line((10,50,90,50),fill='black',width=1)
    cases.append(('weak_filter',weak,None,True))
    manifest={'source_kind':'SELF_AUTHORED_SYNTHETIC_NOT_REAL_BUILDING','seed':1107,'font_sha256':hashlib.sha256(font_path.read_bytes()).hexdigest(),
              'label_truth':[{'text':text,'position':list(xy)} for text,xy in labels],
              'angle_tolerance_degrees':.35,'roundtrip_tolerance_px':1e-6,'cases':[],
              'public':{'file':'cambridge-cottage.jpg','sha256':'5f7612e58e7e8da00c8ebeb646e896a38858997ffd28d5bd9d464a8250ffb58d',
              'source_page':'https://commons.wikimedia.org/w/index.php?title=File:Cambridge_cottage_floorplan.jpg&oldid=1111210234',
              'angle_truth':None,'notice':'Public historical drawing has nonuniform geometry; no absolute skew or engineering scale truth. Selected label subset only.',
              'labels':[{'text':text,'region':box} for text,box in [('PORTICO',[1170,305,1310,355]),('YARD',[415,555,500,635]),
                ('ENTRANCE HALL',[1185,550,1315,640]),('HALL',[1160,830,1290,920]),('CORRIDOR',[1540,720,1810,800]),
                ('DRAWING ROOM',[2090,950,2330,1050]),('DINING ROOM',[1390,950,1580,1070]),('GARDEN ROOM',[920,1080,1110,1170])]]}}
    for name,image,angle,filtered in cases:
        path=output/(name+'.png');image.save(path)
        manifest['cases'].append({'file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'size':list(image.size),
                                  'expected_correction_degrees':angle,'auto_should_decline':name in {'ambiguous','blank'},'median_filter':filtered,
                                  'expected_removed_dark_pixels':81 if filtered else None,
                                  'expected_white_source_point':[350,310] if name=='missing_wall' else None,
                                  'missing_labels':['7200 mm'] if name=='missing_dimension' else []})
    (output/'truth.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'root':str(output),'cases':len(cases),'truth_sha256':hashlib.sha256((output/'truth.json').read_bytes()).hexdigest()}))


if __name__=='__main__':main()

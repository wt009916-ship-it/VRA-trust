"""Generate original synthetic drawing inputs and independent label truth, not field data."""
import hashlib
import json
import random
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont


def main():
    font_path,output=map(Path,sys.argv[1:3]);output.mkdir(parents=True,exist_ok=False)
    font=ImageFont.truetype(str(font_path),36)
    image=Image.new('RGB',(1200,900),'white');draw=ImageDraw.Draw(image)
    draw.rectangle((120,160,1080,760),outline='black',width=5)
    draw.line((600,160,600,400),fill='black',width=4);draw.line((600,490,600,760),fill='black',width=4)
    draw.arc((510,400,690,580),180,270,fill='black',width=2)
    draw.line((120,110,1080,110),fill='black',width=2)
    for x in (120,1080):draw.line((x,90,x,135),fill='black',width=2)
    labels=[('平面图',(490,30)),('6000 mm',(480,120)),('办公室',(260,330)),('会议室',(780,330)),('LEVEL 1',(450,800))]
    truth=[]
    for text,position in labels:
        draw.text(position,text,font=font,fill='black')
        truth.append({'text':text,'bbox':list(draw.textbbox(position,text,font=font))})
    variants={'clean':image,'blur':image.filter(ImageFilter.GaussianBlur(2.2)),
              'low_resolution':image.resize((300,225),Image.Resampling.LANCZOS),
              'tilted':image.rotate(7,expand=True,fillcolor='white')}
    missing=image.copy();ImageDraw.Draw(missing).rectangle((470,118,690,161),fill='white');variants['missing_dimension']=missing
    damaged=image.copy();d=ImageDraw.Draw(damaged);d.rectangle((240,345,390,357),fill=(80,80,80));d.line((740,310,950,390),fill='black',width=5)
    rng=random.Random(711)
    for _ in range(1800):
        x,y=rng.randrange(1200),rng.randrange(900);d.point((x,y),fill=(70,70,70))
    variants['noise_overlap']=damaged
    blank=Image.new('RGB',(600,400),'white');variants['blank']=blank
    manifest={'kind':'self_authored_synthetic_floor_plan_not_real_building','font_sha256':hashlib.sha256(font_path.read_bytes()).hexdigest(),
              'font_name':font.getname(),'seed':711,'labels':truth,'cases':[]}
    for name,img in variants.items():
        path=output/(name+'.png');img.save(path)
        expected=[] if name=='blank' else [t['text'] for t in truth if name!='missing_dimension' or t['text']!='6000 mm']
        manifest['cases'].append({'file':path.name,'width':img.width,'height':img.height,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                                  'expected_labels':expected,'missing_labels':['6000 mm'] if name=='missing_dimension' else [],
                                  'source':'synthetic, independent text ground truth'})
    (output/'truth.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(len(variants),'synthetic cases generated; original text truth stored separately')


if __name__=='__main__':main()

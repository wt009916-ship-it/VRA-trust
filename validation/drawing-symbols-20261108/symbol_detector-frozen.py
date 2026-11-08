"""Bounded architectural-symbol hypotheses from pixels; no engineering facts.

Classical CV prototype. Thick connected ink suggests walls, quarter-circle plus
leaf suggests a hinged door, and three aligned lines between wall ends suggest
a window. Shape agreement scores are not calibrated correctness probabilities.
"""
import math
import cv2
import numpy as np
from PIL import Image

VERSION='architectural-symbol-geometry-v1'
MAX_SIDE=1200
MAX_PIXELS=1_440_000


def _iou(a,b):
    inter=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
    area=lambda x:(x[2]-x[0])*(x[3]-x[1])
    return inter/(area(a)+area(b)-inter) if inter else 0.


def _suppress(rows):
    selected=[]
    for row in sorted(rows,key=lambda r:(-r['shape_agreement'],r['box'])):
        if not any(_iou(row['box'],other['box'])>0.3 for other in selected):selected.append(row)
        if len(selected)>=200:break
    return selected


def _deskew(gray):
    edges=cv2.Canny(gray,50,150)
    lines=cv2.HoughLinesP(edges,1,np.pi/1800,60,minLineLength=max(40,min(gray.shape)//12),maxLineGap=3)
    if lines is None:return gray,np.eye(3),None
    candidates=[]
    for x,y,a,b in lines.reshape(-1,4):
        angle=math.degrees(math.atan2(int(b)-int(y),int(a)-int(x)))
        normalized=(angle+45)%90-45
        candidates.append((normalized,math.hypot(int(b)-int(y),int(a)-int(x)),abs((angle+90)%180-90)<=45))
    total=sum(row[1] for row in candidates);cumulative=0
    for angle,length,_ in sorted(candidates):
        cumulative+=length
        if cumulative>=total/2:break
    agreeing=[row for row in candidates if abs(row[0]-angle)<=1]
    support=sum(row[1] for row in agreeing)/total
    if support<0.8 or sum(row[2] for row in agreeing)<2 or sum(not row[2] for row in agreeing)<2 or abs(angle)>15 or abs(angle)<0.2:
        return gray,np.eye(3),{'applied':False,'direction_agreement':support,'estimated_degrees':angle}
    h,w=gray.shape
    # Image-coordinate line angle -> OpenCV counterclockwise correction.
    matrix=cv2.getRotationMatrix2D((w/2,h/2),angle,1)
    corners=np.array([[0,0,1],[w,0,1],[w,h,1],[0,h,1]],dtype=float)@matrix.T
    low=corners.min(axis=0);high=corners.max(axis=0);matrix[:,2]-=low
    size=np.ceil(high-low).astype(int)
    if size.prod()>2_000_000:return gray,np.eye(3),{'applied':False,'reason':'expanded raster budget'}
    result=cv2.warpAffine(gray,matrix,tuple(size),flags=cv2.INTER_LINEAR,borderValue=255)
    return result,np.vstack([matrix,[0,0,1]]),{'applied':True,'direction_agreement':support,'estimated_degrees':angle}


def _walls(ink):
    opened=cv2.morphologyEx(ink,cv2.MORPH_OPEN,np.ones((3,3),np.uint8))
    count,labels,stats,_=cv2.connectedComponentsWithStats(opened,connectivity=8)
    mask=np.zeros_like(ink)
    for i in range(1,count):
        x,y,w,h,area=stats[i]
        if area>=60 and max(w,h)>=24:mask[labels==i]=1
    return mask


def _doors(thin,walls):
    if not np.any(walls):return []
    h,w=thin.shape;raw=thin.astype('float32');near=cv2.dilate(thin,np.ones((3,3),np.uint8)).astype('float32')
    integral=cv2.integral(raw);distance=cv2.distanceTransform(1-walls,cv2.DIST_L2,3)
    rows=[]
    # With a one-pixel matching tolerance, quarter-arc sagitta must exceed
    # three pixels (r*(1-cos(45deg))) to distinguish a curved opening from
    # tiny rectangular window corners. Smaller symbols remain unclassified.
    for radius in range(12,min(97,min(w,h)//3),2):
        size=radius+3
        arc=np.zeros((size,size),np.uint8);leaf=arc.copy()
        cv2.ellipse(arc,(1,radius+1),(radius,radius),0,270,360,1,1)
        cv2.line(leaf,(1,1),(1,radius+1),1,1)
        original=np.maximum(arc,leaf)
        sums=integral[size:,size:]-integral[:-size,size:]-integral[size:,:-size]+integral[:-size,:-size]
        for mirrored in (False,True):
            base=np.fliplr(original) if mirrored else original
            arc_base=np.fliplr(arc) if mirrored else arc
            leaf_base=np.fliplr(leaf) if mirrored else leaf
            jambs=[(1,radius+1),(radius+1,radius+1)]
            if mirrored:jambs=[(size-1-x,y) for x,y in jambs]
            for turn in range(4):
                template=np.ascontiguousarray(np.rot90(base,turn))
                template_near=cv2.dilate(template,np.ones((3,3),np.uint8)).astype('float32')
                recall=cv2.matchTemplate(near,template.astype('float32'),cv2.TM_CCORR)/int(template.sum())
                precision=cv2.matchTemplate(raw,template_near,cv2.TM_CCORR)/np.maximum(sums,1)
                scores=2*precision*recall/np.maximum(precision+recall,1e-6)
                maxima=(scores>=0.68)&(scores>=cv2.dilate(scores,np.ones((5,5),np.uint8))-1e-6)
                yy,xx=np.where(maxima)
                if len(xx)>400:
                    best=np.argsort(scores[yy,xx])[-400:];yy,xx=yy[best],xx[best]
                transformed=jambs
                for _ in range(turn):transformed=[(y,size-1-x) for x,y in transformed]
                arc_mask=np.rot90(arc_base,turn);leaf_mask=np.rot90(leaf_base,turn)
                for y,x in zip(yy.tolist(),xx.tolist()):
                    if any(distance[y+jy,x+jx]>max(3,radius*0.08) for jx,jy in transformed):continue
                    crop=near[y:y+size,x:x+size]
                    if crop[arc_mask>0].mean()<0.80 or crop[leaf_mask>0].mean()<0.75:continue
                    rows.append({'category':'door','box':[x,y,x+size,y+size],
                                 'shape_agreement':float(min(1,scores[y,x])),'basis':'quarter_arc_and_leaf_between_thick_ink_ends'})
    return _suppress(rows)


def _runs(mask):
    result=[]
    closed=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((1,3),np.uint8))
    for y,line in enumerate(closed):
        edges=np.flatnonzero(np.diff(np.pad(line,(1,1)).astype('int16')))
        for left,right in zip(edges[::2],edges[1::2]):
            if 12<=right-left<=200:result.append((y,int(left),int(right)))
    return sorted(sorted(result,key=lambda r:r[2]-r[1],reverse=True)[:1800])


def _windows(thin,walls):
    if not np.any(walls):return []
    rows=[]
    for vertical in (False,True):
        mask=thin.T.copy() if vertical else thin
        wall=walls.T.copy() if vertical else walls
        distance=cv2.distanceTransform(1-wall,cv2.DIST_L2,3);lines=_runs(mask)
        for i,(y,left,right) in enumerate(lines):
            nearby=[]
            for other in lines[i+1:]:
                if other[0]-y>20:break
                if other[0]-y>=2 and abs(other[1]-left)<=3 and abs(other[2]-right)<=3:nearby.append(other)
            for y2,l2,r2 in nearby:
                if y2-y<4:continue
                middles=[p for p in nearby if y+1<p[0]<y2-1]
                if not middles:continue
                l=max(left,l2);r=min(right,r2);mid=round((y+y2)/2)
                if (r-l)<2*(y2-y) or min(l,r)<=0 or r>=mask.shape[1]:continue
                if max(distance[mid,l],distance[mid,r-1])>max(3,(y2-y)*0.6):continue
                support=(r-l)/max(right-left,r2-l2)
                score=min(1.,0.75*support+0.25*min(len(middles),3)/3)
                box=[l-1,y-1,r+1,y2+1]
                if vertical:box=[box[1],box[0],box[3],box[2]]
                rows.append({'category':'window','box':box,'shape_agreement':score,'basis':'three_parallel_lines_between_thick_ink_ends'})
    return _suppress(rows)


def detect(image):
    if not isinstance(image,Image.Image):raise ValueError('Expected decoded PIL image')
    if min(image.size)<32 or max(image.size)>6000 or image.width*image.height>12_000_000:raise ValueError('Input raster exceeds budget')
    source_size=image.size;scale=min(1.,MAX_SIDE/max(source_size))
    scaled=image.convert('L').resize((round(image.width*scale),round(image.height*scale)),Image.Resampling.BILINEAR)
    gray=np.asarray(scaled);cv2.setNumThreads(1);cv2.setRNGSeed(0)
    if int(gray.max())-int(gray.min())<20:
        return {'version':VERSION,'status':'insufficient_contrast','candidates':[],'data_nature':'GEOMETRIC_HYPOTHESES'},Image.new('L',source_size)
    aligned,matrix,deskew=_deskew(gray)
    _,ink=cv2.threshold(aligned,0,1,cv2.THRESH_BINARY_INV+cv2.THRESH_OTSU)
    if ink.mean()>0.35:raise ValueError('Dark-pixel coverage outside line-plan hypothesis')
    walls=_walls(ink);thin=ink*(1-walls)
    candidates=_doors(thin,walls)+_windows(thin,walls)
    scales=np.diag([scaled.width/image.width,scaled.height/image.height,1.])
    inverse=np.linalg.inv(matrix@scales)
    converted=[]
    for row in candidates:
        l,t,r,b=row['box']
        points=np.array([[l,t,1],[r,t,1],[r,b,1],[l,b,1]],float)@inverse.T
        low=points[:,:2].min(axis=0);high=points[:,:2].max(axis=0)
        if np.any(low<0) or high[0]>source_size[0] or high[1]>source_size[1]:continue
        converted.append({**row,'box':[*low.tolist(),*high.tolist()],'review_required':True,
                          'confidence_probability':None,'source_kind':'GEOMETRY_INFERRED'})
    source_to_aligned=matrix@scales
    restored=cv2.warpAffine(walls*255,source_to_aligned[:2],source_size,flags=cv2.INTER_NEAREST|cv2.WARP_INVERSE_MAP,borderValue=0)
    return {'version':VERSION,'status':'candidates_require_review' if converted or np.any(walls) else 'no_candidates_not_proof_of_absence',
            'candidates':converted,'deskew':deskew,'source_to_analysis':source_to_aligned.tolist(),
            'analysis_size':[aligned.shape[1],aligned.shape[0]],'data_nature':'GEOMETRIC_HYPOTHESES',
            'limitations':['Walls are thick connected ink, not verified structural members.',
                           'Only orthogonal line plans, hinged quarter-arc doors and three-line windows are hypothesized.',
                           'Furniture, text, hatch and nonstandard symbols can be false positives; missing/curved/thin walls can be missed.',
                           'Shape agreement is not a probability. No missing line is reconstructed and no engineering quantity is emitted.']},Image.fromarray(restored)

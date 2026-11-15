"""Bounded raster derivatives. Pixel transformations never reconstruct missing design data."""
import hashlib
import math

POLICY = 'drawing-raster-geometry-v1'
MAX_PIXELS = 12_000_000
MAX_SIDE = 6000


def point(matrix, xy):
    x, y = xy
    return [matrix[0]*x + matrix[1]*y + matrix[2], matrix[3]*x + matrix[4]*y + matrix[5]]


def rotation(width, height, degrees):
    if type(degrees) not in (int, float) or not math.isfinite(degrees) or abs(degrees) > 15:
        raise ValueError('Rotation must be finite, within +/-15 degrees')
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    corners = [(c*x-s*y, s*x+c*y) for x,y in ((0,0),(width,0),(width,height),(0,height))]
    left, top = min(p[0] for p in corners), min(p[1] for p in corners)
    size = [math.ceil(max(p[0] for p in corners)-left-1e-10), math.ceil(max(p[1] for p in corners)-top-1e-10)]
    if min(size)<1 or max(size)>MAX_SIDE or size[0]*size[1]>MAX_PIXELS:
        raise ValueError('Rotated raster exceeds pixel budget')
    forward = [c,-s,-left,s,c,-top]
    inverse = [c,s,c*left+s*top,-s,c,-s*left+c*top]
    return {'source_to_preview':forward,'preview_to_source':inverse,'preview_size':size,
            'source_size':[width,height], 'angle_degrees_clockwise':degrees,
            'coordinates':'pixel-edge coordinates; source is EXIF-normalized/PDF raster, not original PDF vector or engineering coordinates',
            'extent':'expanded bounding rectangle; white outside source; no clipping of source rectangle'}


def suggest_angle(image):
    import cv2
    import numpy as np
    from PIL import Image
    scaled=image.copy();scaled.thumbnail((1600,1600),Image.Resampling.BILINEAR)
    gray=np.asarray(scaled.convert('L'))
    cv2.setNumThreads(1);cv2.setRNGSeed(0)
    edges=cv2.Canny(gray,50,150)
    detected=cv2.HoughLinesP(edges,1,math.pi/1800,80,minLineLength=max(60,int(min(scaled.size)*0.08)),maxLineGap=5)
    rows=[]
    if detected is not None and not (detected.ndim==2 and detected.shape[1]==4 or detected.ndim==3 and detected.shape[1:]==(1,4)):
        raise ValueError('Unexpected native Hough line shape')
    if detected is not None:
        for line in detected.reshape(-1,4):
            x1,y1,x2,y2=map(int,line)
            a=math.degrees(math.atan2(y2-y1,x2-x1));normalized=(a+45)%90-45
            rows.append({'angle':normalized,'length':math.hypot(x2-x1,y2-y1),'axis':'horizontal' if abs((a+90)%180-90)<=45 else 'vertical',
                         'line':[x1,y1,x2,y2]})
    rows=sorted(rows,key=lambda r:(-r['length'],r['line']))[:256]
    notice='Line-direction agreement is a heuristic, not a correctness probability; symbols, perspective and non-orthogonal plans may mislead.'
    base={'method':'bounded HoughLinesP orthogonal-direction consensus','analysis_size':list(scaled.size),
          'line_count':len(rows),'parameters':{'rho_px':1,'theta_degrees':0.1,'threshold':80,'max_gap_px':5,
          'min_length_px':max(60,int(min(scaled.size)*0.08)),'max_lines':256,'support_required':0.8,'agreement_degrees':1.0},
          'limitation':notice,'suggested_correction_degrees':None,'support_ratio':None}
    if len(rows)<4:return {**base,'status':'insufficient_lines'}
    ordered=sorted(rows,key=lambda r:r['angle']);total=sum(r['length'] for r in rows);acc=0
    for row in ordered:
        acc+=row['length']
        if acc>=total/2:median=row['angle'];break
    agreeing=[r for r in rows if abs(r['angle']-median)<=1]
    support=sum(r['length'] for r in agreeing)/total
    axes={axis:sum(r['axis']==axis for r in agreeing) for axis in ('horizontal','vertical')}
    base.update(support_ratio=support,axis_line_counts=axes,median_line_angle_degrees=median)
    if support<0.8 or min(axes.values())<2:return {**base,'status':'ambiguous_directions'}
    if abs(median)>15:return {**base,'status':'outside_rotation_range'}
    return {**base,'status':'suggestion_requires_review','suggested_correction_degrees':-median}


def process(image, options, directory):
    import numpy as np
    from PIL import Image, ImageFilter
    options=options or {'deskew_mode':'none','angle_degrees':0.,'median_filter':False}
    if set(options)!={'deskew_mode','angle_degrees','median_filter'} or options['deskew_mode'] not in {'none','manual','auto'} or type(options['median_filter']) is not bool:
        raise ValueError('Invalid drawing processing options')
    requested=options['angle_degrees']
    rotation(image.width,image.height,requested)  # same finite/range contract inside the isolated worker
    if options['deskew_mode']!='manual' and requested!=0:raise ValueError('Angle applies only in manual mode')
    source=directory/'source-preview.png';image.save(source,format='PNG')
    suggestion=suggest_angle(image) if options['deskew_mode']=='auto' else None
    angle=requested if options['deskew_mode']=='manual' else (suggestion['suggested_correction_degrees'] or 0.) if suggestion else 0.
    matrix=rotation(image.width,image.height,angle)
    candidate=image
    difference=None
    if options['median_filter']:
        candidate=image.filter(ImageFilter.MedianFilter(3))
        before=np.asarray(image);after=np.asarray(candidate)
        mask=np.any(before!=after,axis=2)
        before_dark=np.asarray(image.convert('L'))<128;after_dark=np.asarray(candidate.convert('L'))<128
        path=directory/'filter-difference.png';Image.fromarray(mask.astype('uint8')*255).save(path)
        difference={'algorithm':'Pillow MedianFilter 3x3 before rotation','changed_pixels':int(mask.sum()),'total_pixels':image.width*image.height,
                    'dark_pixels_removed':int((before_dark & ~after_dark).sum()),'dark_pixels_added':int((~before_dark & after_dark).sum()),
                    'mask_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'mask_coordinates':'normalized source raster',
                    'meaning':'Pixel changes only, not semantic damage detection; thin lines and characters may be removed. No engineering correctness claim.'}
    if angle:
        candidate=candidate.transform(tuple(matrix['preview_size']),Image.Transform.AFFINE,matrix['preview_to_source'],
                                      resample=Image.Resampling.BICUBIC,fillcolor='white')
    receipt={'policy_version':POLICY,'requested':options,'transform':matrix,'auto_suggestion':suggestion,'filter_difference':difference,
             'source_preview_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
             'state':'auto_not_applied' if suggestion and suggestion['suggested_correction_degrees'] is None else 'derived_requires_review',
             'data_nature':'DERIVED_RASTER_NOT_RECONSTRUCTED_ENGINEERING_DATA',
             'resampling':'bicubic' if angle else 'none','original_preserved':True}
    return candidate,receipt

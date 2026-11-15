"""Bounded IDF 9.0 design-field comparison, not climate/engineering certification."""
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from .core import ValidationError

FIELDS = [('name',''),('month',''),('day',''),('day_type',''),('maximum_dry_bulb','C'),
 ('daily_dry_bulb_range','K'),('dry_bulb_modifier_type',''),('dry_bulb_day_schedule',''),
 ('humidity_type',''),('wetbulb_or_dewpoint','C'),('humidity_day_schedule',''),
 ('humidity_ratio','kgWater/kgDryAir'),('enthalpy','J/kg'),('daily_wet_bulb_range','K'),
 ('barometric_pressure','Pa'),('wind_speed','m/s'),('wind_direction','deg'),('rain',''),
 ('snow',''),('daylight_saving',''),('solar_model',''),('beam_day_schedule',''),
 ('diffuse_day_schedule',''),('beam_optical_depth',''),('diffuse_optical_depth',''),('sky_clearness','')]
NUMERIC = {1:(1,12),2:(1,31),4:(-90,70),5:(0,160),9:(-100,100),11:(0,1),
 12:(-1000000,10000000),13:(0,160),14:(31000,120000),15:(0,40),16:(0,360),23:(0,1.2),24:(0,3),25:(0,1.2)}
CHOICES = {
 3:'Sunday Monday Tuesday Wednesday Thursday Friday Saturday Holiday SummerDesignDay WinterDesignDay CustomDay1 CustomDay2',
 6:'DefaultMultipliers MultiplierSchedule DifferenceSchedule TemperatureProfileSchedule',
 8:'WetBulb DewPoint HumidityRatio Enthalpy RelativeHumiditySchedule WetBulbProfileMultiplierSchedule WetBulbProfileDifferenceSchedule WetBulbProfileDefaultMultipliers',
 17:'Yes No',18:'Yes No',19:'Yes No',20:'ASHRAEClearSky ZhangHuang Schedule ASHRAETau ASHRAETau2017'}
MAX_BYTES = 2 * 1024**2


def number(value, label, bounds):
    if len(value)>80 or not re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d{1,3})?',value):
        raise ValidationError('Invalid design-condition number: '+label)
    try:
        n=Decimal(value)
    except InvalidOperation as exc:
        raise ValidationError('Invalid design-condition number: '+label) from exc
    if not n.is_finite() or not Decimal(str(bounds[0]))<=n<=Decimal(str(bounds[1])):
        raise ValidationError('Out-of-range design-condition field: '+label)
    return n


def parse(raw, encoding='utf-8-sig', *, model=False):
    if not raw or len(raw)>(32*1024**2 if model else MAX_BYTES):
        raise ValidationError('Design-condition input exceeds byte budget or is empty')
    if encoding not in {'utf-8-sig','cp1252'}:
        raise ValidationError('Unsupported explicit text encoding')
    try:
        text=raw.decode(encoding,errors='strict')
    except UnicodeError as exc:
        raise ValidationError('Text decoding failed; choose actual source encoding') from exc
    if any(ord(c)<32 and c not in '\r\n\t' for c in text):
        raise ValidationError('Control characters in input')
    clean=re.sub(r'!.*','',text)
    if not clean.rstrip().endswith(';'):
        raise ValidationError('Unterminated design-condition object')
    if '"' in clean or "'" in clean:
        raise ValidationError('Quoted fields need a separate parser; no guessed tokenization')
    objects=[]
    line_number,previous_offset=1,0
    for match in re.finditer(r'([^;]+);',clean):
        part=match.group(1)
        if not part.strip():
            continue
        values=[v.strip() for v in part.split(',')]
        if len(values)>10000 or any(len(v)>2000 for v in values):
            raise ValidationError('Design-condition field budget exceeded')
        offset=match.start(1)+len(part)-len(part.lstrip())
        line_number+=clean.count('\n',previous_offset,offset)
        previous_offset=offset
        objects.append((values,line_number))
        if len(objects)>(100000 if model else 5000):
            raise ValidationError('Design-condition object budget exceeded')
    versions=[v[1:] for v,_ in objects if v[0].lower()=='version']
    if (versions and versions!=[['9.0']]) or (model and versions!=[['9.0']]):
        raise ValidationError('Only the explicit IDF 9.0 model schema is supported')
    days,sites,other={},[],set()
    for index,(obj,line) in enumerate(objects,1):
        kind,values=obj[0].lower(),obj[1:]
        if kind=='site:location':
            if len(values)!=5 or not values[0]:
                raise ValidationError('Invalid Site:Location definition')
            for v,bounds in zip(values[1:],[(-90,90),(-180,180),(-12,12),(-1000,9999.9)]):
                number(v,'Site:Location',bounds)
            sites.append({'fields':values,'object_index':index,'line':line})
        elif kind=='sizingperiod:designday':
            if not 17<=len(values)<=len(FIELDS) or not values[0]:
                raise ValidationError('Unsupported or incomplete design-day field layout')
            values+=['']*(len(FIELDS)-len(values))
            if any(len(v)>200 for v in values):
                raise ValidationError('Design-day field exceeds 200 characters')
            name=values[0].casefold()
            if name in days or len(days)>=64:
                raise ValidationError('Duplicate or excessive design days')
            for i in (1,2,3,15,16):
                if not values[i]:
                    raise ValidationError('Missing required field: '+FIELDS[i][0])
            for i,bounds in NUMERIC.items():
                if values[i]:
                    n=number(values[i],FIELDS[i][0],bounds)
                    if i in (1,2) and n!=int(n):
                        raise ValidationError('Noninteger design date')
            for i,choices in CHOICES.items():
                if values[i] and values[i].casefold() not in choices.casefold().split():
                    raise ValidationError('Unknown design-day choice: '+FIELDS[i][0])
            try:
                date(2000,int(Decimal(values[1])),int(Decimal(values[2])))
            except ValueError as exc:
                raise ValidationError('Invalid design date') from exc
            modifier=values[6].casefold() or 'defaultmultipliers'
            humidity=values[8].casefold() or 'wetbulb'
            if modifier!='temperatureprofileschedule' and not values[4]:
                raise ValidationError('Missing maximum dry-bulb temperature')
            required={'wetbulb':9,'dewpoint':9,'humidityratio':11,'enthalpy':12,
              'wetbulbprofilemultiplierschedule':9,'wetbulbprofiledifferenceschedule':9,'wetbulbprofiledefaultmultipliers':9}
            if humidity in required and not values[required[humidity]]:
                raise ValidationError('Missing humidity-condition parameter')
            if humidity in {'wetbulb','dewpoint'} and values[4] and Decimal(values[9])>Decimal(values[4]):
                raise ValidationError('Wetbulb/dewpoint exceeds coincident dry bulb')
            if modifier!='defaultmultipliers' and not values[7]:
                raise ValidationError('Missing dry-bulb day schedule')
            if 'schedule' in humidity and not values[10]:
                raise ValidationError('Missing humidity day schedule')
            if humidity in {'wetbulbprofilemultiplierschedule','wetbulbprofiledefaultmultipliers'} and not values[13]:
                raise ValidationError('Missing wetbulb daily range')
            if values[20].casefold()=='schedule' and (not values[21] or not values[22]):
                raise ValidationError('Missing solar day schedules')
            dependencies=[FIELDS[i][0] for i in (7,10,21,22) if values[i]]
            if modifier!='defaultmultipliers' or 'schedule' in humidity or values[20].casefold()=='schedule':
                dependencies.append('schedule_semantics_not_verified')
            days[name]={'name':values[0],'fields':values,'object_index':index,'line':line,
                        'unverified_dependencies':sorted(set(dependencies))}
        else:
            other.add(obj[0])
    if len(sites)!=1 or not days:
        raise ValidationError('Expected one Site:Location and at least one design day')
    return {'schema':'IDF 9.0','encoding':encoding,'site':sites[0],'days':list(days.values()),
            'other_object_types':sorted(other),'source_authority':'not_independently_verified'}


def equal(left,right,index):
    if not left or not right:
        return left==right
    return Decimal(left)==Decimal(right) if index in NUMERIC else left.casefold()==right.casefold()


def compare(model,source,pairs):
    models={d['name'].casefold():d for d in model['days']}
    sources={d['name'].casefold():d for d in source['days']}
    rows,used=[],set()
    for pair in pairs:
        m,s=pair['model_day'].casefold(),pair['source_day'].casefold()
        if m not in models or s not in sources or m in used:
            raise ValidationError('Missing or duplicate mapped design day')
        used.add(m)
        a,b=models[m],sources[s]
        fields=[{'field':name,'unit':unit,'model':a['fields'][i],'source':b['fields'][i],
                 'equal':equal(a['fields'][i],b['fields'][i],i)}
                for i,(name,unit) in enumerate(FIELDS) if i>0]
        unresolved=sorted(set(a['unverified_dependencies']+b['unverified_dependencies']))
        rows.append({'model_day':a['name'],'source_day':b['name'],
            'model_locator':{'object_index':a['object_index'],'line':a['line']},
            'source_locator':{'object_index':b['object_index'],'line':b['line']},'fields':fields,
            'unverified_dependencies':unresolved,'status':'different_fields' if any(not f['equal'] for f in fields)
            else 'unverified_schedule_dependencies' if unresolved else 'matching_declared_fields'})
    site_fields=[{'field':name,'model':a,'source':b,'equal':Decimal(a)==Decimal(b)}
        for name,a,b in zip(('latitude_deg','longitude_deg','utc_offset_h','elevation_m'),
                           model['site']['fields'][1:],source['site']['fields'][1:])]
    missing=[d['name'] for key,d in models.items() if key not in used]
    unverified_periods=[v for v in model['other_object_types'] if v.lower().startswith('sizingperiod:')]
    status=('incomplete_model_coverage' if missing else 'differences_found' if
        any(r['status']=='different_fields' for r in rows) or any(not f['equal'] for f in site_fields)
        else 'unverified_dependencies' if unverified_periods or any(r['unverified_dependencies'] for r in rows) else 'matching_declared_fields')
    return {'status':status,'rows':rows,'site_fields':site_fields,'unmapped_model_days':missing,'unverified_sizing_period_types':unverified_periods,
        'source_authority':'not_independently_verified','project_applicability':'not_assessed',
        'limitations':['仅核对声明字段；不认证统计来源、当前规范、项目适用性或原生实际采用工况。',
            '空白与显式默认值保守地区分；名称映射须用户指定，同名不自动证明同源。',
            '日程引用需要单独验证；坐标一致不证明设计条件来源权威。未修改模型或重跑物理仿真。']}

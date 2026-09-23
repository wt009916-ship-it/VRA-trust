"""Build a reproducible ENGINEERING REFERENCE, not the team's field building.
Only exterior-wall constructions differ across the three schemes.
"""
from pathlib import Path
import re, json, shutil, hashlib, argparse, math

ROOT=Path(__file__).resolve().parents[1]
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def parse(text):
    return [[v.strip() for v in part.split(',')] for part in re.sub(r'!.*','',text).split(';') if part.strip()]
def main(ep_home):
    src=Path(ep_home)/'ExampleFiles/5ZoneAirCooled.idf'
    weather=Path(ep_home)/'WeatherData/USA_CO_Golden-NREL.724666_TMY3.epw'
    dest=ROOT/'fixtures/demo/reference_5zone';dest.mkdir(parents=True,exist_ok=True)
    objs=parse(src.read_text(encoding='utf-8',errors='replace'))
    ddy=weather.with_suffix('.ddy')
    design=parse(ddy.read_text(encoding='utf-8',errors='replace'))
    selected=[o for o in design if o[0].lower()=='site:location' or (o[0].lower()=='sizingperiod:designday' and ('Htg 99.6%' in o[1] or 'Clg .4% Condns DB=>MWB' in o[1]))]
    if len(selected)!=3:raise ValueError('Expected one matching site and two design days')
    objs=[o for o in objs if o[0].lower() not in {'site:location','sizingperiod:designday'}]+selected
    objs=[o for o in objs if o[0].lower() not in {'output:sqlite','output:table:summaryreports','outputcontrol:table:style'}]
    objs += [['Output:SQLite','SimpleAndTabular'],['Output:Table:SummaryReports','AnnualBuildingUtilityPerformanceSummary'],['OutputControl:Table:Style','HTML','JtoKWH']]
    walls=[o for o in objs if o[0].lower()=='buildingsurface:detailed' and o[2].lower()=='wall' and o[5].lower()=='outdoors']
    constructions={o[3].lower() for o in walls}
    material_objects={o[1].lower():o for o in objs if o[0].lower()=='material'}
    original_wall=next(o for o in objs if o[0].lower()=='construction' and o[1].lower()=='wall-1')
    original_layers=[]
    for name in original_wall[2:]:
        mat=material_objects.get(name.lower())
        if not mat:raise ValueError('Reference wall requires explicit Material objects')
        original_layers.append({'name':name,'thickness':float(mat[3]),'lambda':float(mat[4]),'density':float(mat[5]),'price':None,'role':'原参考构造','color':10066329,'is_insulation':False})
    area=0
    for wall in walls:
        coords=[float(x) for x in wall[11:]]
        points=list(zip(coords[::3],coords[1::3],coords[2::3]))
        cross=[0.,0.,0.]
        for a,b in zip(points,points[1:]+points[:1]):
            cross[0]+=(a[1]-b[1])*(a[2]+b[2]);cross[1]+=(a[2]-b[2])*(a[0]+b[0]);cross[2]+=(a[0]-b[0])*(a[1]+b[1])
        area+=math.sqrt(sum(c*c for c in cross))/2
    # Gross exterior wall area includes openings: excluded from costing until reviewed.
    schemes=[]
    for name,thickness in [('baseline',0),('R1',.08),('R2',.10)]:
        copy=[o[:] for o in objs]
        if thickness:
            copy.append(['Material','VRA_REFERENCE_INSULATION','MediumRough',str(thickness),'0.040','80','840','0.9','0.7','0.7'])
            for o in copy:
                if o[0].lower()=='construction' and o[1].lower() in constructions:o.insert(2,'VRA_REFERENCE_INSULATION')
        model=dest/f'{name}.idf'
        model.write_text('! Engineering reference derived from EnergyPlus official 5ZoneAirCooled.idf\n! Added insulation is a scenario assumption, not a tested material or construction approval.\n\n'+'\n\n'.join(',\n  '.join(o)+';' for o in copy),encoding='utf-8')
        layers=list(reversed(original_layers))
        if thickness:layers.append({'name':'保温教学参数','thickness':thickness,'lambda':.040,'density':80,'price':None,'role':'新增外保温','color':16757603,'is_insulation':True})
        schemes.append({'scheme_id':name,'name':{'baseline':'参考原构造','R1':'参考外墙增加80mm保温','R2':'参考外墙增加100mm保温'}[name],'model':f'fixtures/demo/reference_5zone/{name}.idf','added_insulation_mm':thickness*1000,'construction_layers':layers,'u_value_scenario':1/(.17+sum(l['thickness']/l['lambda'] for l in layers)),'material_status':'scenario_assumption','changed_objects':['Construction:'+n for n in sorted(constructions)] if thickness else [],'cost':None})
    shutil.copy2(weather,dest/'weather.epw')
    shutil.copy2(ddy,dest/'source_design_days.ddy')
    shutil.copy2(Path(ep_home)/'LICENSE.txt',dest/'ENERGYPLUS_LICENSE.txt')
    record={'case_id':'reference_5zone','name':'官方五区建筑改造参考算例（非实测）','data_nature':'engineering_reference','region':'US-CO','weather':'fixtures/demo/reference_5zone/weather.epw','source_model':src.name,'source_model_sha256':digest(src),'source_weather':weather.name,'source_weather_sha256':digest(weather),'source':'EnergyPlus 9.0.1 distributed ExampleFiles and WeatherData','geometry_status':'existing frontend geometry is schematic, not this IDF','gross_exterior_wall_m2':area,'schemes':schemes,'notes':['不是郭峰辉原拟定的南昌5000平方米办公楼，不替代该模型的待交付项。','模型已有原保温；R1/R2是额外增加80/100mm，非无保温基准。','气候为美国Golden参考天气；不得声称南昌节能率。','保温参数为教学假设；无稀土性能或工程合规声明。','造价、生命周期材料数据与真实碳开发资格未提供。']}
    record['source_ddy_sha256']=digest(ddy)
    record['design_days']=[o[1] for o in selected if o[0].lower()=='sizingperiod:designday']
    record['notes'].extend(['地点与设计日取自同站配套DDY，替换官方原模型中的Chicago设计日。','各方案保留相同HVAC定义和自动定容设置，属于预设计情景比较；不等于固定现有设备条件下的现场改造验证。','案例间Warning、未满足设定点小时数须由工程人员审查，能耗排序不自动构成推荐。'])
    (dest/'case.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    (ROOT/'cases/registry.json').write_text(json.dumps({'reference_5zone':'fixtures/demo/reference_5zone/case.json'},indent=2),encoding='utf-8')
    print(json.dumps(record,ensure_ascii=False,indent=2))
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--energyplus-home',required=True);main(ap.parse_args().energyplus_home)

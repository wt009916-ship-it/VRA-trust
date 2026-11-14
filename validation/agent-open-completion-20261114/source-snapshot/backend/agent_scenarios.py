"""Read existing material comparisons; never rerun arithmetic or certify equivalence."""
from decimal import Decimal

from . import core
from .cad import Cad
from .material_takeoff import LayerTakeoffs
from .material_scenarios import MaterialScenarios

STAGES=('production','transport','construction','operation','end_of_life')
STAGE_LABELS={'production':'生产','transport':'运输','construction':'施工','operation':'运行','end_of_life':'寿命末期'}
FACTS=[prefix+'.'+key for prefix in ('baseline','alternative') for key in
       ('material_total','boundary_total_kgco2e','kgco2e_m2_over_study_period',*('stage.'+stage for stage in STAGES))]+[
       'cost_difference','carbon_reduction_kgco2e','cost_reduction_pct','carbon_reduction_pct']
MEANINGS={}
for prefix,label in [('baseline','基准方案（第1方案）'),('alternative','替换方案（第2方案）')]:
    MEANINGS[prefix+'.material_total']=label+'的材料采购金额，声明币种/报价日期；不是工程总造价'
    MEANINGS[prefix+'.boundary_total_kgco2e']=label+'的声明边界碳总量，kgCO2e，整个评估期，不是年量'
    MEANINGS[prefix+'.kgco2e_m2_over_study_period']=label+'的整个评估期单位项目建筑面积碳量，kgCO2e/m²；不是所选墙面积或年量'
    for stage in STAGES:MEANINGS[prefix+'.stage.'+stage]=label+'仅'+STAGE_LABELS[stage]+'阶段碳总量，kgCO2e，整个评估期；排除/缺测不记零'
MEANINGS.update({'cost_difference':'第2方案金额减第1方案金额，声明币种；负数表示第2方案更便宜',
 'carbon_reduction_kgco2e':'第1方案碳总量减第2方案碳总量，kgCO2e；负数表示第2方案排放更高',
 'cost_reduction_pct':'（第1方案金额－第2方案金额）/第1方案金额×100%；基准为零时未知',
 'carbon_reduction_pct':'（第1方案碳总量－第2方案碳总量）/第1方案碳总量×100%；基准为零时未知；不是认证减排量'})


def name(record):
    return ' / '.join(alt['name'] for alt in record['input']['alternatives'])


class ScenarioReads:
    def __init__(self,domain):self.service=MaterialScenarios(LayerTakeoffs(Cad(domain)))
    def view(self,pid,ident):return self.service.view(pid,ident)


def review(record):
    return {'kind':'scenario_review','record_id':record['scenario_id'],'project_id':record['project_id'],
        'record_hash':record['hash'],'name':name(record),'status':record['status'],
        'stale_reasons':record.get('stale_reasons',[]),'stale_details':record.get('stale_details',[]),
        'checked_at':core.now(),'source_status':'MODEL_GEOMETRY_WITH_USER_DECLARED_MAPPING',
        'scope':'同一IFC构件分层来源、两套声明材料方案的成本及纳入阶段碳比较；功能等效、清单完整性、工程总造价和碳资产认证均未核证。',
        'input':record['input'],'result':record['result'],
        'verified':record['status']=='calculated' and record['result'] is not None and record['result']['comparison'] is not None,
        'report_path':f"/api/projects/{record['project_id']}/material-scenarios/{record['scenario_id']}/report.html",
        'source_file_id':record['import_source']['file_id'],'takeoff_id':record['takeoff_id']}


def append_facts(record,add):
    if record['status']!='calculated' or not record.get('result') or record['result']['comparison'] is None:return
    body,result=record['input'],record['result'];years=body['study_years']
    for index,prefix in enumerate(('baseline','alternative')):
        alt=result['alternatives'][index];label=('基准方案' if index==0 else '替换方案')+'（'+alt['name']+'）'
        root='/result/alternatives/'+str(index)
        add(prefix+'.material_total',label+'材料采购金额',alt['cost']['material_total'],body['currency'],'quote_date',path=root+'/cost/material_total')
        add(prefix+'.boundary_total_kgco2e',label+'声明边界碳总量',alt['carbon']['boundary_total_kgco2e'],'kgCO2e','study_period',years=years,path=root+'/carbon/boundary_total_kgco2e')
        add(prefix+'.kgco2e_m2_over_study_period',label+'评估期单位项目建筑面积碳量',alt['carbon']['kgco2e_m2_over_study_period'],'kgCO2e/m2','study_period',years=years,area=alt['carbon_input']['area_m2'],path=root+'/carbon/kgco2e_m2_over_study_period')
        for stage,row in alt['carbon']['stages'].items():
            if row['included']:add(prefix+'.stage.'+stage,label+STAGE_LABELS[stage]+'阶段碳总量',row['kgco2e'],'kgCO2e','study_period',years=years,path=root+'/carbon/stages/'+stage+'/kgco2e')
    for key,label,unit,period in [('cost_difference','替换减基准的材料金额差',body['currency'],'quote_date'),
            ('carbon_reduction_kgco2e','基准减替换的声明边界碳差','kgCO2e','study_period'),
            ('cost_reduction_pct','条件材料金额减少比例','%','quote_date'),('carbon_reduction_pct','条件边界碳减少比例','%','study_period')]:
        reason=None
        if result['comparison'][key] is None:
            baseline=result['alternatives'][0]
            if key=='cost_reduction_pct' and Decimal(baseline['cost']['material_total'])==0:
                reason='基准材料金额为零，减少比例的分母为零，比例无定义；不等于0%。'
            elif key=='carbon_reduction_pct' and Decimal(str(baseline['carbon']['boundary_total_kgco2e']))==0:
                reason='基准边界碳总量为零，减少比例的分母为零，比例无定义；不等于0%。'
        add(key,label,result['comparison'][key],unit,period,years=years if period=='study_period' else None,
            path='/result/comparison/'+key,unavailable_reason=reason)


def context(record):
    body=record['input']
    return {'functional_scope':body['functional_scope'],'currency':body['currency'],'tax_basis':body['tax_basis'],
        'as_of':body['as_of'],'study_years':body['study_years'],'boundaries':body['boundaries'],
        'alternatives':[{'position':i,'name':a['name']} for i,a in enumerate(body['alternatives'])],
        'takeoff_id':record['takeoff_id'],'excluded_stages':[b['stage'] for b in body['boundaries'] if not b['included']],
        'notice':'基准=第1方案，替换=第2方案；金额差为替换－基准，碳减少为基准－替换。碳量覆盖整个评估期；单位面积分母是项目建筑面积。来源含模型几何及声明比例/报价/因子，不证明功能等效、全生命周期清单完整性或认证碳资产。'}

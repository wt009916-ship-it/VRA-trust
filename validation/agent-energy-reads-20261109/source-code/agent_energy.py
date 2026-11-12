"""Source-bound energy reading context; never calibration or an extra calculator."""
from contextlib import closing
from pathlib import Path
import sqlite3
from typing import Literal
from pydantic import Field,StrictBool,StrictInt
from .schema import Contract
from . import core,end_use,end_use_records,utility_records
from .hourly_thermal import environment_rows,HourlyEvidenceError

KINDS={'enduse','utility'}
CARRIERS={'Electricity':'Electricity','Natural Gas':'NaturalGas','Additional Fuel':'AdditionalFuel','District Cooling':'DistrictCooling','District Heating':'DistrictHeating'}
USES={key:end_use.METER_USES.get(key,key).replace(' ','') for key in end_use.USES}
END_FACTS={**{f'end_use.{use}.{carrier}':f'{end_use.USES[key]} / {raw}；年度原生能量kWh，逐时积分或原表舍入需按energy_context区分，不是实测' for key,use in USES.items() for raw,carrier in CARRIERS.items()},**{f'carrier_total.{carrier}':f'{raw}年度总量kWh；原生表舍入值，不混合能量载体' for raw,carrier in CARRIERS.items()},'site_total_kwh':'场地总能量kWh；包含不同能源载体的能量，不是外购电费或实测','native_hours':'原生年度小时数；不是实际运行设备小时数'}
UTILITY_FACTS={'bill_total_kwh':'账单覆盖期间能量总和kWh，不是费用或功率','native_total_kwh':'同一映射期间的模拟能量总和kWh，不一定全年','mbe_percent':'100Σ(模拟−账单)/Σ账单；全年抵消不能证明逐期误差小；百分比','rmse_kwh':'等权账期能量差的均方根kWh；分母n','cvrmse_percent':'100RMSE/账单平均期间能量；百分比，零账单总量时无定义','interval_count':'比较账期数，不是月数或独立建筑数','compared_hours':'实际覆盖模拟小时数，不是全年小时数','native_year_hours':'完整原生年度小时数，不是比较覆盖小时数'}


class EnergyContext(Contract):
    run_id:str=Field(pattern=r'^run_[a-f0-9]{32}$')
    native_year:StrictInt|None=Field(ge=1900,le=2100)
    native_start:str|None=Field(max_length=40)
    native_end:str|None=Field(max_length=40)
    bill_start:str|None=Field(max_length=40)
    bill_end:str|None=Field(max_length=40)
    alignment:Literal['native_annual','exact_calendar','calendar_pattern']
    clock_basis:Literal['native_simulation_clock','local_standard_time']
    uses_daylight_saving:StrictBool
    weather_calendar_matches_native:StrictBool|None
    carrier:str=Field(min_length=1,max_length=80)
    boundary:str=Field(min_length=1,max_length=200)
    data_nature:Literal['model_scenario','measured','published_reference','synthetic']
    basis:Literal['hourly_meter_integral','native_table_rounded','bill_interval_statistics','native_clock_count']


class EndUseReads:
    def __init__(self,domain):self.ledgers=end_use_records.Ledgers(domain)
    def view(self,pid,ident):
        record=self.ledgers.view(pid,ident);record['result']=record.get('summary');record['energy_clock']=None
        if record['result'] is None:return record
        try:
            source,rd=self.ledgers.source(pid,record['source_run']['run_id'])
            if source!=record['source_run']:raise core.ValidationError('Energy source changed')
            path=Path(rd)/'output/eplusout.sql'
            with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as con:
                con.row_factory=sqlite3.Row
                _,_,clock,_,_=environment_rows(con,None)
            years={r['Year'] for r in clock};year=next(iter(years)) if len(years)==1 else None
            if year is not None and not 1900<=year<=2100:year=None
            record['energy_clock']={'native_year':year,'native_start':f'{year}-01-01T00:00' if year else None,'native_end':f'{year+1}-01-01T00:00' if year else None,'uses_daylight_saving':any(r['Dst'] for r in clock)}
            if core.sha(path)!=source['sql_sha256'] or self.ledgers.source(pid,source['run_id'])[0]!=source:raise core.ValidationError('Energy source changed during clock read')
        except (ValueError,OSError,KeyError,sqlite3.Error,HourlyEvidenceError):
            record.update(status='stale',summary=None,result=None,energy_clock=None);record.setdefault('stale_reasons',[]).append('agent_native_clock_unavailable')
        return record


UtilityReads=utility_records.Comparisons


def review(record,kind):
    r=record.get('result');current=record['status'] in ('calculated_model_end_uses','compared_reference','compared_declared_measurements') and r is not None
    scope='年度原生模型设备用途能量账；区域冷热量不是耗电，原表舍入与逐时积分分开，不是实测、设备效率验证或校准。' if kind=='enduse' else '账单与模拟按声明期间/载体比较；MBE会正负抵消，CV(RMSE)反映逐期误差；零分母无定义，满足声明阈值不是实楼校准或认证。'
    route='end-use-ledgers' if kind=='enduse' else 'utility-comparisons'
    return {'kind':kind+'_review','record_id':record[kind+'_id'],'project_id':record['project_id'],'record_hash':record['hash'],'name':record['input']['name'],'status':record['status'],'source_status':'NATIVE_MODEL_NOT_MEASUREMENT' if kind=='enduse' else record['input']['bill_nature'],'scope':scope,'input':record['input'],'result':r,'energy_context':context(record,kind),'verified':current,'stale_reasons':record.get('stale_reasons',[]),'stale_details':record.get('stale_details',[]),'report_path':f"/api/projects/{record['project_id']}/{route}/{record[kind+'_id']}/report.html"}


def context(record,kind):
    r=record.get('result')
    if not r:return {'status':'source_unavailable','calibration_status':'not_certified'}
    if kind=='enduse':return {**record['energy_clock'],'hours':r['hours'],'data_nature':'model_scenario','calibration_status':'not_certified','period':'native_annual','clock_basis':'native_simulation_clock','ideal_systems':r['model']['ideal_systems']}
    return {'native_year':r['native']['year'],'original_bill_start':r['rows'][0]['original']['start'],'original_bill_end':r['rows'][-1]['original']['end'],'mapped_native_start':r['rows'][0]['mapped_start'],'mapped_native_end':r['rows'][-1]['mapped_end'],'alignment':record['input']['alignment'],'meter':r['native']['selected_meter']['name'],'carrier':r['native']['selected_meter']['resource'],'bill_nature':record['input']['bill_nature'],'method':r['statistics']['method'],'denominator':r['statistics']['denominator'],'within_declared_tolerances':r['within_declared_tolerances'],'threshold_source':record['input']['threshold_source'],'context_reasons':r['context_reasons'],'calibration_status':r['calibration_status'],'coverage':r['coverage'],'not_evaluable_reason':r['statistics']['not_evaluable_reason']}


def append_facts(record,kind,add):
    r=record['result'];run=record['source_run']['run_id']
    if kind=='utility':
        n=r['native'];first,last=r['rows'][0],r['rows'][-1]
        ctx={'run_id':run,'native_year':n['year'],'native_start':first['mapped_start'],'native_end':last['mapped_end'],'bill_start':first['original']['start'],'bill_end':last['original']['end'],'alignment':record['input']['alignment'],'clock_basis':'local_standard_time','uses_daylight_saving':False,'weather_calendar_matches_native':n['weather_calendar_matches_native'],'carrier':n['selected_meter']['resource'],'boundary':n['selected_meter']['name'],'data_nature':record['input']['bill_nature'],'basis':'bill_interval_statistics'}
        for key,label in UTILITY_FACTS.items():
            group='coverage' if key in ('compared_hours','native_year_hours') else 'statistics';value=r[group][key];unit='%' if key.endswith('percent') else 'kWh' if key.endswith('kwh') else 'hour' if key.endswith('hours') else 'count'
            add(key,label,value,unit,'utility_periods',path='/result/'+group+'/'+key,unavailable_reason='账单总量为零，百分比无定义，不是零误差或校准通过' if value is None else None,energy_context=ctx)
        return
    clock=record['energy_clock'];base={'run_id':run,**clock,'bill_start':None,'bill_end':None,'alignment':'native_annual','clock_basis':'native_simulation_clock','weather_calendar_matches_native':None,'data_nature':'model_scenario'}
    for i,row in enumerate(r['rows']):
        for carrier,cell in row['carriers'].items():
            exact=cell['hourly_meter_kwh'] is not None;key='end_use.'+USES[row['end_use']]+'.'+CARRIERS[carrier]
            add(key,END_FACTS[key],cell['hourly_meter_kwh'] if exact else cell['tabulated']['kwh'],'kWh','native_annual',path=f'/summary/rows/{i}/carriers/{carrier}/'+('hourly_meter_kwh' if exact else 'tabulated/kwh'),energy_context={**base,'carrier':carrier,'boundary':row['end_use'],'basis':'hourly_meter_integral' if exact else 'native_table_rounded'})
    for carrier,total in r['carrier_totals'].items():
        key='carrier_total.'+CARRIERS[carrier];add(key,END_FACTS[key],total['kwh'],'kWh','native_annual',path='/summary/carrier_totals/'+carrier+'/kwh',energy_context={**base,'carrier':carrier,'boundary':'Total End Uses','basis':'native_table_rounded'})
    add('site_total_kwh',END_FACTS['site_total_kwh'],r['site_total']['kwh'],'kWh','native_annual',path='/summary/site_total/kwh',energy_context={**base,'carrier':'mixed_site_energy','boundary':'Total Site Energy','basis':'native_table_rounded'})
    add('native_hours',END_FACTS['native_hours'],r['hours'],'hour','native_annual',path='/summary/hours',energy_context={**base,'carrier':'not_applicable','boundary':'native_environment_clock','basis':'native_clock_count'})


def explanation(topic,artifact):
    c=artifact.get('energy_context') or {}
    if not artifact.get('verified'):return '当前来源无法核验；不使用历史数值解释期间或误差，不推测失效原因。'
    if topic=='period':return '原生及账单期间、时间映射均保留在energy_context；开始包含、结束不包含，原生年度不一定等于账单年份或覆盖期间。'+str(c)
    if topic=='status':return '所读模型结果或差异指标当前有效；不是实楼校准、认证、原始数据真实性或任务全面完成的证明。'
    return artifact['scope']

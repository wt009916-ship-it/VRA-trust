"""Independent Decimal oracle; no application imports or output-derived expectations."""
from pathlib import Path
from decimal import Decimal as D, ROUND_HALF_UP, localcontext
import json, hashlib
OUT=Path('C:/Users/18483/AppData/Local/Temp/vra-collection-scenarios-public-20261108')
OUT.mkdir(exist_ok=False)
geometry=Path('C:/Users/18483/AppData/Local/Temp/vra-material-collection-public-20261108/frozen-gold.json')
raw=geometry.read_bytes();g=json.loads(raw);volumes={r['material_id']:D(r['union_envelope_m3']) for r in g['cases'][-1]['materials']}
# fraction, waste, density, price, price-unit, factor, factor-unit; explicitly synthetic.
inputs=[{3932:('.08','.07','7850','1.2','kg','1.9','kg'),3941:('1','.12','800','150','m3','.22','kg'),4717:('1','.04','2400','75','t','300','m3')},
        {3932:('.07','.05','7800','1300','t','1500','t'),3941:('1','.08','750','160','m3','180','t'),4717:('1','.02','2350','78','t','.10','kg')}]
scope='公开Duplex所选四墙材料方案算术验证；不证明替换材料结构、耐火或节能等效'
body={'materialset_id':'materialset_'+'0'*32,'functional_scope':scope,'region':'US-CO','currency':'USD','tax_basis':'excluded','as_of':'2026-11-08','study_years':25,'method':'QA arithmetic v2','exclusions':['人工、机械及运输费用不计入材料报价合计'],'excluded_materials':[],
      'boundaries':[{'stage':s,'included':True,'reason':'显式合成活动清单，仅验证计算，不代表实楼完整性'} for s in ['production','transport','construction','operation','end_of_life']], 'alternatives':[]}
def factor(ident,stage,value,unit):
    return {'factor_id':ident,'value':float(value),'denominator':unit,'stage':stage,'source':'公开几何加合成因子算术验收，非认证数据库','publisher':'独立QA','version':'v2','year':2026,'region':'US-CO','method':body['method']}
expected=[]
with localcontext() as ctx:
    ctx.prec=60
    for i,rows in enumerate(inputs):
        alt={'name':['参考方案A','参考方案B'][i],'materials':[],'transport_legs':[],'other_activities':[]}
        derived=[];cost=D(0);production=D(0);mass=D(0)
        for mid,(fraction,waste,density,price,pu,ef,fu) in rows.items():
            net=volumes[mid]*D(fraction);purchase=net*(1+D(waste));kg=purchase*D(density)
            units={'m3':purchase,'kg':kg,'t':kg/1000}
            amount=(units[pu]*D(price)).quantize(D('.01'),rounding=ROUND_HALF_UP)
            carbon=units[fu]*D(ef);cost+=amount;production+=carbon;mass+=kg
            derived.append({'source_material_id':mid,'envelope_m3':str(volumes[mid]),'net_m3':str(net),'purchase_m3':str(purchase),'mass_kg':str(kg),'cost':str(amount),'production_kgco2e':str(carbon)})
            alt['materials'].append({'source_material_id':mid,'material_id':f'qa-{i}-{mid}','name':f'算术参考材料 {mid} / {i+1}',
                'solid_fraction':float(fraction),'fraction_source':'显式合成实体比例，仅验算非实测','waste_ratio':float(waste),'waste_basis':'显式合成采购损耗，仅验算非实测','density_kg_m3':float(density),'density_source':'显式合成密度，仅验算非材料认证',
                'quote':{'quote_id':f'qa-quote-{i}-{mid}','unit_price':float(price),'per_unit':pu,'currency':'USD','tax_basis':'excluded','region':'US-CO','valid_from':'2026-01-01','valid_until':'2026-12-31','source':'合成报价，仅验证单位和逐行舍入','version':'v2'},'factor':factor(f'qa-factor-{i}-{mid}','production',ef,fu)})
        distance=[50,65][i];tkm=(mass+25)/1000*distance;transport=tkm*D('.12')
        alt['transport_legs']=[{'leg_id':f'haul-{i}','name':'合成公路运段','material_ids':list(rows),'purchase_fraction':1.,'fraction_source':'整个采购批次仅一次运输','distance_km':float(distance),'distance_source':'合成路径距离，仅用于算术验收','additional_mass_kg':25.,'additional_mass_source':'显式合成托盘质量25kg','factor':factor('haul-factor','transport','.12','tkm')}]
        stages={'production':production,'transport':transport}
        for stage,q,unit,period,ef in [('construction',[125,100][i],'kWh','whole_period','.45'),('operation',[1200,1100][i],'kWh','annual','.4'),('end_of_life',[250,240][i],'kg','whole_period','.02')]:
            alt['other_activities'].append({'activity_id':stage,'name':'合成'+stage,'stage':stage,'quantity':float(q),'unit':unit,'period':period,'source':'独立合成活动量；运行差异为声明情景非模型预测','factor':factor(stage+'-factor',stage,ef,unit)})
            stages[stage]=D(q)*D(ef)*(25 if period=='annual' else 1)
        body['alternatives'].append(alt)
        expected.append({'name':alt['name'],'derivations':derived,'cost':str(cost),'transport_tkm':str(tkm),'stages':{k:str(v) for k,v in stages.items()},'carbon_total':str(sum(stages.values()))})
gold={'scope':'Public IFC geometry + explicit synthetic material/price/factor/activity assumptions; independent Decimal oracle, not real building or certified LCA',
      'geometry_gold_sha256':hashlib.sha256(raw).hexdigest(),'source_sha256':g['source_sha256'],'selected_ids':g['selected_ids'],'body':body,'expected':expected,
      'comparison':{'cost_difference':str(D(expected[1]['cost'])-D(expected[0]['cost'])),'carbon_reduction':str(D(expected[0]['carbon_total'])-D(expected[1]['carbon_total']))},
      'tolerance':{'volume_m3':'1e-7','carbon_kgco2e':'0.00001','cost':'0.00'},'training':False}
data=json.dumps(gold,ensure_ascii=False,indent=2).encode();(OUT/'frozen-gold.json').write_bytes(data)
print(json.dumps({'gold_sha256':hashlib.sha256(data).hexdigest(),'expected':[{'cost':r['cost'],'carbon_total':r['carbon_total']} for r in expected],'comparison':gold['comparison']}))

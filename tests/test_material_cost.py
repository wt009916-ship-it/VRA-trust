import copy
from fractions import Fraction as F
import pytest
from pydantic import ValidationError
from backend.material_cost import Estimate, calculate
from test_api import create_project


def quote(key,price,unit):
    return {'quote_id':key,'unit_price':price,'per_unit':unit,'currency':'USD','tax_basis':'excluded',
        'region':'US-CO','valid_from':'2026-01-01','valid_until':'2026-12-31',
        'source':'Independent synthetic quote, not market price','version':'audit-1'}


def estimate():
    common={'waste_basis':'Independent declared procurement allowance'}
    return {'name':'Independent quantity and cost audit','region':'US-CO','currency':'USD','tax_basis':'excluded',
        'as_of':'2026-11-05','functional_scope':'Synthetic equivalent envelope scope, not validated design',
        'exclusions':['Labour, equipment, transport, tax and overhead'],
        'lines':[
            {**common,'line_id':'concrete','material_id':'concrete','name':'Synthetic concrete',
             'measure':{'mode':'cuboid','unit':'m3','length':400,'width':300,'height':20,'dimension_unit':'cm','count':2,'deduction':.8,'source':'Independent cuboid dimensions'},
             'waste_ratio':.05,'density_kg_m3':2400,'density_source':'Synthetic density, not measured', 'quote':quote('q-concrete',420,'t')},
            {**common,'line_id':'insulation','material_id':'insulation','name':'Synthetic insulation',
             'measure':{'mode':'rectangle','unit':'m2','length':500,'width':240,'dimension_unit':'cm','count':3,'deduction':6,'source':'Independent area dimensions'},
             'waste_ratio':.1,'quote':quote('q-insulation',12.35,'m2')},
            {**common,'line_id':'fixings','material_id':'fixings','name':'Synthetic fixings',
             'measure':{'mode':'direct','unit':'item','quantity':3,'source':'Independent count of components'},
             'waste_ratio':.1,'quote':quote('q-fixings',2.675,'item')}]}


def cents(value):
    # Independent rational half-up oracle, without Decimal or production helpers.
    scaled=value*100+F(1,2)
    return scaled.numerator//scaled.denominator


def test_independent_rational_geometry_density_waste_and_rounding():
    r=calculate(Estimate(**estimate()))
    concrete=(F(400,100)*F(300,100)*F(20,100)*2-F(8,10))*F(105,100)*2400/1000*420
    insulation=(F(500,100)*F(240,100)*3-6)*F(11,10)*F(1235,100)
    items=4*F(2675,1000)
    expected=cents(concrete)+cents(insulation)+cents(items)
    assert r['material_total']=='4651.85' and F(r['material_total'])*100==expected
    a,b,c=r['rows']
    assert F(a['net_quantity'])==4 and F(a['purchase_quantity'])==F(42,10)
    assert F(a['quantity_in_quote_unit'])==F(1008,100) and a['amount']=='4233.60'
    assert b['amount']=='407.55' and c['purchase_quantity']=='4' and c['amount']=='10.70'
    assert r['tender_certification']==r['functional_equivalence']=='NOT_ASSESSED'


@pytest.mark.parametrize('field',['quantity','waste','price','density','density_source','deduction'])
def test_unknown_never_becomes_complete_zero(field):
    b=estimate();row=b['lines'][0]
    if field=='quantity': row['measure']['length']=None
    elif field=='waste': row['waste_ratio']=None
    elif field=='price': row['quote']['unit_price']=None
    elif field=='deduction': row['measure']['deduction']=None
    else: row['density_kg_m3' if field=='density' else field]=None
    r=calculate(Estimate(**b));assert r['status']=='incomplete' and r['material_total'] is None
    assert r['rows'][0]['amount'] is None and r['rows'][1]['amount']=='407.55'


@pytest.mark.parametrize('field,value',[('waste_ratio',-1),('waste_ratio',True),('waste_ratio','0.1'),('waste_ratio',float('nan')),('density_kg_m3',0),('density_kg_m3',1e-300)])
def test_invalid_numbers(field,value):
    b=estimate();b['lines'][0][field]=value
    with pytest.raises(ValidationError):Estimate(**b)


@pytest.mark.parametrize('field,value',[('currency','CNY'),('tax_basis','included'),('region','CN-JX'),('valid_until','2026-01-01'),('valid_from',True),('valid_from','1767225600')])
def test_quote_context_and_dates_reject_mismatches(field,value):
    b=estimate();b['lines'][0]['quote'][field]=value
    with pytest.raises(ValidationError):Estimate(**b)


def test_unit_conversion_grouping_and_line_rounding():
    b=estimate();b['lines']=b['lines'][2:];row=b['lines'][0]
    row['measure'].update(quantity=1000,unit='kg');row['waste_ratio']=0;row['quote']=quote('kg-price',.000005,'kg')
    row['line_id']='a';second=copy.deepcopy(row);second['line_id']='b';second['measure'].update(quantity=2,unit='t');b['lines'].append(second)
    r=calculate(Estimate(**b))
    assert r['material_total']=='0.02'  # 0.005 -> .01; 0.010 -> .01, then sum.
    assert F(r['materials'][0]['net'])==3000 and r['materials'][0]['unit']=='kg'


def test_mass_to_volume_and_length_conversion():
    b=estimate();b['lines']=b['lines'][:1];row=b['lines'][0]
    row['measure']={'mode':'direct','unit':'t','quantity':2.4,'source':'Independent net mass'}
    row['waste_ratio']=0;row['quote']=quote('volume',420,'m3')
    assert calculate(Estimate(**b))['material_total']=='420.00'
    row.pop('density_kg_m3');row.pop('density_source');row['measure'].update(quantity=2500,unit='mm');row['quote']=quote('length',12,'m')
    assert calculate(Estimate(**b))['material_total']=='30.00'


def test_geometry_ambiguity_units_duplicates_and_excess_deduction():
    for edit in [lambda b:b['lines'][0]['measure'].update(quantity=2),
                 lambda b:b['lines'][1]['measure'].update(height=3),
                 lambda b:b['lines'][2]['measure'].update(quantity=2.5),
                 lambda b:b['lines'][0]['quote'].update(per_unit='m2'),
                 lambda b:b['lines'].append(copy.deepcopy(b['lines'][0])),
                 lambda b:b.update(exclusions=[' '])]:
        b=estimate();edit(b)
        with pytest.raises(ValidationError):Estimate(**b)
    b=estimate();b['lines'][0]['measure']['deduction']=5
    with pytest.raises(ValueError,match='Deduction'):calculate(Estimate(**b))
    b=estimate();extra=copy.deepcopy(b['lines'][0]);extra['line_id']='different';extra['quote']['version']='2';b['lines'].append(extra)
    with pytest.raises(ValidationError,match='inconsistent'):Estimate(**b)


def test_api_history_comparison_exports_and_guards(client):
    pid=create_project(client)['project_id'];base='/api/projects/'+pid
    b=estimate();response=client.post(base+'/material-costs',json=b)
    assert response.status_code==201,response.text
    first=response.json();b['name']='Alternative';b['lines'][0]['quote']['unit_price']=400
    second=client.post(base+'/material-costs',json=b).json()
    ids=[first['cost_id'],second['cost_id']]
    result=client.post(base+'/material-cost-comparisons',json={'cost_ids':ids}).json()
    assert result['results'][1]['difference_from_baseline']=='-201.60'
    assert result['results'][1]['material_total']=='4450.25'
    html=client.get(base+'/material-costs/'+ids[0]+'/report.html').text
    assert '4651.85' in html and '4233.60' in html
    b['name']='<img src=x onerror=alert(1)>';b['lines'][0]['name']='<script>unsafe</script>'
    escaped=client.post(base+'/material-costs',json=b).json()
    html=client.get(base+'/material-costs/'+escaped['cost_id']+'/report.html').text
    assert '<script>' not in html and '&lt;script&gt;' in html and '<img src=x' not in html
    other='/api/projects/'+create_project(client)['project_id']
    assert client.get(other+'/material-costs/'+ids[0]).status_code==409
    b['as_of']='2026-10-01';different=client.post(base+'/material-costs',json=b).json()
    assert client.post(base+'/material-cost-comparisons',json={'cost_ids':[ids[0],different['cost_id']]}).status_code==409
    client.headers.pop('X-CSRF-Token')
    assert client.post(base+'/material-costs',json=b).status_code==403
    client.cookies.clear();assert client.get(base+'/material-costs').status_code==401


def test_sources_withdrawal_tampering_and_project_staleness(client):
    pid=create_project(client)['project_id'];base='/api/projects/'+pid;domain=client.app.state.domain
    upload=client.post(base+'/files',files={'file':('quote.csv',b'price,420\n')}).json()
    ev=client.post(base+'/evidence',json={'type':'literature','name':'Synthetic quote','source_file':upload['file_id'],
        'source_locator':'row 1','authority':'Synthetic author','permission':'Test only','acquisition_method':'test','responsible_person':'auditor','status':'IMPORTED'}).json()
    b=estimate();b['lines'][0]['evidence_ids']=[ev['evidence_id']];b['import_file_id']=upload['file_id']
    record=client.post(base+'/material-costs',json=b).json();url=base+'/material-costs/'+record['cost_id']
    assert client.patch(base+'/evidence/'+ev['evidence_id'],json={'expected_revision':1,'review_state':'rejected','responsible_person':'auditor','review_note':'Rejected synthetic quote'}).status_code==200
    assert client.get(url).json()['result'] is None and client.post(base+'/material-costs',json=b).status_code==409
    assert domain.store.get('cost',record['cost_id'])['result']['material_total']=='4651.85'
    b['lines'][0]['evidence_ids']=[]
    fresh=client.post(base+'/material-costs',json=b).json()
    _,path=domain.file_record(pid,upload['file_id']);path.write_bytes(b'tampered')
    assert client.get(base+'/material-costs/'+fresh['cost_id']).json()['status']=='stale'
    assert client.post(base+'/material-costs',json=b).status_code==409
    b.pop('import_file_id');fresh=client.post(base+'/material-costs',json=b).json()
    project=domain.store.get('project',pid);domain.store.put('project',project,project['revision'])
    assert client.get(base+'/material-costs/'+fresh['cost_id']).json()['result'] is None


def test_zero_baseline_missing_and_large_valid_values(client):
    pid=create_project(client)['project_id'];base='/api/projects/'+pid;b=estimate()
    for row in b['lines']:row['quote']['unit_price']=0
    zero=client.post(base+'/material-costs',json=b).json();normal=client.post(base+'/material-costs',json=estimate()).json()
    assert client.post(base+'/material-cost-comparisons',json={'cost_ids':[zero['cost_id'],normal['cost_id']]}).json()['results'][1]['reduction_pct'] is None
    b['lines'][0]['quote']['unit_price']=None;missing=client.post(base+'/material-costs',json=b).json()
    assert client.post(base+'/material-cost-comparisons',json={'cost_ids':[zero['cost_id'],missing['cost_id']]}).status_code==409
    b=estimate();b['lines'][0]['measure'].update(length=1e7,width=1e7,height=1e7,count=1000000,dimension_unit='m',deduction=0)
    b['lines'][0]['quote']['unit_price']=1e12
    assert F(calculate(Estimate(**b))['material_total'])>10**30


def test_agent_reads_costs_without_inventing_prices_or_cross_project_access(client):
    from backend.agent import ToolRefusal
    pid=create_project(client)['project_id'];base='/api/projects/'+pid
    record=client.post(base+'/material-costs',json=estimate()).json();agent=client.app.state.agent
    assert agent.call(pid,'material_cost_list',{},False)[0]['cost_id']==record['cost_id']
    args={'material_cost_id':record['cost_id']}
    assert agent.call(pid,'material_cost_read',args,False)['result']['material_total']=='4651.85'
    other=create_project(client)['project_id']
    with pytest.raises(ToolRefusal):agent.call(other,'material_cost_read',args,False)
    with pytest.raises(ValueError):agent.call(pid,'material_cost_read',{**args,'price':0},False)


def test_report_keeps_quantity_units_and_unknown_values():
    from backend.material_cost import report
    b=estimate();b['lines'][0]['density_kg_m3']=None
    result=calculate(Estimate(**b))
    table=report({'input':b,'result':result}).split('</table>')[0]
    assert '<td>4 m3</td>' in table and '<td>4.2 m3</td>' in table
    assert '<td>— t</td>' in table and 'None' not in table

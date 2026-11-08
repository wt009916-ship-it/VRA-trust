import copy,gzip,json,shutil,sqlite3
from fractions import Fraction as F
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from backend import core,utility_comparison as calc
from test_api import create_project
from test_cad import upload


@pytest.fixture(scope='module')
def templates(tmp_path_factory):
    data=json.loads(gzip.decompress((Path(__file__).parents[1]/'fixtures/test/native_utility_projection.json.gz').read_bytes()));root=tmp_path_factory.mktemp('native-utility');records={}
    for c in data['cases']:
        rd=root/c['id'];(rd/'input').mkdir(parents=True);(rd/'output').mkdir()
        for rel,key in [('input/model.idf','model'),('input/weather.epw','weather'),('output/eplusout.mtd','mtd')]: (rd/rel).write_text(c[key],encoding='utf8')
        for name,text in c.get('bills',{}).items():(rd/name).write_text(text,encoding='utf8')
        with sqlite3.connect(rd/'output/eplusout.sql') as con:
            for table,d in c['tables'].items():
                con.execute('CREATE TABLE '+table+' ('+','.join('"'+x+'"' for x in d['columns'])+')');con.executemany('INSERT INTO '+table+' VALUES ('+','.join('?' for _ in d['columns'])+')',d['rows'])
        records[c['id']]={'root':rd,'fixture':c}
    return records,data['public_reference']


@pytest.fixture
def native(templates,tmp_path):
    rd=tmp_path/'native';shutil.copytree(templates[0]['2019']['root'],rd);return rd


def body(**changes):
    data={'name':'Utility reference','purpose':'Independent synthetic interval comparison, not calibrated','run_id':'run_'+'1'*32,'bill_evidence_id':'evidence_'+'2'*32,'meter':'Electricity:Facility','bill_nature':'synthetic','alignment':'exact_calendar','period_kind':'calendar_month','clock_source':'Declared local standard time, no DST','boundary_note':'Synthetic facility electricity, no generation, same controlled reference','max_abs_mbe_percent':5.,'max_cvrmse_percent':15.,'threshold_source':'User-declared test tolerances, not an automatic certification'};data.update(changes);return calc.ComparisonInput(**data)
def compare(rd,variant='matched',**changes):
    b=body(**changes);native=calc.native_meter(rd,b.meter);bills=calc.parse_bill(rd/(variant+'.csv'),native['selected_meter']['resource'],b.period_kind);return calc.compare(bills,native,b)
def mutate(rd,query):
    with sqlite3.connect(rd/'output/eplusout.sql') as con:con.execute(query)


@pytest.mark.parametrize('year',['2019','2020'])
@pytest.mark.parametrize('variant',['matched','bias','cancellation','zero'])
def test_native_year_and_frozen_independent_interval_statistics(templates,year,variant):
    data=templates[0][year];r=compare(data['root'],variant);expected=json.loads(data['fixture']['expected'][variant+'-expected'])
    for ours,theirs in [('mbe_percent','mbe_pct'),('rmse_kwh','rmse_kwh'),('cvrmse_percent','cvrmse_pct')]:
        value=expected[theirs]
        if value is None:assert r['statistics'][ours] is None
        else:assert r['statistics'][ours]==pytest.approx(float(value),abs=1e-9)
    assert r['coverage']['complete_year'] and r['coverage']['compared_hours']==(8784 if year=='2020' else 8760)
    assert r['status']=='compared_reference' and 'bill_is_reference_or_synthetic' in r['context_reasons']
    if variant=='zero':assert r['within_declared_tolerances'] is None
    if variant=='cancellation':assert abs(r['statistics']['mbe_percent'])<1e-9 and r['statistics']['rmse_kwh']==pytest.approx(90)


def test_official_synthetic_bill_facts_have_independent_arithmetic(templates,tmp_path):
    p=templates[1];actual=list(map(F,p['raw_kwh']));simulated=list(map(F,p['comparison_reference_not_native']));r=calc.statistics(actual,simulated)
    assert r['mbe_percent']==pytest.approx(10) and r['cvrmse_percent']==pytest.approx(float(p['expected']['cvrmse_pct']))
    assert p['data_nature']=='published_synthetic_reference' and len(p['cells'])==12


@pytest.mark.parametrize('variant',['gap','duplicate','power_unit','wrong_carrier','wrong_year'])
def test_reject_invalid_bill_periods_units_carrier_and_year(native,variant):
    with pytest.raises(core.ValidationError):compare(native,variant)


def test_explicit_calendar_pattern_retains_original_dates(native):
    r=compare(native,'wrong_year',alignment='calendar_pattern');assert r['rows'][0]['original']['start'].startswith('2021') and r['rows'][0]['mapped_start'].startswith('2019')
    assert 'month_day_mapping_not_same_year' in r['context_reasons'] and r['status']=='compared_reference'


@pytest.mark.parametrize('raw',['2019-01-01T00:30','2019-01-01T00:00Z','2019-W01-1','2019-02-29','2019-01-01T24:00','2019-01-01T00:00+08:00'])
def test_ambiguous_time_not_silently_shifted(raw):
    with pytest.raises(core.ValidationError):calc.local_time(raw)


@pytest.mark.parametrize('raw',['-1','NaN','Infinity','true','1e-200','1e60','1_000',''])
def test_invalid_energy_rejected(raw):
    with pytest.raises(core.ValidationError):calc.quantity(raw)


def test_native_dst_is_explicitly_rejected(templates):
    with pytest.raises(core.ValidationError,match='daylight saving'):calc.native_meter(templates[0]['2019-dst']['root'],'Electricity:Facility')


@pytest.mark.parametrize('query',[
 "UPDATE ReportDataDictionary SET Units='kW' WHERE Name='Electricity:Facility'",
 "UPDATE ReportDataDictionary SET Type='Avg' WHERE Name='Electricity:Facility'",
 "DELETE FROM ReportDataDictionary WHERE Name='Electricity:Facility'",
 "INSERT INTO ReportDataDictionary SELECT * FROM ReportDataDictionary WHERE Name='Electricity:Facility'",
 "DELETE FROM ReportData WHERE rowid=(SELECT MIN(rowid) FROM ReportData WHERE ReportDataDictionaryIndex=(SELECT ReportDataDictionaryIndex FROM ReportDataDictionary WHERE Name='Electricity:Facility'))",
 "INSERT INTO ReportData SELECT * FROM ReportData WHERE rowid=(SELECT MIN(rowid) FROM ReportData WHERE ReportDataDictionaryIndex=(SELECT ReportDataDictionaryIndex FROM ReportDataDictionary WHERE Name='Electricity:Facility'))",
 "UPDATE ReportData SET Value=-1 WHERE ReportDataDictionaryIndex=(SELECT ReportDataDictionaryIndex FROM ReportDataDictionary WHERE Name='Electricity:Facility')",
 "UPDATE Time SET Year=0",
 "UPDATE Simulations SET EnergyPlusVersion='EnergyPlus, Version 25.1.0'",
 "ALTER TABLE ReportData RENAME TO RawData;",
])
def test_native_corruption_has_no_annual_fallback(native,query):
    mutate(native,query)
    with pytest.raises(core.ValidationError):calc.native_meter(native,'Electricity:Facility')


def test_hourly_and_noncalendar_bill_boundaries(native):
    p=native/'hours.csv';p.write_text('start,end,energy,unit,carrier\n2019-01-02T01:00,2019-01-02T02:00,900,Wh,Electricity\n2019-01-02T02:00,2019-01-02T03:00,3240000,J,Electricity\n')
    n=calc.native_meter(native,'Electricity:Facility');r=calc.compare(calc.parse_bill(p,'Electricity','hour'),n,body(period_kind='hour'))
    assert r['statistics']['bill_total_kwh']==1.8 and abs(r['statistics']['mbe_percent'])<1e-9 and not r['coverage']['complete_year']
    with pytest.raises(core.ValidationError):calc.parse_bill(p,'Electricity','calendar_month')


def test_source_clock_mismatch_cannot_claim_calibration(native):
    p=native/'input/weather.epw';p.write_text(p.read_text().replace('2019,','2001,'));r=compare(native,bill_nature='measured')
    assert 'weather_years_differ_from_native_calendar' in r['context_reasons'] and r['status']=='compared_reference'


def test_facility_gross_electricity_with_generation_rejected(native):
    p=native/'input/model.idf';p.write_text(p.read_text()+'\nElectricLoadCenter:Distribution,Test;')
    with pytest.raises(core.ValidationError,match='gross facility'):compare(native)


def test_missing_mtd_and_mtd_binding_rejected(native):
    p=native/'output/eplusout.mtd';p.write_text(p.read_text().replace('OnMeter=Electricity:Facility [J]','OnMeter=Unknown:Facility [J]'))
    with pytest.raises(core.ValidationError,match='provenance'):compare(native)


def prepare(client,native,monkeypatch):
    # Protocol source seam only; fresh actual HTTP/native flow is separately required.
    pid=create_project(client)['project_id'];fid=upload(client,pid,'bill.csv',(native/'matched.csv').read_bytes())
    ev=client.post('/api/projects/'+pid+'/evidence',json={'type':'bill','name':'Synthetic bill','source_file':fid,'source_locator':'Frozen CSV all rows','authority':'Reference author','permission':'Synthetic reference','acquisition_method':'Independent declared schedules','responsible_person':'Author','status':'ASSUMED'}).json()
    ev=client.patch('/api/projects/'+pid+'/evidence/'+ev['evidence_id'],json={'expected_revision':ev['revision'],'review_state':'confirmed','responsible_person':'Author','review_note':'Reference only, not measured'}).json()
    service=client.app.state.utility_comparisons;snapshot={'run_id':'run_'+'1'*32,'sql_sha256':core.sha(native/'output/eplusout.sql')}
    def source(project,rid):
        if project!=pid:raise core.ValidationError('Foreign run')
        return copy.deepcopy(snapshot),native
    monkeypatch.setattr(service.sources,'source',source)
    return pid,ev,service,snapshot


def test_authenticated_comparison_exports_and_stale_sources(client,native,monkeypatch):
    pid,ev,service,snapshot=prepare(client,native,monkeypatch);b=body(bill_evidence_id=ev['evidence_id']).model_dump();base='/api/projects/'+pid+'/utility-comparisons'
    response=client.post(base,json=b);assert response.status_code==201,response.text;r=response.json();url=base+'/'+r['utility_id']
    assert client.get(base).json()['records'][0]['utility_id']==r['utility_id']
    assert client.get(url+'/comparison.csv').status_code==200 and 'native_kwh' in client.get(url+'/comparison.csv').text
    assert client.get(url+'/report.html').status_code==200
    with TestClient(client.app) as other:
        for u in [base,url,url+'/comparison.csv',url+'/report.html']:assert other.get(u).status_code==401
        account=other.post('/api/auth/register',json={'username':'utility_other','display_name':'Other','password':'Isolated-utility-other-2026'}).json();other.headers['X-CSRF-Token']=account['csrf_token']
        for u in [base,url,url+'/comparison.csv',url+'/report.html']:assert other.get(u).status_code==404
        assert other.post(base,json=b).status_code==404
    token=client.headers.pop('X-CSRF-Token');assert client.post(base,json=b).status_code==403;client.headers['X-CSRF-Token']=token
    assert client.post(base,json={**b,'bill_nature':'measured'}).status_code==409
    service.lock.acquire()
    try:assert client.post(base,json=b).status_code==429
    finally:service.lock.release()
    snapshot['sql_sha256']='changed';assert client.get(url).json()['result'] is None
    assert client.get(url+'/comparison.csv').status_code==409 and '全部比较数值已撤下' in client.get(url+'/report.html').text


def test_pending_or_withdrawn_bill_cannot_be_used(client,native,monkeypatch):
    pid,ev,service,_=prepare(client,native,monkeypatch);b=body(bill_evidence_id=ev['evidence_id']).model_dump();base='/api/projects/'+pid+'/utility-comparisons';r=client.post(base,json=b);assert r.status_code==201,r.text;uid=r.json()['utility_id']
    assert client.patch('/api/projects/'+pid+'/evidence/'+ev['evidence_id'],json={'expected_revision':ev['revision'],'review_state':'pending','responsible_person':'Author','review_note':'Withdraw current confirmation'}).status_code==200
    assert client.post(base,json=b).status_code==409 and client.get(base+'/'+uid).json()['result'] is None


def test_changes_during_comparison_never_persist_as_current(client,native,monkeypatch):
    pid,ev,service,snapshot=prepare(client,native,monkeypatch);original=calc.compare
    def changed(*args):
        result=original(*args);snapshot['sql_sha256']='changed';return result
    monkeypatch.setattr(calc,'compare',changed);r=client.post('/api/projects/'+pid+'/utility-comparisons',json=body(bill_evidence_id=ev['evidence_id']).model_dump())
    assert r.status_code==409 and service.store.list('utility',pid)==[]


def test_monthly_reference_mapping_cannot_hide_leap_day_difference(templates,native):
    bill=templates[0]['2020']['root']/'matched.csv';b=body(alignment='calendar_pattern')
    with pytest.raises(core.ValidationError,match='leap'):calc.compare(calc.parse_bill(bill,'Electricity','calendar_month'),calc.native_meter(native,b.meter),b)


def test_same_line_generator_definition_is_detected(native):
    p=native/'input/model.idf';p.write_text(p.read_text().rstrip()+'ElectricLoadCenter:Distribution,Test;')
    with pytest.raises(core.ValidationError,match='gross facility'):compare(native)


def test_excessive_native_energy_is_a_controlled_error(native):
    mutate(native,"UPDATE ReportData SET Value=1e300 WHERE ReportDataDictionaryIndex=(SELECT ReportDataDictionaryIndex FROM ReportDataDictionary WHERE Name='Electricity:Facility')")
    with pytest.raises(core.ValidationError,match='magnitude'):compare(native)


def test_thirteen_decimal_bill_values_are_preserved():
    assert calc.quantity('608.7272727272727')==F('608.7272727272727')


def test_calendar_upper_bound_is_controlled_api_rejection(client,native,monkeypatch):
    p=native/'matched.csv';p.write_text('start,end,energy,unit,carrier\n9999-12-01,9999-12-02,1,kWh,Electricity\n9999-12-02,9999-12-03,1,kWh,Electricity\n')
    pid,ev,service,_=prepare(client,native,monkeypatch)
    response=client.post('/api/projects/'+pid+'/utility-comparisons',json=body(bill_evidence_id=ev['evidence_id']).model_dump())
    assert response.status_code==409 and 'supported date range' in response.text
    assert service.store.list('utility',pid)==[]

import copy
import gzip
import json
from pathlib import Path
import shutil
import sqlite3
import pytest
from fastapi.testclient import TestClient
from backend import core, end_use
from backend.end_use_records import Ledgers
from test_api import create_project


@pytest.fixture(scope="module")
def native_template(tmp_path_factory):
    rd=tmp_path_factory.mktemp("enduse-native");(rd/'input').mkdir();(rd/'output').mkdir()
    data=json.loads(gzip.decompress((Path(__file__).parents[1]/'fixtures/test/native_hvac_enduse_projection.json.gz').read_bytes()))
    (rd/'input/model.idf').write_text(data['model_idf'],encoding='utf8');(rd/'output/eplusout.mtd').write_text(data['mtd'],encoding='utf8')
    with sqlite3.connect(rd/'output/eplusout.sql') as con:
        for table,d in data['tables'].items():
            con.execute('CREATE TABLE '+table+' ('+','.join('"'+c+'"' for c in d['columns'])+')')
            con.executemany('INSERT INTO '+table+' VALUES ('+','.join('?' for _ in d['columns'])+')',d['rows'])
    return rd


@pytest.fixture
def native(native_template,tmp_path):
    rd=tmp_path/'native';shutil.copytree(native_template,rd);return rd


def inspect(rd,mtd=True):return end_use.inspect(rd/'output/eplusout.sql',rd/'input/model.idf',rd/'output/eplusout.mtd' if mtd else None)
def mutate(rd,sql):
    with sqlite3.connect(rd/'output/eplusout.sql') as con:con.execute(sql)
def value(result,use,carrier='Electricity'):return next(r for r in result['rows'] if r['end_use']==use)['carriers'][carrier]


def test_native_mixed_annual_device_energy_and_ideal_delivery(native):
    r=inspect(native)
    assert r['hours']==8760 and r['area_m2']==50 and len(r['rows'])==14
    assert r['model']['ideal_systems']==['Ideal']
    # Independent controlled inputs: fan=.28*170/.68=70 W; DX=(1110+70)/3.4 W.
    assert value(r,'Fans')['hourly_meter_kwh']==pytest.approx(70*8760/1000,abs=1e-5)
    assert value(r,'Cooling')['hourly_meter_kwh']==pytest.approx((1110+70)/3.4*8760/1000,rel=.005)
    assert value(r,'Cooling','District Cooling')['hourly_meter_kwh']==pytest.approx(1730*8760/1000,rel=.005)
    assert value(r,'Heating')['hourly_meter_kwh']==0
    assert value(r,'Pumps')['hourly_meter_kwh'] is None
    assert value(r,'Pumps')['tabulated']['kwh']==0
    assert any('Fan Electric Energy' in x['variable'] for x in value(r,'Fans')['component_sources'])
    with sqlite3.connect(native/'output/eplusout.sql') as con:
        for row in r['rows']:
            for v in row['carriers'].values():
                loc=v['tabulated']['locator'];raw=con.execute('SELECT Value FROM TabularDataWithStrings WHERE TableName=? AND RowName=? AND ColumnName=?',(loc['table'],loc['row'],loc['column'])).fetchone()[0].strip();assert loc['raw_value']==raw


@pytest.mark.parametrize('query',[
 "DELETE FROM TabularDataWithStrings WHERE TableName='End Uses' AND RowName='Fans' AND ColumnName='Electricity'",
 "INSERT INTO TabularDataWithStrings SELECT * FROM TabularDataWithStrings WHERE TableName='End Uses' AND RowName='Fans' AND ColumnName='Electricity'",
 "UPDATE TabularDataWithStrings SET Units='kW' WHERE TableName='End Uses' AND RowName='Fans'",
 "UPDATE TabularDataWithStrings SET Value='NaN' WHERE TableName='End Uses' AND RowName='Fans' AND ColumnName='Electricity'",
 "UPDATE TabularDataWithStrings SET Value='-1' WHERE TableName='End Uses' AND RowName='Fans' AND ColumnName='Electricity'",
 "UPDATE TabularDataWithStrings SET Value='999' WHERE TableName='End Uses' AND RowName='Fans' AND ColumnName='Electricity'",
 "UPDATE TabularDataWithStrings SET RowName='Mystery' WHERE TableName='End Uses' AND RowName='Fans'",
 "UPDATE TabularDataWithStrings SET ColumnName='Unknown fuel' WHERE TableName='End Uses' AND ColumnName='Natural Gas'",
 "DELETE FROM ReportDataDictionary WHERE Name='Fans:Electricity'",
 "INSERT INTO ReportDataDictionary SELECT * FROM ReportDataDictionary WHERE Name='Fans:Electricity'",
 "UPDATE ReportDataDictionary SET Units='kWh' WHERE Name='Fans:Electricity'",
 "DELETE FROM ReportData WHERE rowid=(SELECT MIN(rowid) FROM ReportData)",
 "INSERT INTO ReportData SELECT * FROM ReportData WHERE rowid=(SELECT MIN(rowid) FROM ReportData)",
 "UPDATE ReportData SET Value=-1 WHERE rowid=(SELECT MIN(rowid) FROM ReportData)",
 "UPDATE ReportData SET Value=1e20 WHERE rowid=(SELECT MIN(rowid) FROM ReportData)",
 "UPDATE Simulations SET EnergyPlusVersion='EnergyPlus, Version 25.1.0'",
 "UPDATE Time SET Month=2,Day=29 WHERE TimeIndex=(SELECT MIN(TimeIndex) FROM Time)",
 "DROP TABLE ReportDataDictionary",
])
def test_corrupt_or_incompatible_native_data_rejected(native,query):
    mutate(native,query)
    with pytest.raises(core.ValidationError):inspect(native)


def test_without_mtd_only_rounded_table_claims(native):
    r=inspect(native,False);v=value(r,'Cooling');assert v['hourly_meter_kwh'] is None and v['meter_status']=='not_available' and not v['source_mapping_available']


def test_missing_requested_meter_is_not_zero(native):
    mutate(native,"DELETE FROM ReportDataDictionary WHERE Name='Heating:Electricity'")
    with pytest.raises(core.ValidationError,match='Requested meter missing'):inspect(native)


def test_hourly_meter_missing_its_source_mapping_rejected_even_zero(native):
    p=native/'output/eplusout.mtd';p.write_text(p.read_text().replace('OnMeter=Heating:Electricity [J]','OnMeter=Unrelated:Electricity [J]'))
    with pytest.raises(core.ValidationError,match='provenance'):inspect(native)


def test_unrequested_meter_stays_unknown_instead_of_fabricated(native):
    p=native/'input/model.idf';p.write_text(p.read_text().replace('Output:Meter,*,Hourly;','Output:Meter,*,Daily;'))
    mutate(native,"DELETE FROM ReportDataDictionary WHERE Name='Heating:Electricity'")
    assert value(inspect(native),'Heating')['hourly_meter_kwh'] is None


def test_rounding_display_precision_and_units():
    def row(raw,unit):return {'TableName':'End Uses','RowName':'Fans','ColumnName':'Electricity','Value':raw,'Units':unit}
    v=end_use.cell([row('0.00','GJ')],'End Uses','Fans','Electricity');assert v['kwh']==0 and v['rounding_half_width_kwh']==pytest.approx(1.38888888888889)
    for raw,unit in [('3.60','GJ'),('3600','MJ'),('3600000000','J'),('1000','kWh')]:assert end_use.cell([row(raw,unit)],'End Uses','Fans','Electricity')['kwh']==1000


def test_source_change_during_inspection_rejects(native,monkeypatch):
    original=end_use.model_info
    def change(path):
        data=original(path);path.write_text(path.read_text()+'! changed');return data
    monkeypatch.setattr(end_use,'model_info',change)
    with pytest.raises(core.ValidationError,match='Source changed'):inspect(native)


def test_ledger_api_authorization_capacity_integrity_and_stale(client,native,monkeypatch):
    # Protocol seam only; full engine/source binding covered by actual HTTP acceptance.
    pid=create_project(client)['project_id'];service=client.app.state.end_use_ledgers;rid='run_'+'1'*32
    snapshot={'run_id':rid,'model_sha256':core.sha(native/'input/model.idf'),'mtd_sha256':core.sha(native/'output/eplusout.mtd')}
    def source(project,run):
        if project!=pid:raise core.ValidationError('Wrong project')
        return copy.deepcopy(snapshot),native
    monkeypatch.setattr(service,'source',source);base='/api/projects/'+pid+'/end-use-ledgers';body={'name':'Test ledger','purpose':'Controlled simulated equipment reference, not measured','run_id':rid}
    r=client.post(base,json=body);assert r.status_code==201,r.text;record=r.json();url=base+'/'+record['enduse_id']
    assert len(client.get(base).json()['records'])==1 and client.get(url).json()['summary']['hours']==8760
    assert client.get(url+'/report.html').status_code==200
    with TestClient(client.app) as outsider:
        for route in [base,url,url+'/report.html']:assert outsider.get(route).status_code==401
        auth=outsider.post('/api/auth/register',json={'username':'enduse_other','display_name':'Other','password':'Isolated-other-enduse-2026'}).json();outsider.headers['X-CSRF-Token']=auth['csrf_token']
        for route in [base,url,url+'/report.html']:assert outsider.get(route).status_code==404
        assert outsider.post(base,json=body).status_code==404
    token=client.headers.pop('X-CSRF-Token');assert client.post(base,json=body).status_code==403;client.headers['X-CSRF-Token']=token
    service.lock.acquire()
    try:assert client.post(base,json=body).status_code==429
    finally:service.lock.release()
    snapshot['model_sha256']='changed';stale=client.get(url).json();assert stale['status']=='stale' and stale['summary'] is None
    assert 'hourly_meter_kwh' not in client.get(url+'/report.html').text
    snapshot['model_sha256']=record['source_run']['model_sha256']
    original=service.store.get
    def tampered(kind,ident):
        data=copy.deepcopy(original(kind,ident))
        if kind=='enduse':data['summary']['hours']=1
        return data
    monkeypatch.setattr(service.store,'get',tampered);assert client.get(url).json()['summary'] is None


def test_foreign_project_run_is_rejected_before_access(client,monkeypatch):
    service=Ledgers(client.app.state.domain)
    monkeypatch.setattr(service.store,'job',lambda _: {'project_id':'other'})
    monkeypatch.setattr(service.domain,'view',lambda _:pytest.fail('Foreign source must not be read'))
    with pytest.raises(core.ValidationError,match='another project'):service.source('mine','run_'+'2'*32)


def test_history_is_bounded_name_index_without_numeric_claims(client,monkeypatch):
    pid=create_project(client)['project_id'];service=client.app.state.end_use_ledgers
    for i in range(45):service.store.put('enduse',{'enduse_id':'enduse_'+format(i,'032x'),'project_id':pid,'input':{'name':str(i)},'created_at':'reference','summary':{'unverified':999}})
    monkeypatch.setattr(service,'view',lambda *args:pytest.fail('History must not load all numeric details'))
    route='/api/projects/'+pid+'/end-use-ledgers';ids=[];before=None
    for expected in (20,20,5):
        r=client.get(route,params={} if before is None else {'before':before});assert r.status_code==200
        data=r.json();assert len(data['records'])==expected and data['detail_status']=='not_checked' and '999' not in r.text
        ids.extend(x['enduse_id'] for x in data['records']);before=data['next_before']
    assert before is None and len(set(ids))==45 and ids[0]=='enduse_'+format(44,'032x')
    assert client.get(route+'?before=-1').status_code==422


def test_invalid_native_version_returns_controlled_http_error(client,native,monkeypatch):
    pid=create_project(client)['project_id'];service=client.app.state.end_use_ledgers
    monkeypatch.setattr(service,'source',lambda *_:({'mtd_sha256':'test'},native))
    mutate(native,"UPDATE Simulations SET EnergyPlusVersion='EnergyPlus, Version 25.1.0'")
    r=client.post('/api/projects/'+pid+'/end-use-ledgers',json={'name':'Invalid native','purpose':'Reject unsupported native version explicitly','run_id':'run_'+'3'*32})
    assert r.status_code==409 and '9.0.1' in r.text
    assert service.history(pid)['records']==[]

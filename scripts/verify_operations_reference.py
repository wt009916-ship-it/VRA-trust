"""Run a frozen, untrained rule against separately downloaded public LBNL slices.

Usage: python scripts/verify_operations_reference.py INPUT_DIRECTORY NEW_OUTPUT_DIRECTORY
No downloads, no threshold fitting, no private building data.
"""
import csv
import hashlib
import json
import sys
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from time import perf_counter

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from backend.api import create_app

CASES={
    'reference-FCU_FaultFree.csv':'a1d6d1ee468e6247777ed9639db5588e4eb22f957b56b4f1c802e1c57c34a15d',
    'reference-FCU_VLVStuck_Heating_0.csv':'3db4fd2b3e3e99aece98fbb1b99c35f7c34d3e8bd76d3ad1bfcedb1349b15f99'}
SOURCE='LBNL FDD Data Sets FCU; DOI 10.25984/1881324; inventory 2022-08-01; HVACSIM+ simulation; CC BY 4.0'


def body(fid):
    return dict(name='Frozen heating valve screening, first week 2018',file_id=fid,equipment='Simulated LBNL FCU',data_nature='simulation',source=SOURCE,
        time_column='Datetime',time_format='mm/dd/yyyy hh:mm',clock_basis='declared_local_clock',clock_source='LBNL simulation calendar; timezone not inferred',
        expected_interval_seconds=60,maximum_gap_seconds=90,
        channels=[dict(channel_id=key,column=col,name=col,unit=unit,source=SOURCE) for key,col,unit in [('cmd','FCU_HVLV_DM','ratio'),('valve','FCU_HVLV','ratio'),('temp','RM_TEMP','degF'),('power','FCU_WAT','W')]],
        rules=[dict(rule_id='heating_tracking',name='Heating command vs feedback',kind='difference',channel_id='cmd',other_channel_id='valve',unit='ratio',threshold=.1,
            minimum_duration_seconds=300,gate_channel_id='cmd',gate_minimum=.2,gate_unit='ratio',source='Predeclared audit heuristic: command >=0.2, absolute difference >0.1, observed span >=300 s. Not a published diagnostic threshold.')])


def oracle(path):
    # Rational CSV values, independently group selected indices, no application helper.
    with path.open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    selected=[];eligible=0
    for i,row in enumerate(rows):
        command=Fraction(row['FCU_HVLV_DM']);feedback=Fraction(row['FCU_HVLV'])
        if command>=Fraction(1,5):
            eligible+=1
            if abs(command-feedback)>Fraction(1,10):selected.append(i)
    groups=[]
    for i in selected:
        if groups and i==groups[-1][-1]+1:groups[-1].append(i)
        else:groups.append([i])
    events=[]
    for g in groups:
        begin=datetime.strptime(rows[g[0]]['Datetime'],'%m/%d/%Y %H:%M');end=datetime.strptime(rows[g[-1]]['Datetime'],'%m/%d/%Y %H:%M')
        if (end-begin).total_seconds()>=300:events.append((g[0]+2,g[-1]+2,(end-begin).total_seconds()))
    return dict(samples=len(rows),eligible=eligible,violating=len(selected),events=events)


def main():
    inputs,output=map(Path,sys.argv[1:3]);output.mkdir(parents=True,exist_ok=False)
    (output/'frozen-contract.json').write_text(json.dumps(body('file_'+'0'*32),indent=2),encoding='utf-8')
    results=[]
    with TestClient(create_app(output/'runtime',start_worker=False)) as client:
        auth=client.post('/api/auth/register',json=dict(username='reference_auditor',display_name='Isolated audit',password='Isolated-reference-only-2026!')).json()
        client.headers['X-CSRF-Token']=auth['csrf_token']
        project=client.post('/api/projects',json=dict(name='LBNL operational reference only',building=dict(use='reference',location='LBNL simulation',region='reference',area_m2=1))).json()
        base='/api/projects/'+project['project_id']
        for name,expected in CASES.items():
            raw=(inputs/name).read_bytes();assert hashlib.sha256(raw).hexdigest()==expected
            upload=client.post(base+'/files',files={'file':(name,raw)});assert upload.status_code==201,upload.text
            start=perf_counter();response=client.post(base+'/operations',json=body(upload.json()['file_id']));elapsed=perf_counter()-start
            assert response.status_code==201,response.text
            record=response.json();actual=record['result']['rules'][0];independent=oracle(inputs/name)
            assert actual['evaluated_samples']==independent['eligible'] and actual['violating_samples']==independent['violating']
            assert [(e['first_line'],e['last_line'],e['observed_span_seconds']) for e in actual['events']]==independent['events']
            assert not actual['events_truncated'] and record['result']['quality']['sample_count']==independent['samples']
            (output/(name+'.result.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
            results.append(dict(file=name,sha256=expected,independent=independent,event_count=actual['event_count'],excluded=actual['excluded_by_gate_samples'],unknown=actual['unknown_samples'],quality=record['result']['quality'],api_seconds=elapsed))
    (output/'summary.json').write_text(json.dumps(dict(source=SOURCE,results=results,interpretation='Two selected first-week simulations only; no population accuracy or field calibration claim.'),indent=2),encoding='utf-8')
    print(json.dumps([dict(file=r['file'],events=r['event_count'],eligible=r['independent']['eligible'],violating=r['independent']['violating'],seconds=r['api_seconds']) for r in results]))


if __name__=='__main__':main()

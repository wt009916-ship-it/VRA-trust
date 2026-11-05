"""Actual EnergyPlus reference/cancellation checks; never substitutes a mock engine."""
import argparse
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend import core
from backend import execution


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    root=Path(args.output).resolve();root.mkdir(parents=True,exist_ok=False)
    checked=[];runs=[]
    def check(name,value):
        if not value:raise AssertionError(name)
        checked.append(name)
    expected={'baseline':Decimal('57193.23'),'R1':Decimal('55715.19'),'R2':Decimal('55592.10')}
    for scheme in expected:
        rd=root/('run_'+uuid.uuid4().hex)
        result=core.run_simulation('reference_5zone',scheme,'reference_scenario',rd)
        check(scheme+' actual success',result['status']=='succeeded')
        _,manifest,_=core.read_validated(rd)
        check(scheme+' launch receipt',manifest['engine_calls_executed']==1 and manifest['execution_resources']['state']=='finished')
        # Independent Decimal arithmetic directly from original SQL cells.
        with sqlite3.connect((rd/'output/eplusout.sql').as_uri()+'?mode=ro',uri=True) as con:
            def cell(table,row,col,unit):
                rows=con.execute('SELECT Value,Units FROM TabularDataWithStrings WHERE ReportName=? AND ReportForString=? AND TableName=? AND RowName=? AND ColumnName=?',
                                 ('AnnualBuildingUtilityPerformanceSummary','Entire Facility',table,row,col)).fetchall()
                assert len(rows)==1 and rows[0][1]==unit
                return Decimal(rows[0][0].strip())
            energy=cell('Site and Source Energy','Total Site Energy','Total Energy','kWh')
            area=cell('Building Area','Total Building Area','Area','m2')
            electric=cell('End Uses','Total End Uses','Electricity','kWh')
            gas=cell('End Uses','Total End Uses','Natural Gas','kWh')
        check(scheme+' golden total',energy==expected[scheme])
        check(scheme+' carrier reconciliation',electric+gas==energy)
        check(scheme+' Decimal EUI',area==Decimal('927.20') and abs(Decimal(str(result['metrics']['eui_kwh_m2a']))-energy/area)<Decimal('1e-12'))
        runs.append({'run_dir':str(rd.relative_to(ROOT)),'manifest_sha256':core.sha(rd/'manifest.json'),'energy_kwh':str(energy),'area_m2':str(area)})
    rd=root/('run_'+uuid.uuid4().hex)
    def cancel_after_engine_output():
        path=rd/'stdout.log'
        return path.exists() and path.stat().st_size>0
    cancelled=core.run_simulation('reference_5zone','baseline','none',rd,cancel_check=cancel_after_engine_output)
    manifest=core.read_json(rd/'manifest.json')
    check('actual engine cancellation',cancelled['status']=='failed' and manifest['engine_calls_executed']==1)
    check('cancelled metrics unavailable',cancelled['metrics'] is None and cancelled['carbon'] is None)
    check('cancelled SQL not published',not (rd/'output/eplusout.sql').exists())
    recovery_dir=root/('run_'+uuid.uuid4().hex)
    recovery=core.run_simulation('reference_5zone','baseline','none',recovery_dir)
    check('recovery real annual run',recovery['status']=='succeeded' and Decimal(str(recovery['metrics']['annual_energy_kwh']))==expected['baseline'])
    old_hash=core.sha(rd/'manifest.json')
    try:core.run_simulation('reference_5zone','baseline','none',rd)
    except core.ValidationError:pass
    else:raise AssertionError('Existing evidence overwritten')
    check('cancelled history preserved',core.sha(rd/'manifest.json')==old_hash)
    core.write_json(root/'receipt.json',{'checked_at':core.now(),'checks':checked,'count':len(checked),'physics_hash':core.code_hash(),
        'runs':runs,'cancelled_run':str(rd.relative_to(ROOT)),'cancelled_receipt':manifest['execution_resources'],
        'recovery_run':str(recovery_dir.relative_to(ROOT)),'limits':execution.Policy().__dict__,
        'scope':'public reference only; no real-building calibration, production soak or filesystem/network sandbox'})
    print(json.dumps({'checks':len(checked),'status':'passed','receipt':str(root/'receipt.json')}))


if __name__=='__main__':main()

from pathlib import Path
from hashlib import sha256
from decimal import Decimal as D
import json,sys,time

REPO=Path('C:/Users/18483/AppData/Local/Temp/vra-drawing-components-20261108')
OUT=Path('C:/Users/18483/AppData/Local/Temp/vra-material-collection-public-20261108')
SOURCE=Path('D:/稀土agent-稀土制暖全流程/outputs/vra-m2-intake-20261108/Duplex_A_20110907.ifc')
sys.path.insert(0,str(REPO))
from backend import parser_runtime
gold=json.loads((OUT/'frozen-gold.json').read_text())
assert sha256(SOURCE.read_bytes()).hexdigest()==gold['source_sha256']
assert not (OUT/'public-results.json').exists()
results=[]
for case in gold['cases']:
    started=time.perf_counter()
    with parser_runtime.run('cad',SOURCE,options={'operation':'ifc_material_collection','product_ids':case['ids']}) as scope:
        result=json.loads((scope['work']/'result.json').read_text(encoding='utf-8'))
        limits=scope['resource_limits']
    errors=[]
    if case['expect_conflict']:
        if result.get('reason')!='cross_material_overlap_ownership_unresolved' or result.get('union_envelope_m3') is not None:errors.append('conflict_not_refused')
    elif result.get('status')!='measured':errors.append('not_measured:'+str(result.get('reason') or result.get('error')))
    else:
        for key in ('sum_layer_envelope_m3','union_envelope_m3','same_material_overlap_deduction_m3'):
            if abs(D(str(result[key]))-D(case[key]))>D(gold['absolute_tolerance_m3']):errors.append(key)
        byid={r['material_id']:r for r in result['materials']}
        if set(byid)!={r['material_id'] for r in case['materials']}:errors.append('material_identity')
        for expected in case['materials']:
            actual=byid.get(expected['material_id'],{})
            for key in ('source_sum_m3','union_envelope_m3'):
                if key not in actual or abs(D(str(actual[key]))-D(expected[key]))>D(gold['absolute_tolerance_m3']):errors.append(str(expected['material_id'])+':'+key)
    row={'ids':case['ids'],'seconds':time.perf_counter()-started,'passed':not errors,'errors':errors,'result':result,'resource_limits':limits}
    results.append(row)
    (OUT/('public-'+str(case['ids'][0])+'-'+str(len(case['ids']))+'.json')).write_text(json.dumps(row,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:row[k] for k in ('ids','seconds','passed','errors')}),flush=True)
receipt={'gold_sha256':sha256((OUT/'frozen-gold.json').read_bytes()).hexdigest(),'source_unchanged':sha256(SOURCE.read_bytes()).hexdigest()==gold['source_sha256'],
         'source_hashes':{name:sha256((REPO/'backend'/name).read_bytes()).hexdigest() for name in ('ifc_material_collection.py','ifc_layer_quantities.py','ifc_union.py','parser_worker.py','parser_runtime.py')},
         'cases':len(results),'passed':sum(r['passed'] for r in results),'score_change':0,'application_ui_integrated':False}
(OUT/'public-results.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8');print(json.dumps(receipt),flush=True)

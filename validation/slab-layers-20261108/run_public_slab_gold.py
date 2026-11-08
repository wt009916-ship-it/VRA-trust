from pathlib import Path
from decimal import Decimal as D
import sys,json,hashlib,time
R=Path('C:/Users/18483/AppData/Local/Temp/vra-drawing-components-20261108');sys.path.insert(0,str(R))
from backend import parser_runtime
OUT=Path('C:/Users/18483/AppData/Local/Temp/vra-slab-layers-20261108')
source=Path('D:/稀土agent-稀土制暖全流程/outputs/vra-m2-intake-20261108/Duplex_A_20110907.ifc')
gold=json.loads((OUT/'frozen-public-gold-v2.json').read_text());assert hashlib.sha256(source.read_bytes()).hexdigest()==gold['source_sha256']
results=[];started=time.monotonic()
for expected in gold['cases']:
    ident=expected['id']
    with parser_runtime.run('cad',source,options={'operation':'ifc_layers','product_id':ident}) as scope:
        record=json.loads((scope['work']/'result.json').read_text(encoding='utf-8'))
    (OUT/f'public-{ident}.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    result={'id':ident,'status':record.get('status'),'reason':record.get('reason'),'passed':False}
    if record.get('status')=='measured':
        actual={r['layer_id']:r for r in record['layers']}
        errors=[abs(D(str(actual[r['layer_id']]['envelope_volume_m3']))-D(r['volume_m3'])) for r in expected['layers']]
        result.update(max_layer_error_m3=str(max(errors)),passed=len(actual)==len(expected['layers']) and max(errors)<=D(gold['absolute_tolerance_m3']) and abs(D(str(record['host_volume_m3']))-D(expected['host_volume_m3']))<=D('1e-7'))
    results.append(result);print(json.dumps(result),flush=True)
with parser_runtime.run('cad',source,options={'operation':'ifc_layers','product_id':22492}) as scope:
    excluded=json.loads((scope['work']/'result.json').read_text(encoding='utf-8'))
(OUT/'public-excluded-roof.json').write_text(json.dumps(excluded,ensure_ascii=False,indent=2),encoding='utf-8')
receipt={'source_unchanged':hashlib.sha256(source.read_bytes()).hexdigest()==gold['source_sha256'],'gold_sha256':hashlib.sha256((OUT/'frozen-public-gold-v2.json').read_bytes()).hexdigest(),'rows':results,'elapsed_seconds':time.monotonic()-started,'passed':sum(r['passed'] for r in results),'total':len(results),'excluded_roof_status':excluded.get('status'),'excluded_roof_reason':excluded.get('reason')}
(OUT/'public-results.json').write_text(json.dumps(receipt,indent=2))
assert all(r['passed'] for r in results),receipt
assert excluded['status']=='unavailable' and excluded['layers']==[]
print(json.dumps({'passed':receipt['passed'],'total':receipt['total'],'elapsed_seconds':receipt['elapsed_seconds']}),flush=True)

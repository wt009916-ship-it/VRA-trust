import hashlib,json,sys
from pathlib import Path
out=Path(__file__).resolve().parent
oldpath=Path('C:/Users/18483/AppData/Local/Temp/vra-ifc-topology-optimized-a4df02a8ea02464d8eafbaff6de4b908/public/api.json')
new=json.loads((out/'public-windows-v1/api.json').read_text(encoding='utf-8'))
record={'previous_record_exists':oldpath.exists()}
if oldpath.exists():
    old=json.loads(oldpath.read_text(encoding='utf-8'));assert old['source']['hash']==new['source']['hash']
    byid={r['id']:r for r in old['result']['ifc_geometry']['objects']}
    changed=[]
    for row in new['result']['ifc_geometry']['objects']:
        prior=byid[row['id']]
        a,b=prior['volume_m3'],row['volume_m3']
        if prior['status']!=row['status'] or (a is None)!=(b is None) or (a is not None and abs(a-b)>1e-10):
            changed.append({'id':row['id'],'type':row['type'],'name':row['name'],'old_status':prior['status'],'new_status':row['status'],
                'old_volume_m3':a,'new_volume_m3':b,'old_topology':prior.get('topology'),'new_topology':row.get('topology')})
    record.update(source_sha256=new['source']['hash'],changes=changed,scope='Cross-version differences are diagnostics, not independent proof of complex geometry.')
with (out/'public-version-delta-v1.json').open('x',encoding='utf-8') as f:json.dump(record,f,ensure_ascii=False,indent=2)
print(json.dumps({'previous_record_exists':record['previous_record_exists'],'changes':[{'id':r['id'],'old':r['old_volume_m3'],'new':r['new_volume_m3']} for r in record.get('changes',[])]}))

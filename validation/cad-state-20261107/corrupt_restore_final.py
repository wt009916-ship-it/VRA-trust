"""Fault injection exclusively into this batch's isolated synthetic upload."""
import hashlib,json,sqlite3,sys
from pathlib import Path
out=Path(__file__).resolve().parent
runtime=json.loads((out/'ui-runtime-v1.json').read_text())
assert runtime['business_data_used'] is False
root=Path(runtime['data']).resolve()
assert root.name=='ui-data' and root.parent.name=='vra-hourly-candidate-820e5a5dc1a7402492fcbd1b73d0f4f7'
fid='file_c7c83ee99a074ba7ba43c08fa28d0716'
with sqlite3.connect(root/'vra.sqlite3') as con:
    row=con.execute("SELECT body FROM records WHERE kind='file' AND id=? ORDER BY revision DESC LIMIT 1",(fid,)).fetchone()
obj=json.loads(row[0]);path=(root/obj['path']).resolve()
assert path.is_relative_to(root)
original=(out/'browser-original-overlap-v1.ifc').read_bytes()
assert hashlib.sha256(original).hexdigest()==obj['hash']=='ff00c32e0cf8a89d114911c76d3f752627fe9ebf8430bd5fe339bddf7b46d277'
fault=b'CAD-state isolated synthetic fault injection'
if sys.argv[1]=='corrupt':
    assert path.read_bytes()==original
    path.write_bytes(fault)
elif sys.argv[1]=='restore':
    assert path.read_bytes()==fault
    path.write_bytes(original)
else:raise ValueError('Unknown operation')
print(json.dumps({'operation':sys.argv[1],'file_id':fid,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'original_business_files_touched':False}))

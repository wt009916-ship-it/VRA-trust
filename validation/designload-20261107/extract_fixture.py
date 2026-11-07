import hashlib,json,sqlite3
from pathlib import Path
repo=Path(__file__).resolve().parents[2]
probe=json.loads((Path(__file__).parent/'steady-probe-v1.json').read_text())
root=Path(probe['root']);sql=root/'output/eplusout.sql';model=root/'input.idf'
tables={}
with sqlite3.connect('file:'+sql.as_posix()+'?mode=ro',uri=True) as con:
 for table in ('Simulations','ZoneSizes','Zones','TabularDataWithStrings'):
  cursor=con.execute('SELECT * FROM '+table)
  tables[table]={'columns':[d[0] for d in cursor.description],'rows':cursor.fetchall()}
target=repo/'fixtures/test/native_zone_sizing_projection.json'
with target.open('x',encoding='utf-8') as f:json.dump({'source':'Self-authored synthetic steady box executed by EnergyPlus 9.0.1; projection is parser fixture, not new simulation',
 'sql_sha256':hashlib.sha256(sql.read_bytes()).hexdigest(),'model_sha256':hashlib.sha256(model.read_bytes()).hexdigest(),
 'model_idf':model.read_text(),'expected_W':probe['expected_W'],'tables':tables},f,indent=2)
print(json.dumps({'fixture':str(target),'bytes':target.stat().st_size}))

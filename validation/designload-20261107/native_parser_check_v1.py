import hashlib,json,sys
from pathlib import Path
repo=Path(__file__).resolve().parents[2];sys.path.insert(0,str(repo))
from backend.design_loads import inspect_design_loads
out=Path(__file__).parent
records=json.loads((out/'steady-matrix-v1.json').read_text())['records'];results=[]
for record in records:
 root=Path(record['root']);parsed=inspect_design_loads(root/'output/eplusout.sql',root/'input.idf')
 assert parsed['status']=='calculated_model_scenario',parsed.get('reason')
 assert parsed['tabular_crosscheck']=='matched_W_cells'
 for native in record['sizes']:
  row=next(r for r in parsed['rows'] if r['load_type']==native['LoadType'])
  assert row['calculated_sensible_load_W']==native['CalcDesLoad']
  assert row['user_adjusted_sensible_load_W']==native['UserDesLoad']
 results.append({'id':record['spec']['id'],'receipt':parsed})
with (out/'native-parser-v1.json').open('x') as stream:json.dump({'scope':'Reparse five earlier fresh native variant runs; not five new simulations',
 'parser_sha256':hashlib.sha256((repo/'backend/design_loads.py').read_bytes()).hexdigest(),'results':results},stream,indent=2)
print(json.dumps({'native_cases':len(results),'load_rows':sum(len(r['receipt']['rows']) for r in results)}))

from pathlib import Path
import sys, uuid, json
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.core import run_simulation, compare_runs, write_json
from backend.service import report_html
dirs=[]
for scheme in ['baseline','R1','R2']:
    rd=ROOT/'runs'/('run_'+uuid.uuid4().hex)
    r=run_simulation('reference_5zone',scheme,'reference_scenario',rd)
    print(scheme, r['status'], r.get('metrics',{}), r.get('error'), flush=True)
    if r['status']!='succeeded':raise SystemExit(1)
    dirs.append(rd)
summary=compare_runs(dirs)
write_json(ROOT/'validation/reference_comparison.json',summary)
(ROOT/'validation/reference_report.html').write_text(report_html(summary),encoding='utf-8')
print('Published reference runs:',[p.name for p in dirs])

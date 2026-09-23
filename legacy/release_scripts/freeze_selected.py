"""Publish an explicitly selected, already validated comparison; no new simulation."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend import core
from backend.service import report_html,run_dir
if __name__=='__main__':
    if len(sys.argv)<3:raise SystemExit('Usage: python scripts/freeze_selected.py baseline_run retrofit_run [retrofit_run]')
    data=core.compare_runs([run_dir(r) for r in sys.argv[1:]])
    core.write_json(ROOT/'validation/reference_comparison.json',data)
    (ROOT/'validation/reference_report.html').write_text(report_html(data),encoding='utf-8')
    print('Frozen:',[r['run_id'] for r in data['results']])

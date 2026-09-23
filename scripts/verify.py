"""Repeat local checks; --engine also creates fresh physical reference runs."""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--engine',action='store_true');args=parser.parse_args()
    out=ROOT/'validation/final';out.mkdir(parents=True,exist_ok=True)
    node=shutil.which('node')
    if not node:raise SystemExit('Node.js required')
    commands=[]
    if args.engine:
        commands += [('native_reference',[sys.executable,'-X','utf8','scripts/run_reference.py'],ROOT),('golden_path',[sys.executable,'-X','utf8','scripts/golden_path.py'],ROOT)]
    commands += [('backend_tests',[sys.executable,'-m','pytest','-q'],ROOT),('backend_lint',[sys.executable,'-m','ruff','check','backend','tests/test_api.py','tests/test_parser_contract.py','scripts/golden_path.py','scripts/replay.py'],ROOT),('frontend_lint',[node,'scripts/check_frontend.mjs'],ROOT),('frontend_tests',[node,'--test','frontend/tests/truth.test.js','frontend/legacy/tests/adapter.test.js'],ROOT),('frontend_build',[node,'node_modules/vite/bin/vite.js','build'],ROOT/'frontend'),('contract_export',[sys.executable,'scripts/export_contract.py'],ROOT)]
    checks=[]
    for name,command,cwd in commands:
        cp=subprocess.run(command,cwd=cwd,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=600)
        (out/(name+'.log')).write_text(cp.stdout+'\n'+cp.stderr,encoding='utf-8')
        checks.append({'name':name,'passed':cp.returncode==0,'exit_code':cp.returncode})
        print(name,'PASS' if cp.returncode==0 else 'FAIL',flush=True)
    (out/'checks.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
    if not all(c['passed'] for c in checks):raise SystemExit(1)

if __name__=='__main__':main()

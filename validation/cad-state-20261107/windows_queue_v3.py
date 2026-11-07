"""Avoid overlapping two full Windows native suites."""
import subprocess,sys,time
from pathlib import Path
out=Path(__file__).resolve().parent
deadline=time.monotonic()+3600
while not (out/'windows-checks-v1.json').exists():
    if time.monotonic()>deadline:raise TimeoutError('Prior frozen Windows suite did not finish')
    time.sleep(2)
raise SystemExit(subprocess.run([sys.executable,'-B','-X','utf8',str(out/'windows_candidate_v3.py')]).returncode)

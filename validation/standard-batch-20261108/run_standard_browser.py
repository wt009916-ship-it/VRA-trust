from pathlib import Path
import subprocess
D=Path(__file__).parent;R=Path('C:/Users/18483/AppData/Local/Temp/vra-agent-read-execution-20261108');V=R/'validation/standard-batch-20261108'
log=V/'browser-first.log';assert not log.exists()
r=subprocess.run(['node','C:/Users/18483/AppData/Local/npm-cache/_npx/31e32ef8478fbf80/node_modules/@playwright/cli/playwright-cli.js','-s=vra-standard-batch','run-code','--filename',str(D/'check_standard_browser.js')],cwd=R,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
log.write_bytes(r.stdout);print(r.stdout.decode('utf-8')[:14000]);raise SystemExit(r.returncode)

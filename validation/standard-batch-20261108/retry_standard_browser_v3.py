from pathlib import Path
import shutil,subprocess
D=Path(__file__).parent;R=Path('C:/Users/18483/AppData/Local/Temp/vra-agent-read-execution-20261108');V=R/'validation/standard-batch-20261108'
old=D/'check_standard_browser_v2.js';shutil.copyfile(old,V/'browser-check-second.js')
s=old.read_text(encoding='utf-8');needle=" const result=page.locator('#norm-result');"
assert s.count(needle)==1
s=s.replace(needle," while(await rows.count()>2)await rows.last().getByRole('button',{name:'移除查询条款',exact:true}).click();\n"+needle)
p=D/'check_standard_browser_v3.js';assert not p.exists();p.write_text(s,encoding='utf-8')
log=V/'browser-third.log';assert not log.exists()
r=subprocess.run(['node','C:/Users/18483/AppData/Local/npm-cache/_npx/31e32ef8478fbf80/node_modules/@playwright/cli/playwright-cli.js','-s=vra-standard-batch','run-code','--filename',str(p)],cwd=R,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
log.write_bytes(r.stdout);print(r.stdout.decode('utf-8')[:21000]);raise SystemExit(r.returncode)

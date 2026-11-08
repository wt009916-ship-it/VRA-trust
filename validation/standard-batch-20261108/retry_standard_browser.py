from pathlib import Path
import shutil,subprocess
D=Path(__file__).parent;R=Path('C:/Users/18483/AppData/Local/Temp/vra-agent-read-execution-20261108');V=R/'validation/standard-batch-20261108'
old=D/'check_standard_browser.js';shutil.copyfile(old,V/'browser-check-first.js')
s=old.read_text(encoding='utf-8').replace('async(page)=>{','''async(page)=>{
 await page.getByRole('navigation',{name:'项目工作视图'}).getByRole('button',{name:'工作台',exact:true}).click();
 await page.getByRole('button',{name:'规范资料',exact:true}).click();
 await page.getByRole('combobox',{name:'查询方式',exact:true}).selectOption('batch');''',1)
s=s.replace("const base='/api/projects/'+partial.project_id;", "const base=new URL('/api/projects/'+partial.project_id,page.url()).href;")
s=s.replace("page.request.get('/api/auth/me')", "page.request.get(new URL('/api/auth/me',page.url()).href)")
script=D/'check_standard_browser_v2.js';assert not script.exists();script.write_text(s,encoding='utf-8')
log=V/'browser-second.log';assert not log.exists()
r=subprocess.run(['node','C:/Users/18483/AppData/Local/npm-cache/_npx/31e32ef8478fbf80/node_modules/@playwright/cli/playwright-cli.js','-s=vra-standard-batch','run-code','--filename',str(script)],cwd=R,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
log.write_bytes(r.stdout);print(r.stdout.decode('utf-8')[:18000]);raise SystemExit(r.returncode)

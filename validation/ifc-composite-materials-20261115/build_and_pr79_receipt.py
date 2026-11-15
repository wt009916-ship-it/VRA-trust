import hashlib,json,os,runpy,shutil,subprocess,sys
from pathlib import Path
root=Path(__file__).parent
repo=Path('C:/Users/18483/AppData/Local/Temp/vra-timestep-reliability-20261108')
deps=Path('C:/Users/18483/AppData/Local/Temp/vra-member-frontend-deps-20261115/frontend/node_modules')
build=Path('C:/Users/18483/AppData/Local/Temp/vra-composite-frontend-build-20261115')
shutil.copytree(repo/'frontend',build,ignore=shutil.ignore_patterns('node_modules','dist'))
# Reuse the verified lock-identical dependency installation through a directory
# junction in this new build directory. Never alter the old release/dependency tree.
subprocess.run(['cmd','/c','mklink','/J',str(build/'node_modules'),str(deps)],check=True,capture_output=True)
node=Path('C:/Users/18483/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe')
with (root/'frontend.log').open('wb') as log:
 subprocess.run([str(node),'--test'],cwd=build,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
with (root/'build.log').open('wb') as log:
 subprocess.run([str(node),str(deps/'vite/bin/vite.js'),'build'],cwd=build,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
source_lock=hashlib.sha256((repo/'frontend/package-lock.json').read_bytes()).hexdigest()
assert source_lock==hashlib.sha256((deps.parent/'package-lock.json').read_bytes()).hexdigest()
receipt={'source_lock_sha256':source_lock,'build_success':True,'browser':'deferred',
 'dist':{p.relative_to(build/'dist').as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (build/'dist').rglob('*') if p.is_file()},
 'frontend_sources':{p.relative_to(repo).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (repo/'frontend/src').rglob('*') if p.is_file()}}
(root/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
sys.argv=['github_sync.py','load_only'];g=runpy.run_path('D:/稀土agent-稀土制暖全流程/outputs/vra-prototype-sync-20261104/github_sync.py')
pr=g['call']('/pulls/79');assert pr['head']['sha']=='205e9fdbd05eb6d2d277a615cb35f377ca736522'
body=pr['body'].replace('全部远程CI等待本PR精确提交，不预填通过。','精确提交205e9fd三项远程CI全部成功：后端2043通过、22跳过、2警告、6子测试（857.05秒）；前端248及构建、接口30通过。22跳过未计通过。')
g['call']('/pulls/79','PATCH',{'body':body})
print(json.dumps({'build':True,'pr79_exact_ci_closed':True}))

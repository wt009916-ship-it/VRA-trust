import hashlib,json,shutil,subprocess
from pathlib import Path
root=Path(__file__).parent;repo=Path('C:/Users/18483/AppData/Local/Temp/vra-timestep-reliability-20261108')
deps=Path('C:/Users/18483/AppData/Local/Temp/vra-member-frontend-deps-20261115/frontend/node_modules')
dest=root/'frontend-build';assert not dest.exists()
lock=hashlib.sha256((repo/'frontend/package-lock.json').read_bytes()).hexdigest()
assert lock==hashlib.sha256((deps.parent/'package-lock.json').read_bytes()).hexdigest()=='1864735a72a41a3f121692313609b91697c5162c9183bc14b6023b40902905c7'
shutil.copytree(repo/'frontend',dest,ignore=shutil.ignore_patterns('node_modules','dist'))
subprocess.run(['cmd','/c','mklink','/J',str(dest/'node_modules'),str(deps)],check=True,capture_output=True)
node=Path('C:/Users/18483/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe')
with (root/'build.log').open('wb') as log:subprocess.run([str(node),str(deps/'vite/bin/vite.js'),'build'],cwd=dest,stdout=log,stderr=subprocess.STDOUT,check=True)
receipt={'source_lock_sha256':lock,'build_success':True,'browser':'deferred_by_user','files':{p.relative_to(dest/'dist').as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (dest/'dist').rglob('*') if p.is_file()}}
(root/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print('Build successful; browser not exercised')

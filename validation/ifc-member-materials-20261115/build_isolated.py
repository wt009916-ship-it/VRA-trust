import base64,hashlib,json,os,shutil,subprocess,tarfile,urllib.request
from pathlib import Path
repo=Path('C:/Users/18483/AppData/Local/Temp/vra-timestep-reliability-20261108')
root=Path('C:/Users/18483/AppData/Local/Temp/vra-member-frontend-deps-20261115');root.mkdir(exist_ok=False)
node=Path('C:/Users/18483/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe')
metadata=json.load(urllib.request.urlopen('https://registry.npmjs.org/npm/11.6.2',timeout=30))
url=metadata['dist']['tarball'];assert url=='https://registry.npmjs.org/npm/-/npm-11.6.2.tgz'
raw=urllib.request.urlopen(url,timeout=30).read(20000000);algorithm,expected=metadata['dist']['integrity'].split('-',1)
assert algorithm=='sha512' and base64.b64encode(hashlib.sha512(raw).digest()).decode()==expected
archive=root/'npm.tgz';archive.write_bytes(raw)
with tarfile.open(archive) as tf:tf.extractall(root/'npm',filter='data')
build=root/'frontend'
shutil.copytree(repo/'frontend',build,ignore=shutil.ignore_patterns('node_modules','dist'))
env={**os.environ,'PATH':str(node.parent)+os.pathsep+os.environ.get('PATH','')}
out=Path(__file__).parent
with (out/'dependency-repair.log').open('wb') as log:
 subprocess.run([str(node),str(root/'npm/package/bin/npm-cli.js'),'ci','--no-audit','--no-fund'],cwd=build,env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=240)
with (out/'build-repaired.log').open('wb') as log:
 subprocess.run([str(node),str(build/'node_modules/vite/bin/vite.js'),'build'],cwd=build,env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
receipt={'source_lock_sha256':hashlib.sha256((repo/'frontend/package-lock.json').read_bytes()).hexdigest(),
 'isolated_lock_sha256':hashlib.sha256((build/'package-lock.json').read_bytes()).hexdigest(),
 'npm_version':'11.6.2','npm_archive_verified_integrity':metadata['dist']['integrity'],
 'build_success':True,'original_dependency_directory_modified':False,
 'files':{p.relative_to(build/'dist').as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (build/'dist').rglob('*') if p.is_file()}}
(out/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt))

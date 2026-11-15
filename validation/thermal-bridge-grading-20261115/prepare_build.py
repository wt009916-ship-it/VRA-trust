import hashlib,json,shutil
from pathlib import Path
root=Path(__file__).parent
repo=Path('D:/稀土agent-稀土制暖全流程/.codex_work/vra-resource-leveling-20261115')
deps=Path('C:/Users/18483/AppData/Local/Temp/vra-member-frontend-deps-20261115/frontend')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(repo/'frontend/package-lock.json')==sha(deps/'package-lock.json')
dest=root/'frontend-build'
shutil.copytree(repo/'frontend',dest,ignore=shutil.ignore_patterns('node_modules','dist','.vite'))
(root/'build-preparation.json').write_text(json.dumps({'lock_sha256':sha(repo/'frontend/package-lock.json'),'dependency_directory':str(deps/'node_modules'),'build_directory':str(dest)},indent=2)+'\n')
print('Copied isolated frontend; dependency lock matches.')

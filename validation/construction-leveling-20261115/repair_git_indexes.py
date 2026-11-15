"""Rebuild missing indexes for existing immutable packs; no fetch, ref change or history rewrite."""
import hashlib,json,subprocess
from pathlib import Path
root=Path(__file__).parent
repo=Path('C:/Users/18483/AppData/Local/Temp/vra-timestep-reliability-20261108')
expected=Path('C:/Users/18483/AppData/Local/Temp/vra-design-release-a773af75c60e4c7db80c7091a498175b/.git').resolve()
def git(*args):return subprocess.check_output(['git','-c','gc.auto=0','-c','maintenance.auto=false',*args],cwd=repo,text=True,encoding='utf-8').strip()
common=Path(git('rev-parse','--git-common-dir')).resolve();assert common==expected
head=git('rev-parse','HEAD');assert head=='49306007f6b7c886f442f307ddc82ffec4dcd00e'
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def missing():return [x for x in git('rev-list','--objects','HEAD','--missing=print').splitlines() if x.startswith('?')]
receipt={'head_before':head,'missing_objects_before':len(missing()),'scope':'Only missing .idx for existing verified packs; no object rewriting or fetch','packs':[]}
for p in sorted((common/'objects/pack').glob('*.pack')):
 assert p.resolve().is_relative_to(common/'objects/pack')
 if p.with_suffix('.idx').exists():continue
 original=sha(p)
 output=git('index-pack',str(p))
 assert output==p.stem.removeprefix('pack-'),(p.name,output)
 assert sha(p)==original
 receipt['packs'].append({'file':p.name,'bytes':p.stat().st_size,'pack_sha256':original,'index_sha256':sha(p.with_suffix('.idx')),'verified_pack_id':output})
receipt['head_after']=git('rev-parse','HEAD');receipt['missing_objects_after']=len(missing())
assert receipt['head_after']==head and receipt['missing_objects_after']==0
with (root/'git-fsck.log').open('wb') as log:
 result=subprocess.run(['git','fsck','--full','--no-reflogs'],cwd=repo,stdout=log,stderr=subprocess.STDOUT)
receipt['fsck_exit']=result.returncode
(root/'git-index-repair.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
assert result.returncode==0
print(json.dumps({'reindexed_packs':len(receipt['packs']),'missing_before':receipt['missing_objects_before'],'missing_after':receipt['missing_objects_after'],'fsck_exit':result.returncode,'head_unchanged':True}))

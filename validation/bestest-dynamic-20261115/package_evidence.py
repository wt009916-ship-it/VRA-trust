"""Copy only audit-owned receipts/scripts; omit raw licensed inputs and private runtime."""
import gzip,hashlib,json,shutil
from pathlib import Path
BASE=Path(__file__).parent
ROOT=Path('D:/稀土agent-稀土制暖全流程/.codex_work/vra-resource-leveling-20261115')
DEST=ROOT/'validation/bestest-dynamic-20261115'
DEST.mkdir(exist_ok=False)
def copy(relative,compress=False):
    source=BASE/relative
    if not source.is_file():return
    target=DEST/(relative+('.gz' if compress else ''));target.parent.mkdir(parents=True,exist_ok=True)
    data=source.read_bytes();target.write_bytes(gzip.compress(data,mtime=0) if compress else data)
for name in ['PLAN.md','acquisition.json','reference-frozen-v2.json','schema-audit.json','input-preparation-v4.json','existing-preflight.json','assessment.json','paired-observations.json','historical-energyplus-diagnostic.json','pytest-weather.log','frontend-tests.log','frontend-build.log','frontend-build-v2.log','frontend-source-hashes.json','summarize.log']:
    copy(name)
for path in BASE.glob('*.py'):copy(path.name)
for name in ['workbook-inspection.log','freeze-reference-v1.log','freeze-reference-v2.log','native-first.log','native-compat-v2.log','native-compatible-first.log','native-v4-first.log','native-v4-remaining.log','http-baseline.log','http-integrated-v1.log']:
    copy(name)
for dirname in ['native-compat-v2','native-compatible-first','native-v4-first','native-v4-remaining']:
    for path in (BASE/dirname).rglob('*'):
        if path.is_file() and path.suffix in ['.json','.err','.end','.log']:copy(path.relative_to(BASE).as_posix())
for dirname in ['http-baseline','http-integrated-v1']:
    for path in (BASE/dirname).iterdir():
        if path.suffix in ['.json','.log','.txt','.html']:
            copy(path.relative_to(BASE).as_posix(),path.suffix=='.html' or (path.suffix=='.json' and path.stat().st_size>50000))
ci=BASE.parent/'thermal-bridge-grading-20261115/post-ci'
target=DEST/'predecessor-pr83-ci';target.mkdir()
for name in ['ci-receipt.json','backend.log','frontend.log','api.log']:shutil.copy2(ci/name,target/name)
manifest={p.relative_to(DEST).as_posix():{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in DEST.rglob('*') if p.is_file()}
(DEST/'manifest.json').write_text(json.dumps({'files':manifest,'scope':'Own source, observations, receipts and derived factual reference values. No original IDF/EPW/XLSX, native SQL, accounts, session tokens or private runtime included.'},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'files':len(manifest),'bytes':sum(v['bytes'] for v in manifest.values()),'manifest':str(DEST/'manifest.json')}))

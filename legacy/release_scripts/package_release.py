"""Local release archive; excludes environments, credentials and obsolete runs."""
import sys, zipfile, json, hashlib, shutil, re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend import core

def main():
    checks=core.read_json(ROOT/'validation/verification.json')
    if not all(c['passed'] for c in checks['checks']):raise SystemExit('Verification failed')
    summary=core.read_json(ROOT/'validation/reference_comparison.json')
    selected={r['run_id'] for r in summary['results']}
    for rid in selected:
        r,_,_=core.read_validated(ROOT/'runs'/rid)
        if r['status']!='succeeded':raise SystemExit('Stale release evidence')
    # Preserve third-party license notices with the built browser distribution.
    deps=ROOT/'frontend/node_modules';notices=ROOT/'third_party_notices'
    if deps.is_dir():
        for p in deps.rglob('*'):
            if p.is_file() and p.name.lower().startswith(('license','copying','notice')) and p.stat().st_size<2_000_000:
                rel=p.relative_to(deps);dest=notices/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
    files=[];omissions=[]
    for p in ROOT.rglob('*'):
        if not p.is_file():continue
        rel=p.relative_to(ROOT);parts=rel.parts
        if any(x in {'node_modules','__pycache__','.git','.venv','.venv2'} for x in parts):continue
        if p.suffix.lower() in {'.pyc','.zip'} or p.name.startswith('.env'):continue
        if parts[0]=='runs' and (len(parts)<3 or parts[1] not in selected):continue
        if parts[0]=='legacy':
            if p.suffix not in {'.py','.md','.txt'} or any(x in {'run_output','batch_run_output','output','data','history_report','assets'} for x in parts):continue
        if p.name=='release_files.json':continue
        if p.suffix in {'.py','.js','.json','.md','.txt'} and p.stat().st_size<5_000_000:
            text=p.read_text(encoding='utf-8',errors='replace')
            if re.search(r'\bsk-[A-Za-z0-9_-]{24,}',text):
                if parts[0]=='legacy':omissions.append(rel.as_posix());continue
                raise SystemExit('Potential credential in release: '+rel.as_posix())
        files.append(p)
    manifest={'created_at':core.now(),'selected_runs':sorted(selected),'omitted_legacy_potential_credentials':omissions,'files':[{'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':core.sha(p)} for p in sorted(files)]}
    core.write_json(ROOT/'release_files.json',manifest);files.append(ROOT/'release_files.json')
    dest=ROOT.parent/'稀土智暖_三人交付修订整合版_20260923.zip'
    with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in files:z.write(p,Path(ROOT.name)/p.relative_to(ROOT))
    with zipfile.ZipFile(dest) as z:
        if z.testzip() is not None:raise SystemExit('Archive verification failed')
    digest=core.sha(dest)
    dest.with_suffix('.sha256.txt').write_text(digest+'  '+dest.name+'\n',encoding='utf-8')
    print(json.dumps({'archive':str(dest),'bytes':dest.stat().st_size,'files':len(files),'sha256':digest,'selected_runs':sorted(selected)},ensure_ascii=True,indent=2))
if __name__=='__main__':main()

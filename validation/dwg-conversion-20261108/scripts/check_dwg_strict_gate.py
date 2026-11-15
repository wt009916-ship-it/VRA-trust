from pathlib import Path
import json, sys, tarfile, zipfile, shutil
root=Path('C:/Users/18483/AppData/Local/Temp/vra-libredwg-014-reference-20261108')
repo=Path('C:/Users/18483/AppData/Local/Temp/vra-dwg-conversion-20261108')
sys.path.insert(0,str(repo))
from backend.native_windows import staging
from backend.native_ownership import owned_temporary
from backend.native_staging import copy_file
from backend import execution
import ezdxf
out=root/'strict-gate';out.mkdir(exist_ok=False)
cases=['example_r14','example_2000','example_2004']
(out/'frozen.json').write_text(json.dumps({'additional_cases':cases,'gate':'ezdxf readfile plus audit: no errors and no fixes; default conversion, no recovery or format downgrade','reason':'previous nine preflight outputs did not run audit; all require repairs'}))
results=[]
for p in (root/'decode-reference').glob('*/output.dxf'):
    a=ezdxf.readfile(p).audit()
    results.append({'case':p.parent.name,'phase':'prior output audit, no repeated conversion','errors':len(a.errors),'fixes':len(a.fixes),'issues':[{'code':int(f.code),'message':f.message} for f in a.fixes]})
(out/'results.json').write_text(json.dumps(results,indent=2))
for name in cases:
    target=out/name;target.mkdir()
    with tarfile.open(root/'libredwg-0.14.tar.xz') as t:
        (target/'input.dwg').write_bytes(t.extractfile('libredwg-0.14/test/test-data/'+name+'.dwg').read())
    result={'case':name}
    try:
        with staging() as s,owned_temporary(root) as control:
            rt=s['root']/'runtime';rt.mkdir()
            with zipfile.ZipFile(root/'libredwg-0.14-win64.zip') as z:
                for n in ['dwg2dxf.exe','libredwg-0.dll','libiconv-2.dll','libpcre2-8-0.dll','libpcre2-16-0.dll']:(rt/n).write_bytes(z.read(n))
            copy_file(target/'input.dwg',s['root']/'input.dwg',10*1024**2)
            logs=control/'logs';logs.mkdir()
            try:
                result['receipt']=execution.supervise([rt/'dwg2dxf.exe','-o',s['work']/'output.dxf',s['root']/'input.dwg'],control,logs,execution.Policy(memory_bytes=512*1024**2,cpu_seconds=20,output_bytes=16*1024**2,output_files=32,log_bytes=256*1024),30,output=s['work'],isolation={'sid':s['sid'],'work':str(s['work'])},extra_output_roots=[s['profile_root']])
                shutil.copyfile(s['work']/'output.dxf',target/'output.dxf')
            finally:
                for p in logs.glob('*.log'):shutil.copyfile(p,target/p.name)
        a=ezdxf.readfile(target/'output.dxf').audit()
        result.update(errors=len(a.errors),fixes=len(a.fixes),issues=[{'code':int(f.code),'message':f.message} for f in a.fixes][:30])
    except Exception as e:result['error']=str(e)
    results.append(result);(out/'results.json').write_text(json.dumps(results,indent=2));print(json.dumps({k:v for k,v in result.items() if k not in {'receipt','issues'}}),flush=True)

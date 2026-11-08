from pathlib import Path
import json,sys,shutil,hashlib
root=Path('C:/Users/18483/AppData/Local/Temp/vra-acadsharp-probe-20261108')
source=Path('C:/Users/18483/AppData/Local/Temp/vra-libredwg-014-reference-20261108')
sys.path.insert(0,'C:/Users/18483/AppData/Local/Temp/vra-dwg-conversion-20261108')
from backend.native_windows import staging
from backend.native_ownership import owned_temporary
from backend.native_staging import copy_file
from backend import execution
import ezdxf
out=root/'screen';out.mkdir(exist_ok=False)
inputs=sorted((source/'decode-reference').glob('*/input.dwg'))+sorted((source/'strict-gate').glob('*/input.dwg'))
(out/'frozen.json').write_text(json.dumps({'cases':[{'id':p.parent.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in inputs],'gate':'same inputs; default writer; strict ezdxf readfile/audit with zero errors/fixes; no automatic repair; all engine notifications retained','scope':'engine screen only, not application acceptance','binaries':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.glob('*.dll')}},indent=2))
results=[]
for path in inputs:
    target=out/path.parent.name;target.mkdir();result={'case':path.parent.name}
    try:
        with staging() as s,owned_temporary(root) as control:
            rt=s['root']/'runtime';rt.mkdir()
            dotnet=Path('C:/Program Files/dotnet')
            files={dotnet/'dotnet.exe':rt/'dotnet.exe',dotnet/'host/fxr/8.0.21/hostfxr.dll':rt/'host/fxr/8.0.21/hostfxr.dll'}
            for p in (dotnet/'shared/Microsoft.NETCore.App/8.0.21').iterdir():
                if p.is_file() and p.suffix in {'.dll','.json'}:files[p]=rt/p.relative_to(dotnet)
            for n in ['Converter.dll','Converter.runtimeconfig.json','ACadSharp.dll']:files[root/n]=rt/n
            for src,dst in files.items():
                dst.parent.mkdir(parents=True,exist_ok=True);copy_file(src,dst,64*1024**2)
            copy_file(path,s['root']/'input.dwg',10*1024**2)
            logs=control/'logs';logs.mkdir()
            try:
                result['receipt']=execution.supervise([rt/'dotnet.exe',rt/'Converter.dll',s['root']/'input.dwg',s['work']/'output.dxf'],control,logs,execution.Policy(memory_bytes=1024**3,cpu_seconds=20,output_bytes=16*1024**2,output_files=32,log_bytes=256*1024),40,output=s['work'],isolation={'sid':s['sid'],'work':str(s['work'])},extra_output_roots=[s['profile_root']])
                shutil.copyfile(s['work']/'output.dxf',target/'output.dxf')
            finally:
                for p in logs.glob('*.log'):shutil.copyfile(p,target/p.name)
        doc=ezdxf.readfile(target/'output.dxf');a=doc.audit()
        notes=[json.loads(l) for l in (target/'stdout.log').read_text(encoding='utf-8-sig').splitlines() if l.startswith('{')]
        (target/'notifications.json').write_text(json.dumps(notes,indent=2))
        result.update(errors=len(a.errors),fixes=len(a.fixes),strict_pass=not a.errors and not a.fixes,notifications=len(notes),error_notes=sum(n.get('type')=='Error' for n in notes),counts=len(doc.modelspace()),units=doc.units,issues=[{'code':int(f.code),'message':f.message} for f in a.fixes][:30])
    except Exception as e:
        result['error']=str(e)
        if hasattr(e,'receipt'):result['receipt']=e.receipt
    results.append(result);(out/'results.json').write_text(json.dumps(results,indent=2));print(json.dumps({k:v for k,v in result.items() if k not in {'receipt','issues'}}),flush=True)
    if 'error' in result and len(results)==1:
        print('First native launch failed; stop without re-running remaining inputs.');break

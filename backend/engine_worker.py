"""Private supervisor entry point. Never exposed as an Agent/API shell tool."""
import json
import os
import subprocess
import sys
from pathlib import Path
from contextlib import nullcontext

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.engine_limits import install
from backend.native_environment import environment


def write(path,value):
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value),encoding='utf-8')
    temporary.replace(path)


def main():
    request=Path(sys.argv[1])
    if request.stat().st_size>65536:raise ValueError('Oversized engine request')
    data=json.loads(request.read_text(encoding='utf-8'))
    receipt={'nonce':data['nonce'],'supervisor_pid':os.getpid(),
             **install(data['memory_bytes'],data['cpu_seconds'],data['file_bytes'])}
    target=request.with_suffix('.receipt.json')
    write(target,{**receipt,'state':'ready'})
    # Child inherits the installed job/rlimits and stdout/stderr pipes. No shell.
    launched=False
    try:
        if data.get('isolation') is not None:
            if sys.platform!='win32':raise RuntimeError('Requested LPAC unavailable')
            from backend.native_windows import launch
            isolation=data['isolation']
            context=launch(data['command'],isolation['work'],isolation['sid'])
        else:
            context=nullcontext(subprocess.Popen(data['command'],cwd=request.parent,stdin=subprocess.DEVNULL,
                                 env=environment(request.parent),creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)))
        with context as process:
            launched=True
            receipt.update(engine_pid=process.pid,state='launched')
            if data.get('isolation') is not None:
                receipt['isolation']={'mechanism':'windows_lpac','appcontainer_sid':isolation['sid'],
                    'capabilities':['registryRead'],'token_verified':True,'job_verified':True,
                    'lpac_access_check_verified':True,'capabilities_verified':True,'child_processes':'supervisor_job_limit_2',
                    'inherited_handles':'standard_streams_only','network_capabilities':[]}
            write(target,receipt)
            code=process.wait()
    except Exception as exc:
        # A suspended process may have been created then rejected; do not assert
        # an engine call ran unless the verified launch context actually yielded.
        write(target,{**receipt,'state':'execution_failed' if launched else 'launch_failed',
                      'failure_type':type(exc).__name__,'os_error':getattr(exc,'winerror',None)})
        return 70
    write(target,{**receipt,'state':'finished','exit_code':code})
    return 0 if code==0 else 1


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception:
        # Parent reads an incomplete receipt and fails; never print private args.
        raise SystemExit(70) from None

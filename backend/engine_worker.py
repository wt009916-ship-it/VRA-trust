"""Private supervisor entry point. Never exposed as an Agent/API shell tool."""
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.engine_limits import install


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
    try:
        process=subprocess.Popen(data['command'],cwd=request.parent,stdin=subprocess.DEVNULL,
                                 creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    except Exception:
        write(target,{**receipt,'state':'launch_failed'})
        return 70
    receipt.update(engine_pid=process.pid,state='launched')
    write(target,receipt)
    code=process.wait()
    write(target,{**receipt,'state':'finished','exit_code':code})
    return 0 if code==0 else 1


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception:
        # Parent reads an incomplete receipt and fails; never print private args.
        raise SystemExit(70) from None

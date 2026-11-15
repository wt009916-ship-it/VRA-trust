"""Bounded byte copies for freshly created, application-owned native workspaces."""
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import tempfile

from .native_ownership import owned_temporary as private_temporary
from .runtime_lock import safe_path


def copy_file(source,target,maximum):
    source=safe_path(source);size=source.stat().st_size
    if not source.is_file() or size>maximum:raise ValueError('Native staging file invalid/oversized')
    digest=hashlib.sha256();count=0
    with source.open('rb') as inp,target.open('xb') as out:
        while chunk:=inp.read(1024*1024):
            count+=len(chunk)
            if count>maximum:raise ValueError('Native staging file grew beyond budget')
            digest.update(chunk);out.write(chunk)
    if count!=size:raise ValueError('Native staging file changed size')
    return {'sha256':digest.hexdigest(),'bytes':count}


@contextmanager
def linux_engine_workspace(engine,model=None,weather=None):
    engine=safe_path(engine)
    with private_temporary(Path(tempfile.gettempdir())) as root:
        runtime=root/'runtime';runtime.mkdir(mode=0o700)
        work=root/'output';work.mkdir(mode=0o700)
        sources=[engine]+[p for p in engine.parent.iterdir() if '.so' in p.name or p.name=='Energy+.idd']
        if len(sources)>256:raise ValueError('Native runtime file count exceeded')
        budget=128*1024**2;identities={}
        for source in sources:
            # Official ELF runtime .so aliases may point inside the same install.
            # Copy their bytes, never create links or follow an alias outside it.
            resolved=source.resolve(strict=True)
            if resolved.parent!=engine.parent:raise ValueError('Native runtime alias escapes installation')
            target=runtime/source.name
            identity=copy_file(resolved,target,budget)
            budget-=identity['bytes'];identities[source.name]=identity
            os.chmod(target,0o500 if source==engine else 0o400)
        for name,source in [('model.idf',model),('weather.epw',weather)]:
            if source is not None:
                identities[name]=copy_file(source,root/name,256*1024**2)
                os.chmod(root/name,0o400)
        executable=runtime/engine.name
        yield {'root':root,'work':work,'engine':executable,'identities':identities,'extra_output_roots':[],
               'isolation':{'mechanism':'linux_landlock_seccomp','read_paths':[str(root)],
                            'execute_paths':[str(executable)],'work':str(work)}}

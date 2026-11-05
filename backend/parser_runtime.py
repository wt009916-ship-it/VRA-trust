"""Per-task read-only parser runtime and input, with a trusted native supervisor.

Only public code/dependencies enter the verified runtime snapshot. Never grant
permissions on original installations or business files. No unrestricted fallback.
"""
from contextlib import contextmanager
from dataclasses import replace
from importlib.metadata import distribution
import os
import re
from pathlib import Path, PurePosixPath
import shutil
import sys
import sysconfig
import tempfile
import threading
import time

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from . import core, execution
from .native_staging import copy_file
from .private_storage import private_temporary
from .runtime_lock import safe_path
from .worker_limits import POLICIES
from . import parser_runtime_cache

ROOT=Path(__file__).resolve().parent
PACKAGES={'cad':('ezdxf','ifcopenshell'),'standards':('pypdf',),
          'drawing':('rapidocr','onnxruntime','Pillow','pypdfium2')}
MODULES={'cad':('cad_worker.py','dxf_geometry.py','ifc_details.py','ifc_geometry.py'),
         'standards':('standards_worker.py',),'drawing':('drawing_worker.py','drawing_models.py')}
MAX_BYTES=1024**3
MAX_FILES=20000
_capacity=threading.BoundedSemaphore(2)
_plan_lock=threading.RLock()
_plans={}


def dependencies(kind):
    pending=list(PACKAGES[kind]);found={}
    while pending:
        name=canonicalize_name(pending.pop())
        if name in found:continue
        if len(found)>=64:raise ValueError('Parser dependency count exceeded')
        dist=distribution(name);found[name]=dist
        for text in dist.requires or ():
            requirement=Requirement(text)
            if requirement.marker and not requirement.marker.evaluate({'extra':''}):continue
            if requirement.url or requirement.extras:raise ValueError('Unsupported parser dependency declaration')
            dependency=distribution(requirement.name)
            if not requirement.specifier.contains(dependency.version,prereleases=True):
                raise ValueError('Parser dependency version mismatch')
            pending.append(requirement.name)
    return found


def identity(kind):
    try:versions={name:dist.version for name,dist in dependencies(kind).items()}
    except (OSError,ValueError,ImportError) as exc:
        raise core.ValidationError('Isolated parser dependencies unavailable or inconsistent') from exc
    return core.hash_json({'runtime':core.sha(Path(__file__)),'worker':core.sha(ROOT/'parser_worker.py'),
        'cache':core.sha(ROOT/'parser_runtime_cache.py'),'policy':POLICIES[kind],
        'native':{name:core.sha(ROOT/name) for name in ('native_staging.py','native_environment.py',
                   'native_windows.py','native_linux.py','engine_worker.py','engine_limits.py','execution.py','execution_lifetime.py')},
        'python':sys.version,'platform':sys.platform,
        'dependencies':versions})


def plan(kind):
    """Select installed wheel files without copying scripts, links or user data."""
    files={}
    def add(source,target):
        source=safe_path(source)
        if not source.is_file():raise ValueError('Parser runtime file missing')
        previous=files.get(target)
        if previous is not None and previous!=source:raise ValueError('Parser runtime destination collision')
        files[target]=source
        if len(files)>MAX_FILES:raise ValueError('Parser runtime file count exceeded')
    for dist in dependencies(kind).values():
        base=safe_path(dist.locate_file(''))
        for entry in dist.files or ():
            relative=PurePosixPath(str(entry))
            # Wheel command-line launchers are not used by this entry point.
            if relative.is_absolute() or '..' in relative.parts:continue
            if '__pycache__' in relative.parts or relative.suffix in {'.pyc','.pth'}:continue
            add(base/Path(relative),'packages/'+relative.as_posix())
    for name in (*MODULES[kind],'parser_worker.py'):add(ROOT/name,'code/'+name)
    if sys.platform=='win32':
        base=safe_path(sys.base_prefix)
        for p in base.iterdir():
            if p.is_file() and (p.suffix.lower()=='.dll' or p.name=='python.exe'):add(p,'python/'+p.name)
        for directory in ('Lib','DLLs'):
            for parent,dirs,names in os.walk(base/directory,followlinks=False):
                dirs[:]=[d for d in dirs if d not in {'site-packages','__pycache__','test','idlelib','tkinter','turtledemo','ensurepip'}]
                for name in names:
                    p=Path(parent)/name
                    if p.suffix.lower() in {'.py','.pyd','.dll'}:add(p,'python/'+p.relative_to(base).as_posix())
    elif sys.platform!='linux':raise ValueError('Native parsers require Windows or Linux')
    size=sum(p.stat().st_size for p in files.values())
    if size>MAX_BYTES:raise ValueError('Parser runtime byte budget exceeded')
    return files,size


def _plan_for_run(kind,fingerprint):
    # Resolve and validate the same installed manifest once per policy version.
    # cache.get still checks ALL source size/mtime stamps and cached byte hashes
    # on every request; it never silently refreshes a changed installation.
    with _plan_lock:
        if kind not in _plans or _plans[kind][0]!=fingerprint:
            _plans[kind]=(fingerprint,*plan(kind))
        return _plans[kind][1:]


@contextmanager
def _workspace():
    if sys.platform=='win32':
        from .native_windows import staging
        with staging() as scope:
            yield {**scope,'isolation':{'sid':scope['sid'],'work':str(scope['work'])},
                   'extra_roots':[scope['profile_root']]}
    elif sys.platform=='linux':
        with private_temporary(Path(tempfile.gettempdir())) as root:
            work=root/'output';work.mkdir(mode=0o700)
            python=Path(getattr(sys,'_base_executable',sys.executable)).resolve(strict=True)
            # An application may use an official Python installed outside /usr.
            # The selected interpreter's public stdlib/shared runtime is needed
            # before the staged packages can be imported (-S skips site hooks).
            reads=[str(root),str(Path(sysconfig.get_path('stdlib')).resolve(strict=True))]
            library=Path(sysconfig.get_config_var('LIBDIR') or '')/str(sysconfig.get_config_var('LDLIBRARY') or '')
            if library.is_file():reads.append(str(library.resolve(strict=True)))
            yield {'root':root,'work':work,'python':python,'extra_roots':[],
                   'isolation':{'mechanism':'linux_landlock_seccomp','read_paths':reads,
                                'execute_paths':[str(python)],'work':str(work)}}
    else:raise ValueError('Native parsers require Windows or Linux')


@contextmanager
def run(kind,source,page=1):
    if kind not in PACKAGES:raise core.ValidationError('Unknown parser')
    if not _capacity.acquire(False):raise core.ValidationError('Native parsers busy; retry later')
    started=time.monotonic()
    try:
        source=safe_path(source);fingerprint=identity(kind);files,size=_plan_for_run(kind,fingerprint)
        limit=20*1024**2 if kind=='standards' else 10*1024**2
        if not 0<source.stat().st_size<=limit:raise core.ValidationError('Parser input size invalid')
        if shutil.disk_usage(tempfile.gettempdir()).free<size+limit+128*1024**2:
            raise core.ValidationError('Insufficient free storage for isolated parser')
        runtime=parser_runtime_cache.get(kind,files,size,fingerprint,MAX_BYTES,MAX_FILES)
        with _workspace() as scope,private_temporary(Path(tempfile.gettempdir())) as control:
            root,work=scope['root'],scope['work'];runtime_root=runtime['root']
            if sys.platform=='linux':scope['isolation']['read_paths'].append(str(runtime_root))
            input_path=root/('input'+source.suffix.lower())
            input_identity=copy_file(source,input_path,limit)
            if input_identity['sha256']!=core.sha(source):raise core.ValidationError('Parser input changed during staging')
            if sys.platform=='linux':input_path.chmod(0o400)
            python=runtime_root/'python/python.exe' if sys.platform=='win32' else scope['python']
            args=[str(runtime_root/'code/parser_worker.py'),kind,str(input_path),str(work/'result.json'),str(page)]
            bootstrap='import sys,runpy;sys.path[:0]='+repr([str(runtime_root/'code'),str(runtime_root/'packages')])+';sys.argv='+repr(args)+';runpy.run_path(sys.argv[0],run_name="__main__")'
            policy=replace(execution.Policy(),**POLICIES[kind],output_bytes=(64 if kind=='drawing' else 16)*1024**2,
                           output_files=128,log_bytes=256*1024)
            logs=control/'logs';logs.mkdir()
            staging_seconds=time.monotonic()-started
            try:
                receipt=execution.supervise([python,'-I','-B','-S','-X','utf8','-c',bootstrap],control,logs,policy,
                    60 if kind=='drawing' else 30,output=work,isolation=scope['isolation'],extra_output_roots=scope['extra_roots'])
            except execution.ExecutionError as exc:
                # Diagnostics stay internal; API clients see only this bounded message.
                exc.parser_stderr=(logs/'stderr.log').read_text(encoding='utf-8',errors='replace') if (logs/'stderr.log').exists() else ''
                rejected=work/'result.json';report=exc.receipt
                if (report.get('filesystem_network_sandbox') is True and report.get('launch_state')=='finished'
                    and report.get('exit_code')==1 and rejected.is_file() and rejected.stat().st_size<=4096):
                    try:
                        detail=core.read_json(rejected)
                        error=detail.get('error') if isinstance(detail,dict) else None
                    except (OSError,ValueError):error=None
                    if isinstance(error,str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}',error):
                        raise core.ValidationError('File rejected by isolated parser: '+error+'; original preserved') from exc
                raise core.ValidationError('Parser resource enforcement or isolated execution failed; original preserved') from exc
            if identity(kind)!=fingerprint:raise core.ValidationError('Parser runtime changed during processing')
            resources={'kind':kind,'enforced':True,'boundary':'FILESYSTEM_NETWORK_AND_RESOURCE_BUDGET',
                       'mechanism':receipt['mechanism'],'memory_bytes':receipt['memory_bytes'],'cpu_seconds':receipt['cpu_seconds'],
                       'execution_receipt':receipt,'input_copy':input_identity,'runtime_hash':runtime['hash'],
                       'runtime_bytes':runtime['bytes'],'runtime_files':runtime['files'],'runtime_cache_hit':runtime['cache_hit'],
                       'runtime_verification':runtime['verification'],
                       'policy_hash':fingerprint,'staging_seconds':staging_seconds,
                       'elapsed_before_cleanup_seconds':time.monotonic()-started}
            yield {'work':work,'resource_limits':resources}
    except core.ValidationError:raise
    except (OSError,ValueError,RuntimeError,ImportError) as exc:
        raise core.ValidationError('Isolated parser unavailable or input/runtime changed; original preserved') from exc
    finally:_capacity.release()

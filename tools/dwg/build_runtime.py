"""Build an explicit local runtime; never invoked by an upload or API call.

Requires official ACadSharp 3.8.35 nupkg, installed .NET 8.0.21, Windows csc.
No system installation, PATH changes, global restore, or automatic download.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import zipfile

PACKAGE_SHA256 = '020013744e7415e6d7e244d1b2376be25614b83c2596a0ec3a9056237db759d4'


def build(package,dotnet,compiler,out):
    if hashlib.sha256(package.read_bytes()).hexdigest() != PACKAGE_SHA256:
        raise ValueError('Official package bytes do not match reviewed package')
    out.mkdir(parents=True,exist_ok=False)
    with zipfile.ZipFile(package) as archive:
        (out/'ACadSharp.dll').write_bytes(archive.read('lib/net8.0/ACadSharp.dll'))
    runtime = dotnet/'shared/Microsoft.NETCore.App/8.0.21'
    for src in [dotnet/'dotnet.exe',dotnet/'host/fxr/8.0.21/hostfxr.dll',*runtime.iterdir()]:
        if src.is_file() and (src.suffix in {'.dll','.json'} or src == dotnet/'dotnet.exe'):
            dst=out/src.relative_to(dotnet);dst.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(src,dst)
    shutil.copyfile(Path(__file__).with_name('ACadSharp.LICENSE.txt'),out/'ACadSharp.LICENSE.txt')
    for name in ['LICENSE.txt','ThirdPartyNotices.txt']:
        shutil.copyfile(dotnet/name,out/('dotnet-'+name))
    source = Path(__file__).with_name('Converter.cs')
    refs = [p for p in runtime.glob('System.*.dll') if '.Native.' not in p.name]+[runtime/'mscorlib.dll',runtime/'netstandard.dll',out/'ACadSharp.dll']
    command=[str(compiler),'/noconfig','/nologo','/nostdlib+','/target:exe','/out:'+str(out/'Converter.dll')]
    command += ['/reference:'+str(p) for p in refs]+[str(source)]
    env={k:v for k,v in os.environ.items() if k.upper() != 'LIB'}
    process=subprocess.run(command,capture_output=True,env=env)
    (out/'build.log').write_bytes(process.stdout+process.stderr)
    if process.returncode:raise ValueError('Bridge compilation failed; see build.log')
    (out/'Converter.runtimeconfig.json').write_text(json.dumps({'runtimeOptions':{'tfm':'net8.0','framework':{'name':'Microsoft.NETCore.App','version':'8.0.21'},'rollForward':'Disable'}}))
    files={p.relative_to(out).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in out.rglob('*') if p.is_file() and p.name != 'build.log' and p.suffix != '.txt'}
    manifest={'schema':1,'engine':'ACadSharp 3.8.35','framework':'8.0.21','package_sha256':PACKAGE_SHA256,
              'bridge_source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'files':files}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    return {'runtime':str(out),'files':len(files),'manifest_sha256':hashlib.sha256((out/'manifest.json').read_bytes()).hexdigest()}


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ['package','dotnet','compiler','output']:parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(build(args.package,args.dotnet,args.compiler,args.output)))

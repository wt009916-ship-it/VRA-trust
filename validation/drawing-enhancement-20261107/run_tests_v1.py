"""Run meaningful local tests in private temporary storage; preserve each log."""
import os,subprocess,sys,tempfile,uuid
from pathlib import Path
repo=Path.cwd();out=Path(__file__).parent
base=Path(tempfile.gettempdir())/('vra-drawing-geometry-tests-'+uuid.uuid4().hex);base.mkdir()
env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',VRA_DATA_DIR=str(base/'bootstrap'))
with (out/'tests-v1.log').open('xb') as stream:
    result=subprocess.run([sys.executable,'-m','pytest','-q','-p','no:cacheprovider','tests/test_drawing_geometry.py','tests/test_drawings.py',
                           '--basetemp',str(base/'pytest')],cwd=repo,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=900)
print({'exit_code':result.returncode,'base':str(base)},flush=True)
raise SystemExit(result.returncode)

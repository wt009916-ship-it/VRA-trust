"""Small, explicit child environment; never forward provider secrets or loaders."""
import os
from pathlib import Path


def environment(work):
    work=str(Path(work).resolve())
    # AppContainer creation needs the account's base Windows profile locations.
    # Values identify paths; access to their contents is still checked by the OS.
    allowed={'SYSTEMROOT','SYSTEMDRIVE','WINDIR','USERPROFILE','LOCALAPPDATA','APPDATA'}
    result={key:value for key,value in os.environ.items() if key.upper() in allowed}
    result.update(TEMP=work,TMP=work,TMPDIR=work,HOME=work,XDG_CONFIG_HOME=work,
                  OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',MKL_NUM_THREADS='2',
                  LANG='C.UTF-8',LC_ALL='C.UTF-8',PYTHONDONTWRITEBYTECODE='1')
    return result

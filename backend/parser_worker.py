"""Private entry point: called only AFTER the trusted supervisor installs isolation."""
import json
import os
import sys
import traceback
from pathlib import Path


def main():
    kind,source,target,page,*options=sys.argv[1:]
    source,target=Path(source),Path(target)
    # Windows process creation retains profile variables needed by LPAC. Once
    # inside the boundary, libraries must use only this task's monitored cache.
    # In particular ezdxf otherwise probes ~/.cache/font_manager_cache.json.
    for name in ('HOME','USERPROFILE','APPDATA','LOCALAPPDATA','XDG_CONFIG_HOME','XDG_CACHE_HOME'):
        os.environ[name]=str(target.parent)
    try:
        if kind=='cad':
            from cad_worker import parse
            result=parse(source);maximum=8*1024**2
        elif kind=='standards':
            from standards_worker import extract
            result=extract(source);maximum=4*1024**2
        elif kind=='drawing':
            from drawing_worker import parse
            if len(options)>1:raise ValueError('Unexpected drawing options')
            result=parse(source,int(page),target.with_name('preview.png'),json.loads(options[0]) if options else None);maximum=2*1024**2
        else:raise ValueError('Unknown parser')
        text=json.dumps(result,ensure_ascii=False,allow_nan=False)
        if len(text.encode('utf-8'))>maximum:raise ValueError('Parser result exceeds budget')
        target.write_text(text,encoding='utf-8')
    except Exception as exc:
        # The supervisor captures bounded, private diagnostics, never API text.
        traceback.print_exc()
        target.write_text(json.dumps({'error':type(exc).__name__}),encoding='utf-8')
        return 1
    return 0


if __name__=='__main__':raise SystemExit(main())

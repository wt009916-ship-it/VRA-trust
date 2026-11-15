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
            if len(options)>1:raise ValueError('Unexpected CAD options')
            if options:
                values=json.loads(options[0])
                if not isinstance(values,dict):raise ValueError('Invalid CAD operation')
                if set(values)=={'operation','product_ids'} and values['operation']=='ifc_union':
                    from ifc_union import measure_union
                    result=measure_union(source,values['product_ids'])
                elif set(values)=={'operation','product_ids'} and values['operation']=='ifc_material_collection':
                    from ifc_material_collection import measure_collection
                    result=measure_collection(source,values['product_ids'])
                elif set(values)=={'operation','product_id'} and values['operation']=='ifc_beam_profile':
                    from ifc_beam_profiles import inspect_beam
                    result=inspect_beam(source,values['product_id'])
                elif set(values)=={'operation','product_id'} and values['operation']=='ifc_layers':
                    from ifc_layer_quantities import measure_layers
                    result=measure_layers(source,values['product_id'])
                else:
                    raise ValueError('Invalid CAD operation')
            else:
                result=parse(source)
            maximum=8*1024**2
        elif kind=='standards':
            from standards_worker import extract, select_page
            if len(options)>1: raise ValueError('Unexpected standards options')
            if options:
                if json.loads(options[0])!={'operation':'select_page'}: raise ValueError('Invalid standards operation')
                result=select_page(source,int(page),target.with_name('selected.pdf'))
            else: result=extract(source)
            maximum=4*1024**2
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

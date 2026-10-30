"""Reproducible shape matrix: authored controls, IFC geometry roundtrip, native annual engine.

Controls test coverage and conservation; they do NOT add to real-project counts.
All operation, weather and assemblies are hypothetical software inputs.
"""
import argparse
import copy
import os
from pathlib import Path
import runpy
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.morphology_cases import cases


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--geometry-only',action='store_true')
    args=parser.parse_args();out=args.output.resolve()
    if out.exists() or out.is_relative_to(ROOT):parser.error('Choose a new directory outside the checkout')
    out.mkdir(parents=True);os.environ['VRA_DATA_DIR']=str(out/'bootstrap')
    from backend import core,model_export,model_import,model_geometry
    from backend.model_schema import ModelDraft,ImportOptions
    helpers=runpy.run_path(str(ROOT/'tests/test_model_workbench.py'))
    report={'nature':'AUTHORED_CONTROLLED_GEOMETRY_NOT_REAL_BUILDINGS','compiler_hash':model_export.compiler_hash(),
            'weather':'Golden reference, not source-site weather','cases':[]}
    for key,rooms in cases().items():
        item={'case':key,'rooms':len(rooms)};report['cases'].append(item);job=out/key;job.mkdir()
        try:
            m=ModelDraft(name=key,rooms=rooms,review_note='Controlled software morphology acceptance; no measured building claim',
                thermal={**helpers['THERMAL'],'constructions':helpers['ASSEMBLIES']}).model_dump()
            core.write_json(job/'model.json',m)
            source=job/'source.ifc';source.write_text(model_export.ifc(m),encoding='utf-8')
            imported=model_import.ifc(source,ImportOptions(file_id='controlled_source'))
            area=sum(model_geometry.floor_area(r) for r in m['rooms']);volume=sum(model_geometry.room_volume(r) for r in m['rooms'])
            a=sum(model_geometry.floor_area(r) for r in imported['rooms']);v=sum(model_geometry.room_volume(r) for r in imported['rooms'])
            item.update(ifc_sha256=core.sha(source),source_area_m2=area,imported_area_m2=a,source_volume_m3=volume,imported_volume_m3=v)
            if len(imported['rooms'])!=len(rooms) or abs(a-area)>max(.0001,area*1e-6) or abs(v-volume)>max(.0001,volume*1e-6):
                raise core.ValidationError('IFC roundtrip conservation mismatch')
            audit=model_export.geometry_audit(m);core.write_json(job/'audit.json',audit);item['audit_passed']=audit['passed']
            if not audit['passed']:raise core.ValidationError(str(audit['issues']))
            text,surfaces=model_export.idf(m);(job/'model.idf').write_text(text,encoding='utf-8')
            item['exposed_floor_faces']=sum(s['kind']=='Floor' and s['boundary']=='Outdoors' for s in surfaces)
            if key in ('cantilever','skybridge','split_level') and not item['exposed_floor_faces']:
                raise core.ValidationError('Suspended/exposed floor wrongly treated as ground')
            item['status']='geometry_passed'
            if not args.geometry_only:
                shutil.copy2(ROOT/'fixtures/demo/reference_5zone/weather.epw',job/'weather.epw')
                c=copy.deepcopy(core.load_case('reference_5zone'));c.update(case_id='controlled_'+key,name=key+' authored software control',
                    geometry_status='Controlled analytic/faceted morphology, not an as-built building',weather='weather.epw',
                    notes=['Hypothetical office operation/assemblies/Golden weather; not source-building performance'],
                    schemes=[{**c['schemes'][0],'model':'model.idf'}])
                r=core.run_simulation(c['case_id'],'baseline','none',job/'run',case_override=c,file_root=job)
                item.update(status='annual_'+r['status'],warnings=r.get('warnings_count'),annual_days=(r.get('metrics') or {}).get('annual_days'),error=r.get('error'))
        except Exception as e:item.update(status='blocked',error=type(e).__name__+': '+str(e)[:2000])
        core.write_json(out/'results.json',report);print(key,item['status'],item.get('warnings'),str(item.get('error'))[:500],flush=True)
    core.write_json(out/'results.json',report)


if __name__=='__main__':main()

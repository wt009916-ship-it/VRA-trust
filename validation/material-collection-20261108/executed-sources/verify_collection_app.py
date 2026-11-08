from pathlib import Path
import shutil,subprocess,sys,json
R=Path('C:/Users/18483/AppData/Local/Temp/vra-drawing-components-20261108')
HERE=Path(__file__).parent
OUT=Path('C:/Users/18483/AppData/Local/Temp/vra-material-collection-public-20261108')
shutil.copyfile(HERE/'test_material_collection_service.py',R/'tests/test_material_collection_service.py')
shutil.copyfile(HERE/'material-collection.test.js',R/'frontend/tests/material-collection.test.js')
commands=[('api-related',[sys.executable,'-B','-X','utf8','-m','pytest','tests/test_material_collection_service.py','tests/test_ifc_union.py','tests/test_material_takeoff.py','tests/test_material_scenarios.py','-q','-p','no:cacheprovider','--basetemp',str(OUT/'pytest-api')],R),
          ('frontend',['node','--test','tests/material-collection.test.js','tests/ifc-ui.test.js','tests/cad-current.test.js'],R/'frontend'),
          ('ruff',[sys.executable,'-m','ruff','check','backend/ifc_material_collection.py','backend/ifc_layer_quantities.py','backend/cad_union.py','backend/material_collection_service.py','backend/material_takeoff.py','backend/parser_worker.py','backend/parser_runtime.py','tests/test_ifc_material_collection.py','tests/test_material_collection_service.py'],R)]
for name,args,cwd in commands:
    result=subprocess.run(args,cwd=cwd,capture_output=True,text=True,encoding='utf-8',errors='replace')
    (OUT/(name+'.log')).write_text(result.stdout+result.stderr,encoding='utf-8')
    print(json.dumps({'check':name,'exit_code':result.returncode,'tail':(result.stdout+result.stderr)[-1800:]}),flush=True)

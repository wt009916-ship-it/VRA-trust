import shutil
from pathlib import Path
root=Path(__file__).parent
repo=Path('C:/Users/18483/AppData/Local/Temp/vra-timestep-reliability-20261108')
shutil.copy2(root/'ifc_composite_materials.py',repo/'backend/ifc_composite_materials.py')
p=repo/'backend/ifc_member_quantities.py'
s=p.read_text(encoding='utf-8')
needle="        material, mapping = single_material(binding, element)"
replacement="""        declared = binding['material']
        group = declared.get('profile_set') if declared['type'] == 'IfcMaterialProfileSetUsage' else declared
        if (group and group['type'] == 'IfcMaterialProfileSet' and len(group['profiles']) > 1
                and (group.get('composite_profile_id') or len({p['material']['id'] for p in group['profiles']}) > 1)):
            try:
                from .ifc_composite_materials import measure_composite
            except ImportError:
                from ifc_composite_materials import measure_composite
            return measure_composite(doc, element, binding, group, scale, result, mesh_sink)
        material, mapping = single_material(binding, element)"""
assert s.count(needle)==1
p.write_text(s.replace(needle,replacement),encoding='utf-8')
for name in ['parser_runtime.py','material_takeoff.py']:
    p=repo/'backend'/name;s=p.read_text(encoding='utf-8')
    s=s.replace("'ifc_member_quantities.py',","'ifc_member_quantities.py','ifc_composite_materials.py',")
    if name=='material_takeoff.py':
        s=s.replace('厚度为空。空腔','厚度为空；复合梁柱片段编号指原材料轮廓实体，逐材空间分区。空腔')
    p.write_text(s,encoding='utf-8')
p=repo/'backend/ifc_material_collection.py';s=p.read_text().replace('declared homogeneous beams/columns','declared homogeneous or explicitly partitioned composite beams/columns');p.write_text(s,encoding='utf-8')
p=repo/'frontend/src/material-collection-ui.js';s=p.read_text(encoding='utf-8').replace('明确单一材料的梁柱','明确单材或可核验复合分区的梁柱').replace('单一材料梁柱','明确材料分区的梁柱');p.write_text(s,encoding='utf-8')
p=repo/'frontend/tests/ifc-member-ui.test.js';s=p.read_text(encoding='utf-8').replace('明确单一材料的梁柱','明确单材或可核验复合分区的梁柱');p.write_text(s,encoding='utf-8')
fixture=(root/'reference_fixture.py').read_text(encoding='utf-8');fixture=fixture[fixture.index('from test_ifc_member_quantities'):]
imports='import hashlib\nimport json\nfrom pathlib import Path\nimport ifcopenshell\nimport pytest\nfrom backend.ifc_layer_quantities import measure_layers\nfrom backend.ifc_material_collection import measure_collection\n'
(repo/'tests/test_ifc_composite_materials.py').write_text(imports+fixture+(root/'test_ifc_composite_materials_tail.py').read_text(encoding='utf-8'),encoding='utf-8')
out=repo/'validation/ifc-composite-materials-20261115';out.mkdir(exist_ok=False)
shutil.copy2(root/'reference-frozen.json',out/'reference-frozen.json')
shutil.copy2(root/'PLAN.md',repo/'docs/IFC_COMPOSITE_MATERIALS_PLAN.md')
print('Installed bounded composite partition implementation and reference tests')

from pathlib import Path
root=Path(__file__).parent;repo=Path('C:/Users/18483/AppData/Local/Temp/vra-timestep-reliability-20261108')
p=repo/'backend/ifc_composite_materials.py';s=p.read_text(encoding='utf-8');needle='    composite = item.SweptArea\n'
assert s.count(needle)==1
s=s.replace(needle,needle+"    if composite.ProfileType != 'AREA' or not math.isfinite(item.Depth) or item.Depth <= 0:\n        raise ValueError('composite_source_sweep_invalid')\n")
p.write_text(s,encoding='utf-8')
p=repo/'tests/test_ifc_composite_materials.py'
with p.open('a',encoding='utf-8') as f:f.write('''


@pytest.mark.parametrize('problem',['curve_profile','zero_depth','negative_depth'])
def test_invalid_original_sweep_is_not_silently_repaired_by_partition(tmp_path,problem):
    doc,element,_,_,_,solid,path=composite(tmp_path,case='adjacent')
    if problem=='curve_profile':solid.SweptArea.ProfileType='CURVE'
    else:solid.Depth=0. if problem=='zero_depth' else -4.
    doc.write(str(path));sink=[];r=measure_layers(path,element.id(),mesh_sink=sink)
    assert r['status']=='unavailable' and r['reason']=='composite_source_sweep_invalid',r
    assert r['layers']==[] and r['host_volume_m3'] is r['total_layer_envelope_m3'] is None and not sink
''')
# Preserve the first HTTP run and repeat the integrated check on changed source.
s=(root/'http_acceptance.py').read_text(encoding='utf-8').replace("/'actual-http'","/'actual-http-final'")
(root/'http_acceptance_final.py').write_text(s,encoding='utf-8')
print('Original composite AREA and positive finite depth checked before decomposition')

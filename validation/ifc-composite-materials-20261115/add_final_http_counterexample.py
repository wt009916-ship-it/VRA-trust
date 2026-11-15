from pathlib import Path
root=Path(__file__).parent;p=root/'http_acceptance_final.py';s=p.read_text(encoding='utf-8')
s=s.replace("_,element,_,_,profiles,_,input_path=composite", "doc,element,_,_,profiles,solid,input_path=composite")
needle="  c.patch(base+'/evidence/'"
insert="""  solid.SweptArea.ProfileType='CURVE'
  bad=c.post(base+'/files',files={'file':('bad-composite.ifc',doc.to_string().encode())}).json()
  badcad=c.post(base+'/cad-inspections',json={'file_id':bad['file_id']});check('bad_declaration_inspection_preserved',badcad.status_code==201,badcad.status_code)
  rejected=c.post(base+'/ifc-layer-takeoffs',json={'cad_id':badcad.json()['cad_id'],'product_id':element.id()});check('bad_declaration_takeoff_returned',rejected.status_code==201,rejected.status_code)
  refused=rejected.json();save('invalid-profile-takeoff.json',refused)
  check('invalid_original_profile_refused',refused['status']=='unavailable' and refused['result']['total_layer_envelope_m3'] is None and refused['result']['reason']=='composite_source_sweep_invalid',{'status':refused['status'],'reason':refused['result']['reason'],'volume':refused['result']['total_layer_envelope_m3']})
  c.patch(base+'/evidence/'"""
assert s.count(needle)==1;s=s.replace(needle,insert).replace('len(checks)==15','len(checks)==18')
p.write_text(s,encoding='utf-8')

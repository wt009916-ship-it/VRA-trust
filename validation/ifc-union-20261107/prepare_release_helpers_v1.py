import hashlib,json,shutil
from pathlib import Path
out=Path('validation/ifc-union-20261107');repo=Path.cwd();old=repo/'validation/ifc-net-20261107'
a=json.loads((out/'candidate-source-v1.json').read_text());b=json.loads((out/'candidate-source-v2.json').read_text())
hashes={r['path']:r['sha256'] for r in a['files']}
assert [r['path'] for r in b['files'] if hashes.get(r['path'])!=r['sha256']]==['tests/test_execution.py']
shutil.copytree(Path(a['root'])/'frontend/dist',Path(b['root'])/'frontend/dist')
(out/'candidate-equivalence-v1.json').write_text(json.dumps({'v1':a['root'],'v2':b['root'],'only_difference':'tests/test_execution.py Linux-only process-status race fix','backend_and_frontend_bytes_identical':True},indent=2))
for name in ['LICENSE','AUTHORS']:
 shutil.copyfile(out/'probe-installed/manifold3d-3.5.4.dist-info/licenses'/name,out/('manifold3d-'+name+'.txt'))
shutil.copyfile(old/'source-preservation-v1.json',out/'source-preservation-v1.json')
context=json.loads((old/'runtime-context-v1.json').read_text());context.update(base_commit='fe7e8f36da209dfa3b61398b508eda720ecd8d18',prototype_launcher=26940,prototype_listener=41608)
(out/'runtime-context-v1.json').write_text(json.dumps(context,ensure_ascii=False,indent=2),encoding='utf-8')
for name in ['verify_git_source_v1.py','capture_remote_v1.py','merge_release_v1.py','launch_prototype_v1.py','stop_services_v1.py']:
 s=(old/name).read_text(encoding='utf-8').replace('ifc-net-20261107','ifc-union-20261107').replace('IFC_OPENINGS_EVIDENCE','IFC_SELECTED_UNION_EVIDENCE')
 if name=='merge_release_v1.py':s=s.replace('396bda09ae9e95a31fbb493ab0f518a2fd38b5ff','fe7e8f36da209dfa3b61398b508eda720ecd8d18')
 if name=='stop_services_v1.py':
  s=s.replace('parent,child,port=40744,3260,18774','parent,child,port=26936,16836,18774').replace('parent,child,port=21244,31520,18772','parent,child,port=26940,41608,18772')
 (out/name).write_text(s,encoding='utf-8',newline='\n')
print('Prepared guarded release helpers; services unchanged.')

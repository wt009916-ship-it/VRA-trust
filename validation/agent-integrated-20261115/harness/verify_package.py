import gzip
import hashlib
import json
from pathlib import Path

ROOT=Path('D:/稀土agent-稀土制暖全流程/.codex_work/vra-resource-leveling-20261115')
folder=ROOT/'validation/agent-integrated-20261115'
manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
issues=[];secret_keys=[]
def inspect(value,path):
    if isinstance(value,dict):
        for k,v in value.items():
            if k.lower() in {'password','csrf_token','access_token','api_key','authorization','cookie'} and isinstance(v,str) and v:
                secret_keys.append({'path':path,'key':k})
            inspect(v,path)
    elif isinstance(value,list):
        for child in value:inspect(child,path)
for row in manifest['files']:
    path=folder/row['path'];data=path.read_bytes()
    if hashlib.sha256(data).hexdigest()!=row['sha256']:issues.append(row['path'])
    raw=gzip.decompress(data) if path.suffix=='.gz' else data
    if hashlib.sha256(raw).hexdigest()!=row['original_sha256']:issues.append(row['path']+':raw')
    if path.suffix=='.json' or path.name.endswith('.json.gz'):
        inspect(json.loads(raw),row['path'])
assert not issues and not secret_keys,(issues,secret_keys)
result={'files_verified':len(manifest['files']),'mismatches':issues,'sensitive_value_key_hits':secret_keys,
        'private_runtimes_packaged':False,'native_inputs_packaged':False,'scope':'Hash verification and exact JSON key scan; not a general security certification'}
(Path(__file__).parent/'package-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result))

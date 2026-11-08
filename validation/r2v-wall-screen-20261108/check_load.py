from pathlib import Path
import os,sys,json,hashlib,time,datetime
os.environ['CUDA_VISIBLE_DEVICES']=''
root=Path(__file__).parent
sys.path.insert(0,str(root/'adapted'))
receipt={'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'inference_ran':False,'weights_only':True,'device':'cpu','training_ran':False,'pretrained_backbone_download':False}
try:
 import torch
 from types import SimpleNamespace
 from models.model import Model
 torch.set_num_threads(2)
 meta=json.loads((root/'acquisition.json').read_text())
 assert hashlib.sha256((root/'checkpoint.pth').read_bytes()).hexdigest()==meta['weight']['sha256']
 start=time.monotonic()
 state=torch.load(root/'checkpoint.pth',map_location='cpu',weights_only=True)
 assert isinstance(state,dict) and 0<len(state)<2000
 assert all(isinstance(k,str) and isinstance(v,torch.Tensor) for k,v in state.items())
 assert all(torch.isfinite(v).all().item() for v in state.values())
 model=Model(SimpleNamespace(width=256,height=256))
 expected=model.state_dict()
 # PyTorch 1.0 state dict may omit later-generated BN counters; strict load separately reports compatibility.
 missing=sorted(set(expected)-set(state));extra=sorted(set(state)-set(expected))
 mismatch=[k for k in set(expected)&set(state) if expected[k].shape!=state[k].shape]
 receipt.update(torch_version=torch.__version__,checkpoint_keys=len(state),model_keys=len(expected),missing=missing,extra=extra,shape_mismatch=mismatch,parameter_count=sum(p.numel() for p in model.parameters()))
 assert not missing and not extra and not mismatch,'Checkpoint must exactly match the architecture'
 model.load_state_dict(state,strict=True)
 model.eval()
 receipt.update(strict_load_success=True,seconds=time.monotonic()-start)
except Exception as exc:
 receipt.update(strict_load_success=False,error=type(exc).__name__+': '+str(exc))
finally:
 receipt['finished_at']=datetime.datetime.now(datetime.timezone.utc).isoformat()
 (root/'load-receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
 print(json.dumps(receipt),flush=True)

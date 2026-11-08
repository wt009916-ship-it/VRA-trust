from pathlib import Path
import pickle,io,json,zipfile,hashlib,struct

ROOT=Path('C:/Users/18483/AppData/Local/Temp/vra-floorplan-feasibility-20261108')

def capture_wkb(value):
    if type(value) is not bytes or len(value)>10_000_000:raise ValueError('Invalid geometry bytes')
    return {'_wkb_hex':value.hex()}

class NumericDType:
    formats={'f8':'d','f4':'f','i8':'q','i4':'i','i2':'h','i1':'b','u8':'Q','u4':'I','u2':'H','u1':'B'}
    def __init__(self,kind,*args):
        if kind not in self.formats or any(type(x) is not bool for x in args):raise ValueError('Only numeric scalar dtype allowed')
        self.kind=kind;self.order='<'
    def __setstate__(self,state):
        if type(state) is not tuple or len(state)!=8 or state[0]!=3 or state[1] not in ('<','>','|') or state[2:5]!=(None,None,None):
            raise ValueError('Unsupported dtype state')
        self.order='<' if state[1]=='|' else state[1]

def capture_scalar(dtype,data):
    if type(dtype) is not NumericDType or type(data) is not bytes:raise ValueError('Only bounded numeric scalars allowed')
    fmt=dtype.order+dtype.formats[dtype.kind]
    if len(data)!=struct.calcsize(fmt):raise ValueError('Scalar byte count mismatch')
    return struct.unpack(fmt,data)[0]

class GeometryOnlyUnpickler(pickle.Unpickler):
    def find_class(self,module,name):
        if (module,name)==('shapely.io','from_wkb'):return capture_wkb
        if (module,name)==('numpy','dtype'):return NumericDType
        if (module,name)==('numpy._core.multiarray','scalar'):return capture_scalar
        raise pickle.UnpicklingError(f'Unapproved pickle global: {module}.{name}')

archive=ROOT/'ResPlan.zip'
assert hashlib.sha256(archive.read_bytes()).hexdigest()==json.loads((ROOT/'resplan-download.json').read_text())['sha256']
with zipfile.ZipFile(archive) as z:
    raw=z.read('ResPlan.pkl')
data=GeometryOnlyUnpickler(io.BytesIO(raw)).load()
assert type(data) is list and len(data)==17000
print(json.dumps({'count':len(data),'first_keys':list(data[0]),'first_non_geometry':{k:v for k,v in data[0].items() if not isinstance(v,(dict,list))}},default=str),flush=True)
selection=json.loads((ROOT/'selection-frozen.json').read_text())
# Canonical split IDs correspond to the published plan id; verify before selection.
assert all(type(row) is dict and type(row.get('id')) is int for row in data)
lookup={row['id']:row for row in data};assert len(lookup)==len(data)
selected=[lookup[i] for i in selection['ids']]
target=ROOT/'selected-geometries.json';assert not target.exists()
target.write_text(json.dumps({'selection':selection,'plans':selected},indent=2,allow_nan=False),encoding='utf-8')
print(json.dumps({'selected_ids':[r['id'] for r in selected],'json_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
                  'decoder':'Only shapely.io.from_wkb mapped to a bytes-to-hex capture function; no upstream constructors executed'}),flush=True)
